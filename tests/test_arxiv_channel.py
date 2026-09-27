"""Dedicated tests for the ``arxiv`` channel (mocked HTTP, no network)."""

import io
from email.message import Message
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from weblens.channels import _http
from weblens.channels.arxiv import ArxivChannel

_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <updated>2023-08-02T00:41:18Z</updated>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All
      You Need</title>
    <summary>  The dominant sequence
      transduction models.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <arxiv:comment>15 pages</arxiv:comment>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>"""

_ERROR_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/api/errors#incorrect_id_format_for_bad</id>
    <title>Error</title>
    <summary>incorrect id format for bad</summary>
  </entry>
</feed>"""


class _Resp(io.BytesIO):
    status = 200
    headers = Message()


def _fake(body, seen):
    def fake_open(req, timeout, allowed):
        seen.append((req.full_url, set(allowed)))
        return _Resp(body)

    return fake_open


def test_can_handle():
    ch = ArxivChannel()
    assert ch.can_handle("https://arxiv.org/abs/1706.03762")
    assert ch.can_handle("https://export.arxiv.org/abs/1706.03762")
    assert not ch.can_handle("https://arxiv.org.evil.test/abs/1")


def test_check_is_offline_and_ok():
    ch = ArxivChannel()
    with patch.object(_http, "_open", side_effect=AssertionError("network used")):
        status, _ = ch.check()
    assert status == "ok" and ch.active_backend == ch.backends[0] and ch.tier == 0


def test_search_free_text_ands_terms_and_parses_entries():
    seen: list = []
    with patch.object(_http, "_open", _fake(_FEED, seen)):
        results = ArxivChannel().search("attention transformer", limit=500, sort="submittedDate")
    url, allowed = seen[0]
    assert allowed == {"export.arxiv.org"}
    assert url.startswith("https://export.arxiv.org/api/query?")
    qs = parse_qs(urlsplit(url).query)
    assert qs["search_query"] == ["all:attention AND all:transformer"]
    assert qs["max_results"] == ["100"] and qs["sortBy"] == ["submittedDate"]
    paper = results[0]
    assert paper["id"] == "1706.03762v7"
    assert paper["title"] == "Attention Is All You Need"
    assert paper["summary"] == "The dominant sequence transduction models."
    assert paper["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper["primary_category"] == "cs.CL"
    assert paper["categories"] == ["cs.CL", "cs.LG"]
    assert paper["pdf_url"] == "http://arxiv.org/pdf/1706.03762v7"
    assert paper["comment"] == "15 pages"


def test_search_passes_field_syntax_through():
    seen: list = []
    with patch.object(_http, "_open", _fake(_FEED, seen)):
        ArxivChannel().search("au:hinton AND cat:cs.LG")
    assert parse_qs(urlsplit(seen[0][0]).query)["search_query"] == ["au:hinton AND cat:cs.LG"]


def test_search_rejects_bad_sort_and_empty_query():
    with pytest.raises(ValueError):
        ArxivChannel().search("x", sort="random")
    with pytest.raises(ValueError):
        ArxivChannel().search("  ")


@pytest.mark.parametrize("bad", ["", "abc", "1706.03762&max_results=1000", "../x", "1706"])
def test_get_paper_validates_id(bad):
    with patch.object(_http, "_open", side_effect=AssertionError("network used")):
        with pytest.raises(ValueError):
            ArxivChannel().get_paper(bad)


def test_get_paper_accepts_old_and_new_ids():
    for good in ("1706.03762", "arXiv:2401.01234v2", "hep-th/9901001v1", "math.GT/0309136"):
        seen: list = []
        with patch.object(_http, "_open", _fake(_FEED, seen)):
            ArxivChannel().get_paper(good)
        assert parse_qs(urlsplit(seen[0][0]).query)["id_list"][0] in good


def test_api_error_entry_raises():
    with patch.object(_http, "_open", _fake(_ERROR_FEED, [])), pytest.raises(ValueError, match="incorrect id"):
        ArxivChannel().search("x")


def test_read_handles_abs_and_pdf_urls():
    for url in ("https://arxiv.org/abs/1706.03762", "https://arxiv.org/pdf/1706.03762v7.pdf"):
        seen: list = []
        with patch.object(_http, "_open", _fake(_FEED, seen)):
            paper = ArxivChannel().read(url)
        assert paper["title"] == "Attention Is All You Need"
        assert parse_qs(urlsplit(seen[0][0]).query)["id_list"][0].startswith("1706.03762")
