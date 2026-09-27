"""Dedicated tests for the ``wikipedia`` channel (mocked HTTP, no network)."""

import io
import json
from email.message import Message
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from weblens.channels import _http
from weblens.channels.wikipedia import WikipediaChannel


class _Resp(io.BytesIO):
    status = 200
    headers = Message()


def _fake(payload, seen):
    def fake_open(req, timeout, allowed):
        seen.append((req.full_url, set(allowed)))
        return _Resp(json.dumps(payload).encode())

    return fake_open


def test_can_handle():
    ch = WikipediaChannel()
    assert ch.can_handle("https://en.wikipedia.org/wiki/Python")
    assert ch.can_handle("https://de.m.wikipedia.org/wiki/Berlin")
    assert not ch.can_handle("https://wikipedia.org.evil.test/wiki/X")
    assert not ch.can_handle("https://example.com/wiki/X")


def test_check_is_offline_and_ok():
    ch = WikipediaChannel()
    with patch.object(_http, "_open", side_effect=AssertionError("network used")):
        status, _ = ch.check()
    assert status == "ok" and ch.active_backend == ch.backends[0] and ch.tier == 0


@pytest.mark.parametrize(
    "lang", ["EN.evil.test", "e", "en/../x", "en.x", "1a", "www", "en_gb", "a" * 21, "-en"],
)
def test_invalid_language_codes_rejected(lang):
    with patch.object(_http, "_open", side_effect=AssertionError("network used")):
        with pytest.raises(ValueError):
            WikipediaChannel().get_summary("X", lang=lang)


def test_get_summary_encodes_title_and_pins_host():
    seen: list = []
    payload = {
        "title": "AC/DC",
        "description": "band",
        "extract": "Australian rock band.",
        "type": "standard",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/AC/DC"}},
    }
    with patch.object(_http, "_open", _fake(payload, seen)):
        result = WikipediaChannel().get_summary("AC/DC ?#")
    url, allowed = seen[0]
    assert url == "https://en.wikipedia.org/api/rest_v1/page/summary/AC%2FDC_%3F%23"
    assert allowed == {"en.wikipedia.org"}
    assert result["extract"] == "Australian rock band."
    assert result["url"] == "https://en.wikipedia.org/wiki/AC/DC"


def test_search_uses_action_api_and_strips_snippet_html():
    seen: list = []
    payload = {"query": {"search": [
        {"title": "Zürich", "pageid": 1, "snippet": '<span class="searchmatch">Zürich</span> is',
         "wordcount": 10, "timestamp": "t"}
    ]}}
    with patch.object(_http, "_open", _fake(payload, seen)):
        hits = WikipediaChannel().search("zürich & co", lang="de-ch", limit=999)
    url, allowed = seen[0]
    parsed = urlsplit(url)
    assert parsed.netloc == "de-ch.wikipedia.org" and parsed.path == "/w/api.php"
    qs = parse_qs(parsed.query)
    assert qs["list"] == ["search"] and qs["srsearch"] == ["zürich & co"] and qs["srlimit"] == ["50"]
    assert hits[0]["snippet"] == "Zürich is"
    assert hits[0]["url"] == "https://de-ch.wikipedia.org/wiki/Z%C3%BCrich"


def test_get_article_truncates_and_reports_missing():
    payload = {"query": {"pages": [{"title": "T", "extract": "abcdef"}]}}
    with patch.object(_http, "_open", _fake(payload, [])):
        art = WikipediaChannel().get_article("T", max_chars=3)
    assert art["text"] == "abc" and art["truncated"] is True

    missing = {"query": {"pages": [{"title": "Nope", "missing": True}]}}
    with patch.object(_http, "_open", _fake(missing, [])), pytest.raises(ValueError):
        WikipediaChannel().get_article("Nope")


def test_read_parses_language_and_title():
    seen: list = []
    payload = {"query": {"pages": [{"title": "Straße", "extract": "x"}]}}
    with patch.object(_http, "_open", _fake(payload, seen)):
        art = WikipediaChannel().read("https://de.m.wikipedia.org/wiki/Stra%C3%9Fe_des_17._Juni")
    url, allowed = seen[0]
    assert allowed == {"de.wikipedia.org"}
    assert parse_qs(urlsplit(url).query)["titles"] == ["Straße des 17. Juni"]
    assert art["lang"] == "de"


@pytest.mark.parametrize("lang", ["en", "simple", "zh-min-nan", "be-tarask", "roa-rup", "de-ch"])
def test_project_language_codes_accepted_and_host_pinned(lang):
    seen: list = []
    with patch.object(_http, "_open", _fake({"title": "X"}, seen)):
        WikipediaChannel().get_summary("X", lang=lang)
    url, allowed = seen[0]
    assert allowed == {f"{lang}.wikipedia.org"}
    assert urlsplit(url).hostname == f"{lang}.wikipedia.org"


@pytest.mark.parametrize(
    ("url", "lang"),
    [
        ("https://simple.wikipedia.org/wiki/Armenia", "simple"),
        ("https://zh-min-nan.wikipedia.org/wiki/Tâi-oân", "zh-min-nan"),
        ("https://be-tarask.m.wikipedia.org/wiki/Беларусь", "be-tarask"),
        ("https://wikipedia.org/wiki/Python_(programming_language)", "en"),
        ("https://www.wikipedia.org/wiki/Python", "en"),
        ("https://m.wikipedia.org/wiki/Python", "en"),
    ],
)
def test_read_maps_host_to_language(url, lang):
    seen: list = []
    payload = {"query": {"pages": [{"title": "T", "extract": "x"}]}}
    with patch.object(_http, "_open", _fake(payload, seen)):
        art = WikipediaChannel().read(url)
    assert art["lang"] == lang
    assert seen[0][1] == {f"{lang}.wikipedia.org"}


@pytest.mark.parametrize(
    "url",
    [
        "https://a.b.wikipedia.org/wiki/X",
        "https://en.x.wikipedia.org/wiki/X",
        "https://www.m.wikipedia.org/wiki/X",
        "https://1a.wikipedia.org/wiki/X",
    ],
)
def test_read_rejects_unexpected_wikipedia_hosts(url):
    with patch.object(_http, "_open", side_effect=AssertionError("network used")), \
            pytest.raises(ValueError):
        WikipediaChannel().read(url)
