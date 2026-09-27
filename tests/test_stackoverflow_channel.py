"""Dedicated tests for the ``stackoverflow`` channel (mocked HTTP, no network).

The Stack Exchange API always gzips (even errors), reports quota on every
response and can demand a per-method ``backoff``; all three are covered here.
"""

import gzip
import io
import json
import urllib.error
from email.message import Message
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from weblens.channels import _http
from weblens.channels import stackoverflow as so_mod
from weblens.channels.stackoverflow import StackOverflowChannel


class _Resp(io.BytesIO):
    status = 200

    def __init__(self, body):
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Encoding"] = "gzip"


def _gz(payload):
    return gzip.compress(json.dumps(payload).encode())


def _router(routes, seen):
    def fake_open(req, timeout, allowed):
        seen.append(req.full_url)
        path = urlsplit(req.full_url).path
        return _Resp(_gz(routes[path]))

    return fake_open


@pytest.fixture(autouse=True)
def _clear_backoff():
    so_mod._backoff_until.clear()
    yield
    so_mod._backoff_until.clear()


def _q(i, **kw):
    return {"question_id": i, "title": "How &amp; why", "link": f"https://stackoverflow.com/q/{i}",
            "score": 3, "answer_count": 1, "is_answered": True, "tags": ["python"],
            "owner": {"display_name": "alice"}, "creation_date": 1, **kw}


def test_can_handle():
    ch = StackOverflowChannel()
    for url in ("https://stackoverflow.com/questions/1", "https://unix.stackexchange.com/q/2",
                "https://superuser.com/q/3", "https://ru.stackoverflow.com/q/4"):
        assert ch.can_handle(url), url
    assert not ch.can_handle("https://stackoverflow.com.evil.test/q/1")


def test_check_is_offline_and_ok():
    ch = StackOverflowChannel()
    with patch.object(_http, "_open", side_effect=AssertionError("network used")):
        status, _ = ch.check()
    assert status == "ok" and ch.active_backend == ch.backends[0] and ch.tier == 0


def test_search_encodes_params_inflates_gzip_and_records_quota():
    seen: list = []
    routes = {"/2.3/search/advanced": {"items": [_q(1)], "quota_remaining": 250, "quota_max": 300}}
    ch = StackOverflowChannel()
    with patch.object(_http, "_open", _router(routes, seen)):
        results = ch.search("a&b=c #x", site="superuser", limit=1000, tagged=["python", "asyncio"],
                            accepted=True)
    qs = parse_qs(urlsplit(seen[0]).query)
    assert seen[0].startswith("https://api.stackexchange.com/2.3/search/advanced?")
    assert qs["q"] == ["a&b=c #x"] and qs["site"] == ["superuser"]
    assert qs["pagesize"] == ["100"] and qs["tagged"] == ["python;asyncio"]
    assert qs["accepted"] == ["True"]
    assert results[0]["title"] == "How & why" and results[0]["author"] == "alice"
    assert ch.last_quota == {"quota_remaining": 250, "quota_max": 300}


@pytest.mark.parametrize("site", ["stackoverflow&key=x", "../x", "a" * 60])
def test_invalid_site_rejected(site):
    with patch.object(_http, "_open", side_effect=AssertionError("network used")):
        with pytest.raises(ValueError):
            StackOverflowChannel().search("x", site=site)


def test_get_question_fetches_body_and_answers():
    seen: list = []
    routes = {
        "/2.3/questions/231767": {"items": [_q(231767, body="<p>What does <code>yield</code> do?</p>")]},
        "/2.3/questions/231767/answers": {"items": [
            {"answer_id": 9, "question_id": 231767, "score": 50, "is_accepted": True,
             "owner": {"display_name": "bob"}, "body": "<p>It makes a generator.</p>"}
        ]},
    }
    with patch.object(_http, "_open", _router(routes, seen)):
        q = StackOverflowChannel().read(
            "https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do"
        )
    assert q["body"] == "What does yield do?"
    assert q["answers"][0]["body"] == "It makes a generator."
    assert q["answers"][0]["url"] == "https://stackoverflow.com/a/9"
    answers_qs = parse_qs(urlsplit(seen[1]).query)
    assert answers_qs["filter"] == ["withbody"] and answers_qs["sort"] == ["votes"]


def test_read_maps_site_from_host():
    seen: list = []
    routes = {"/2.3/questions/5": {"items": [_q(5)]}}
    with patch.object(_http, "_open", _router(routes, seen)):
        StackOverflowChannel().get_question(5, site="unix", answer_limit=0)
    assert parse_qs(urlsplit(seen[0]).query)["site"] == ["unix"]
    assert StackOverflowChannel.site_from_host("unix.stackexchange.com") == "unix"
    assert StackOverflowChannel.site_from_host("ru.stackoverflow.com") == "ru.stackoverflow"
    assert StackOverflowChannel.site_from_host("www.superuser.com") == "superuser"
    assert StackOverflowChannel._site_host("ru.stackoverflow") == "ru.stackoverflow.com"
    assert StackOverflowChannel._site_host("unix") == "unix.stackexchange.com"


def test_ids_validated():
    for bad in ("abc", 0, "1;2", ["1", "x"], list(range(1, 102))):
        with pytest.raises(ValueError):
            StackOverflowChannel().get_answers(bad)


def test_api_error_body_is_surfaced():
    def fake_open(req, timeout, allowed):
        body = _gz({"error_id": 502, "error_name": "throttle_violation", "error_message": "too many"})
        hdrs = Message()
        hdrs["Content-Encoding"] = "gzip"
        raise urllib.error.HTTPError(req.full_url, 400, "Bad", hdrs, io.BytesIO(body))

    with patch.object(_http, "_open", fake_open), pytest.raises(RuntimeError, match="throttle_violation"):
        StackOverflowChannel().search("x")


def test_backoff_is_recorded_and_enforced():
    routes = {"/2.3/search/advanced": {"items": [], "backoff": 60}}
    ch = StackOverflowChannel()
    with patch.object(_http, "_open", _router(routes, [])):
        ch.search("x")
        with pytest.raises(RuntimeError, match="back off"):
            ch.search("y")


def test_short_backoff_sleeps_instead_of_failing(monkeypatch):
    slept = []
    monkeypatch.setattr(so_mod.time, "sleep", slept.append)
    so_mod._record_backoff("search/advanced", 2)
    routes = {"/2.3/search/advanced": {"items": []}}
    with patch.object(_http, "_open", _router(routes, [])):
        StackOverflowChannel().search("x")
    assert slept and 0 < slept[0] <= 2
