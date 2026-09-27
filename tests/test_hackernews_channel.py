"""Dedicated tests for the ``hackernews`` channel (mocked HTTP, no network)."""

import io
import json
from email.message import Message
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from weblens.channels import _http
from weblens.channels.hackernews import HackerNewsChannel

FB = "https://hacker-news.firebaseio.com/v0"


class _Resp(io.BytesIO):
    status = 200
    headers = Message()


def _router(routes: dict, seen: list):
    def fake_open(req, timeout, allowed):
        seen.append(req.full_url)
        key = req.full_url.split("?", 1)[0]
        if key not in routes:
            raise AssertionError(f"unexpected URL {req.full_url}")
        return _Resp(json.dumps(routes[key]).encode())

    return fake_open


def _item(i, **kw):
    return {"id": i, "type": "story", "by": f"u{i}", "time": 1, **kw}


# --- can_handle / check ---

def test_can_handle():
    ch = HackerNewsChannel()
    assert ch.can_handle("https://news.ycombinator.com/item?id=1")
    assert not ch.can_handle("https://news.ycombinator.com.evil.test/item?id=1")
    assert not ch.can_handle("https://example.com")


def test_check_is_offline_and_ok():
    ch = HackerNewsChannel()
    with patch.object(_http, "_open", side_effect=AssertionError("network used")):
        status, msg = ch.check()
    assert status == "ok" and msg
    assert ch.active_backend == ch.backends[0]
    assert ch.tier == 0


# --- stories ---

def test_get_stories_limits_and_shapes():
    seen: list = []
    routes = {
        f"{FB}/topstories.json": [3, 2, 1],
        f"{FB}/item/3.json": _item(3, title="T3", url="https://a.test", score=10, descendants=4),
        f"{FB}/item/2.json": _item(2, title="Ask HN", text="<p>hi &amp; bye"),
    }
    with patch.object(_http, "_open", _router(routes, seen)):
        stories = HackerNewsChannel().get_stories("top", limit=2)
    assert [s["id"] for s in stories] == [3, 2]
    assert stories[0]["url"] == "https://a.test"
    assert stories[0]["comments_count"] == 4
    assert stories[1]["url"] == "https://news.ycombinator.com/item?id=2"
    assert stories[1]["text"] == "hi & bye"
    assert f"{FB}/item/1.json" not in seen


def test_get_stories_rejects_unknown_kind():
    with pytest.raises(ValueError):
        HackerNewsChannel().get_stories("../evil")


# --- item + comments ---

def test_get_item_walks_comments_breadth_first_with_budget():
    routes = {
        f"{FB}/item/10.json": _item(10, title="S", kids=[11, 12, 13]),
        f"{FB}/item/11.json": {"id": 11, "by": "a", "text": "c11", "kids": [21]},
        f"{FB}/item/12.json": {"id": 12, "deleted": True},
        f"{FB}/item/13.json": {"id": 13, "by": "b", "text": "c13"},
        f"{FB}/item/21.json": {"id": 21, "by": "c", "text": "c21", "kids": [31]},
    }
    with patch.object(_http, "_open", _router(routes, [])):
        item = HackerNewsChannel().get_item(10, comment_limit=10, max_depth=2)
    got = [(c["id"], c["depth"], c["parent"]) for c in item["comments"]]
    assert got == [(11, 1, 10), (13, 1, 10), (21, 2, 11)]  # 12 deleted, 31 past depth


def test_get_item_rejects_bad_id():
    for bad in ("abc", 0, -1, "1/../2"):
        with pytest.raises(ValueError):
            HackerNewsChannel().get_item(bad)


def test_read_parses_item_url():
    routes = {f"{FB}/item/42.json": _item(42, title="X")}
    with patch.object(_http, "_open", _router(routes, [])):
        item = HackerNewsChannel().read("https://news.ycombinator.com/item?id=42")
    assert item["title"] == "X" and item["comments"] == []


# --- search ---

def test_search_encodes_query_and_shapes_hits():
    seen: list = []
    routes = {
        "https://hn.algolia.com/api/v1/search_by_date": {
            "hits": [
                {"objectID": "7", "title": "Rust", "url": None, "points": 5,
                 "num_comments": 2, "author": "z", "created_at": "2026-01-01"}
            ]
        }
    }
    with patch.object(_http, "_open", _router(routes, seen)):
        hits = HackerNewsChannel().search("rust & go?", limit=500, sort="date")
    qs = parse_qs(urlsplit(seen[0]).query)
    assert qs == {"query": ["rust & go?"], "hitsPerPage": ["100"], "tags": ["story"]}
    assert hits[0]["id"] == 7
    assert hits[0]["url"] == "https://news.ycombinator.com/item?id=7"


def test_get_user_validates_username():
    with pytest.raises(ValueError):
        HackerNewsChannel().get_user("../admin")
    routes = {f"{FB}/user/pg.json": {"id": "pg", "karma": 9, "submitted": [1, 2]}}
    with patch.object(_http, "_open", _router(routes, [])):
        user = HackerNewsChannel().get_user("pg")
    assert user["karma"] == 9 and user["submitted_count"] == 2
