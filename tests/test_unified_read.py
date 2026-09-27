"""`weblens read` routing and adapters (all upstream calls mocked)."""

from __future__ import annotations

import base64
import email.message
import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weblens.channels import get_channel
from weblens.unified import github as gh
from weblens.unified import read as rd
from weblens.unified import upstream
from weblens.unified import youtube as yt
from weblens.unified.errors import ToolMissingError, UsageError, WebLensError
from weblens.unified.models import ReadResult

# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("url", "channel"),
    [
        ("https://news.ycombinator.com/item?id=1", "hackernews"),
        ("https://en.wikipedia.org/wiki/Armenia", "wikipedia"),
        ("https://arxiv.org/abs/1706.03762", "arxiv"),
        ("https://stackoverflow.com/questions/231767", "stackoverflow"),
        ("https://unix.stackexchange.com/questions/1/x", "stackoverflow"),
        ("https://www.youtube.com/watch?v=jNQXAC9IVRw", "youtube"),
        ("https://youtu.be/jNQXAC9IVRw", "youtube"),
        ("https://github.com/python/cpython", "github"),
        ("https://www.v2ex.com/t/123", "v2ex"),
        ("https://www.reddit.com/r/rust/comments/abc/x/", "reddit"),
        ("https://x.com/jack/status/20", "twitter"),
        ("https://www.bilibili.com/video/BV1xx411c7mD", "bilibili"),
        ("https://www.linkedin.com/in/someone", "linkedin"),
        ("https://github.blog/feed/", "rss"),
        ("https://example.com/", "web"),
        # lookalike hosts must not match platform channels
        ("https://github.com.evil.test/a/b", "web"),
    ],
)
def test_route_most_specific_first(url, channel):
    assert rd.route(url).name == channel


def test_ordered_channels_put_rss_then_web_last_and_skip_search_only():
    names = [ch.name for ch in rd.ordered_channels()]
    assert names[-2:] == ["rss", "web"]
    assert names[: len(rd.ROUTE_ORDER)] == rd.ROUTE_ORDER
    assert "exa_search" not in names


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/python/cpython/releases.atom",
        "https://news.ycombinator.com/rss",
        "https://rss.arxiv.org/rss/cs.AI",
        "https://export.arxiv.org/rss/cs.AI",
        "https://www.reddit.com/r/rust/.rss",
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC123",
        "https://stackoverflow.com/feeds/tag/python",
        "https://en.wikipedia.org/w/index.php?title=Special:RecentChanges&feed=atom",
    ],
)
def test_feed_shaped_urls_on_platform_hosts_go_to_feedparser(url):
    # Feed-shaped URLs beat platform routing unless the URL is a native page shape.
    assert rd.route(url).name == "rss"


@pytest.mark.parametrize(
    ("url", "channel"),
    [
        # native shapes win even when the last segment looks feed-like
        ("https://github.com/atom/atom", "github"),
        ("https://github.com/someone/feed", "github"),
        ("https://github.com/o/r/blob/main/feed.xml", "github"),
        ("https://en.wikipedia.org/wiki/RSS", "wikipedia"),
        ("https://stackoverflow.com/questions/1/rss", "stackoverflow"),
        # substring lookalikes are not feeds any more
        ("https://www.npmjs.com/package/atomically", "web"),
        ("https://medium.com/@bradfrost/atomic-design-methodology", "web"),
        ("https://example.com/feedback", "web"),
        ("https://example.com/rss-guide", "web"),
        ("https://www.linkedin.com/feed/update/urn:li:activity:1/", "linkedin"),
    ],
)
def test_non_feed_urls_keep_their_route(url, channel):
    assert rd.route(url).name == channel


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/feed", True),
        ("https://example.com/feed/", True),
        ("https://example.com/RSS/", True),
        ("https://example.com/blog/atom.xml", True),
        ("https://example.com/index.atom", True),
        ("https://example.com/x.rss", True),
        ("https://example.com/feeds/posts/default", True),
        ("https://example.com/news?format=rss", True),
        ("https://example.com/?feed=rss2", True),
        ("https://feeds.feedburner.com/example", True),
        ("https://rss.arxiv.org/rss/cs.AI", True),
        ("https://example.com/atomically", False),
        ("https://example.com/atomic-design", False),
        ("https://example.com/feedback", False),
        ("https://example.com/feed/update/123", False),
        ("https://example.com/rss-readers", False),
        ("https://rss.com/", False),
        ("https://example.com/?format=json", False),
        ("ftp://example.com/feed", False),
    ],
)
def test_is_feed_url_is_strict(url, expected):
    from weblens.channels.rss import is_feed_url

    assert is_feed_url(url) is expected


# --------------------------------------------------------------------------- #
# read_url entry point
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("url", ["http://localhost/x", "ftp://example.com", "", "http://10.0.0.1/"])
def test_read_url_rejects_non_public_urls_as_usage_error(url):
    with pytest.raises(UsageError) as info:
        rd.read_url(url)
    assert info.value.exit_code == 2


def test_read_url_rejects_non_positive_max_chars():
    with pytest.raises(UsageError):
        rd.read_url("https://example.com", max_chars=0)


def test_read_url_truncates_body():
    fake = ReadResult(title="t", url="u", source="web", body="x" * 100)
    with patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url("https://example.com", max_chars=10)
    assert result.truncated is True
    assert result.body.startswith("x" * 10)
    assert len(result.body) <= 12


def test_read_url_maps_unexpected_errors_to_actionable_error():
    with patch.object(rd, "_read_web", side_effect=urllib.error.URLError("offline")):
        with pytest.raises(WebLensError) as info:
            rd.read_url("https://example.com")
    assert "network error" in info.value.one_line()
    assert info.value.exit_code == 1


def test_read_url_generic_channel_without_reader_falls_back_to_jina_with_note():
    fake = ReadResult(title="t", url="u", source="web", body="b")
    with patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url("https://www.linkedin.com/in/someone")
    assert result.source == "linkedin"
    assert "Jina" in result.notes[0]


# --------------------------------------------------------------------------- #
# Native adapters
# --------------------------------------------------------------------------- #


def test_hackernews_adapter_formats_story_and_comments():
    item = {
        "id": 1, "title": "Y Combinator", "url": "http://ycombinator.com",
        "hn_url": "https://news.ycombinator.com/item?id=1", "score": 57, "author": "pg",
        "time": 1160418111, "type": "story", "comments_count": 3, "text": "",
        "comments": [
            {"author": "sama", "text": "hi", "depth": 1},
            {"author": "pg", "text": "reply", "depth": 2},
        ],
    }
    ch = get_channel("hackernews")
    with patch.object(type(ch), "read", return_value=item):
        result = rd.read_url("https://news.ycombinator.com/item?id=1")
    assert result.title == "Y Combinator"
    assert result.metadata["points"] == 57
    assert result.metadata["date"].startswith("2006-10-09")
    assert result.metadata["link"] == "http://ycombinator.com"
    assert "- **sama**: hi" in result.body
    assert "  - **pg**: reply" in result.body


def test_wikipedia_adapter_passes_max_chars():
    ch = get_channel("wikipedia")
    article = {"title": "Armenia", "url": "https://en.wikipedia.org/wiki/Armenia",
               "lang": "en", "text": "Armenia is...", "truncated": True}
    with patch.object(type(ch), "read", return_value=article) as read:
        result = rd.read_url("https://en.wikipedia.org/wiki/Armenia", max_chars=500)
    assert read.call_args.kwargs["max_chars"] == 500
    assert result.truncated is True
    assert result.body == "Armenia is..."


def test_arxiv_adapter():
    ch = get_channel("arxiv")
    paper = {"id": "1706.03762v7", "title": "Attention Is All You Need",
             "authors": ["A", "B"], "summary": "We propose", "published": "2017-06-12",
             "categories": ["cs.CL"], "pdf_url": "https://arxiv.org/pdf/1706.03762v7",
             "url": "https://arxiv.org/abs/1706.03762v7"}
    with patch.object(type(ch), "read", return_value=paper):
        result = rd.read_url("https://arxiv.org/abs/1706.03762")
    assert result.metadata["authors"] == "A, B"
    assert "We propose" in result.body


def test_stackoverflow_adapter_lists_answers():
    ch = get_channel("stackoverflow")
    question = {"title": "What does yield do?", "url": "https://stackoverflow.com/q/231767",
                "score": 10, "answer_count": 1, "tags": ["python"], "author": "A",
                "creation_date": 1224800471, "body": "Q body",
                "answers": [{"author": "B", "score": 5, "is_accepted": True, "body": "A body"}]}
    with patch.object(type(ch), "read", return_value=question):
        result = rd.read_url("https://stackoverflow.com/questions/231767")
    assert "Answer by B (score 5 ✓ accepted)" in result.body
    assert result.metadata["tags"] == "python"


def test_v2ex_topic_adapter_and_non_topic_fallback():
    ch = get_channel("v2ex")
    topic = {"id": 5, "title": "T", "url": "https://www.v2ex.com/t/5", "content": "C",
             "replies_count": 1, "node_title": "Python", "author": "u", "created": 0,
             "replies": [{"author": "r", "content": "hello"}]}
    with patch.object(type(ch), "get_topic", return_value=topic) as get_topic:
        result = rd.read_url("https://www.v2ex.com/t/5#reply1")
    get_topic.assert_called_once_with(5)
    assert "- **r**: hello" in result.body

    fake = ReadResult(title="go", url="u", source="web")
    with patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url("https://www.v2ex.com/go/python")
    assert "only V2EX topic URLs" in result.notes[0]


# --------------------------------------------------------------------------- #
# Web / Jina parsing
# --------------------------------------------------------------------------- #


def test_parse_jina_splits_header_and_body():
    text = ("Title: Example Domain\n\nURL Source: https://example.com\n\n"
            "Published Time: Mon\n\nMarkdown Content:\nHello *world*\n")
    title, meta, body = rd.parse_jina(text)
    assert title == "Example Domain"
    assert meta == {"published": "Mon"}
    assert body == "Hello *world*"


def test_parse_jina_without_header_returns_whole_text():
    assert rd.parse_jina("just text") == ("", {}, "just text")


def test_web_adapter_uses_jina_channel():
    ch = get_channel("web")
    with patch.object(type(ch), "read", return_value="Title: T\n\nMarkdown Content:\nbody"):
        result = rd.read_url("https://example.com")
    assert (result.title, result.body, result.backend) == ("T", "body", "Jina Reader")


# --------------------------------------------------------------------------- #
# RSS
# --------------------------------------------------------------------------- #

_FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>My Feed</title>
<link>https://blog.example.com/</link><description>desc</description>
<item><title>Post 1</title><link>https://blog.example.com/1</link>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate><description>&lt;p&gt;Hello&lt;/p&gt;</description></item>
</channel></rss>"""


def test_rss_adapter_parses_feed():
    with patch("weblens.channels._http.fetch_public", return_value=("https://blog.example.com/feed", _FEED)):
        result = rd.read_url("https://blog.example.com/feed")
    assert result.source == "rss"
    assert result.title == "My Feed"
    assert result.metadata["entries"] == 1
    assert "### Post 1" in result.body and "Hello" in result.body


def test_rss_adapter_falls_back_to_web_for_non_feeds():
    fake = ReadResult(title="page", url="u", source="web", backend="Jina Reader", body="b")
    with patch("weblens.channels._http.fetch_public", return_value=("u", b"<html>no feed</html>")), \
            patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url("https://example.com/feed")
    assert result.source == "web"
    assert result.notes[0] == ("the URL looks like a feed, but it is not a parseable RSS/Atom feed; "
                               "read via Jina Reader instead")


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.HTTPError("https://example.com/feed", 403, "Forbidden", email.message.Message(), None),
        urllib.error.URLError("connection refused"),
        TimeoutError("slow"),
        ValueError("response exceeds the byte safety limit"),
        RuntimeError("boom"),
        WebLensError("feedparser not installed", "pip install feedparser"),
    ],
)
def test_rss_any_failure_falls_back_to_web_with_note(error):
    fake = ReadResult(title="page", url="u", source="web", backend="Jina Reader", body="b")
    with patch.object(rd, "_read_rss", side_effect=error), \
            patch.object(rd, "_read_web", return_value=fake) as web:
        result = rd.read_url("https://example.com/feed")
    web.assert_called_once()
    assert result.body == "b"
    assert result.notes[0].startswith("the URL looks like a feed, but reading it as a feed failed (")
    assert result.notes[0].endswith("; read via Jina Reader instead")


def test_rss_failure_on_platform_host_falls_back_to_the_platform_route():
    fake = ReadResult(title="page", url="u", source="web", backend="Jina Reader", body="b")
    with patch.object(rd, "_read_rss", side_effect=rd._NotAFeed()), \
            patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url("https://github.com/python/cpython/releases.atom")
    assert result.source == "github"  # the GitHub route: Jina with its own note
    assert "not a parseable RSS/Atom feed" in result.notes[0]
    assert "github page type has no native reader" in result.notes[1]


def test_platform_feed_url_is_read_with_feedparser():
    with patch("weblens.channels._http.fetch_public",
               return_value=("https://news.ycombinator.com/rss", _FEED)) as fetch:
        result = rd.read_url("https://news.ycombinator.com/rss")
    fetch.assert_called_once()
    assert (result.source, result.title, result.notes) == ("rss", "My Feed", [])


def test_non_feed_page_has_no_feed_note():
    fake = ReadResult(title="npm", url="u", source="web", backend="Jina Reader", body="b")
    with patch("weblens.channels._http.fetch_public") as fetch, \
            patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url("https://www.npmjs.com/package/atomically")
    fetch.assert_not_called()
    assert result.notes == []


def test_sniffed_feed_that_fails_to_parse_falls_back_with_note():
    fake = ReadResult(title="page", url="u", source="web", backend="Jina Reader", body="b")
    with patch.object(rd, "_sniff_feed", return_value=("https://e.example/x", b"<rss>")), \
            patch.object(rd, "_parse_feed", side_effect=RuntimeError("bad")), \
            patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url("https://e.example/x")
    assert result.notes[0].startswith("the response looked like a feed, but reading it as a feed failed")


# --------------------------------------------------------------------------- #
# Upstream-CLI platforms
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("channel", "backend", "url", "argv"),
    [
        ("reddit", "OpenCLI", "https://www.reddit.com/r/x/comments/abc12/t/",
         ["opencli", "reddit", "read", "abc12", "-f", "yaml"]),
        ("reddit", "rdt-cli", "https://www.reddit.com/r/x/comments/abc12/t/",
         ["rdt", "read", "abc12", "--yaml"]),
        ("twitter", "twitter-cli", "https://x.com/a/status/1",
         ["twitter", "tweet", "https://x.com/a/status/1", "--yaml"]),
        ("twitter", "OpenCLI", "https://x.com/a/status/1", None),
        ("bilibili", "bili-cli", "https://www.bilibili.com/video/BV1xx411c7mD",
         ["bili", "video", "BV1xx411c7mD"]),
        ("bilibili", "Bilibili search API", "https://www.bilibili.com/video/BV1xx411c7mD", None),
        ("reddit", "OpenCLI", "https://www.reddit.com/r/x/", None),
    ],
)
def test_upstream_read_argv(channel, backend, url, argv):
    assert rd.upstream_read_argv(channel, backend, url) == argv


def test_upstream_read_runs_active_backend_cli():
    ch = get_channel("reddit")

    def fake_check(self, config=None):
        self.active_backend = "rdt-cli"
        return "ok", ""

    proc = upstream.CommandResult(0, "title: Hello post\nbody: text\n", "")
    with patch.object(type(ch), "check", fake_check), \
            patch.object(upstream, "run", return_value=proc) as run:
        result = rd.read_url("https://www.reddit.com/r/x/comments/abc12/t/")
    assert run.call_args.args[0] == ["rdt", "read", "abc12", "--yaml"]
    assert result.title == "Hello post"
    assert result.backend == "rdt-cli"


def test_upstream_read_failure_is_actionable():
    ch = get_channel("reddit")

    def fake_check(self, config=None):
        self.active_backend = "rdt-cli"
        return "ok", ""

    proc = upstream.CommandResult(1, "", "Error: not logged in")
    with patch.object(type(ch), "check", fake_check), \
            patch.object(upstream, "run", return_value=proc):
        with pytest.raises(WebLensError, match="rdt failed"):
            rd.read_url("https://www.reddit.com/r/x/comments/abc12/t/")


def test_upstream_read_without_backend_falls_back_to_jina_with_note():
    ch = get_channel("twitter")

    def fake_check(self, config=None):
        self.active_backend = None
        return "off", ""

    fake = ReadResult(title="t", url="u", source="web", body="b")
    with patch.object(type(ch), "check", fake_check), \
            patch.object(rd, "_read_web", return_value=fake), \
            patch.object(upstream, "run") as run:
        result = rd.read_url("https://x.com/a/status/1")
    run.assert_not_called()
    assert "no working twitter backend" in result.notes[0]


# --------------------------------------------------------------------------- #
# YouTube (yt-dlp)
# --------------------------------------------------------------------------- #

_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
All right, so here we are

00:00:02.000 --> 00:00:04.000 align:start
All right, so here we are
<c>in front of</c> the elephants
"""

_INFO = {
    "id": "jNQXAC9IVRw", "title": "Me at the zoo", "channel": "jawed",
    "upload_date": "20050424", "duration": 19, "view_count": 1000, "language": "en",
    "description": "desc", "webpage_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "subtitles": {"en": [{"ext": "vtt"}]}, "automatic_captions": {},
}


class _FakeYtDlp:
    """Scripted yt-dlp: -J returns info; subtitle calls write a file or fail."""

    def __init__(self, info=None, sub_outcomes=("ok",)):
        self.info = info or _INFO
        self.sub_outcomes = list(sub_outcomes)
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout=None, env=None):
        self.calls.append(list(argv))
        if "-J" in argv:
            return upstream.CommandResult(0, json.dumps(self.info), "")
        outcome = self.sub_outcomes.pop(0)
        if outcome == "ok":
            tmp = Path(argv[argv.index("-P") + 1])
            (tmp / "subs.en.vtt").write_text(_VTT, encoding="utf-8")
            return upstream.CommandResult(0, "", "")
        return upstream.CommandResult(
            1, "", "ERROR: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests")


def test_clean_url_strips_playlist_params():
    assert yt.clean_url("https://www.youtube.com/watch?v=abc&list=PL1&index=3&t=10") == \
        "https://www.youtube.com/watch?v=abc&t=10"


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        ({"language": "en", "subtitles": {"en": [1], "de": [1]}}, ("en", False)),
        ({"language": "de", "subtitles": {"de": [1]}, "automatic_captions": {"en": [1]}}, ("de", False)),
        ({"language": "en", "subtitles": {"live_chat": [1]},
          "automatic_captions": {"en-orig": [1], "en": [1]}}, ("en-orig", True)),
        ({"language": "ja", "automatic_captions": {"ja-orig": [1], "ja": [1], "en": [1]}}, ("ja-orig", True)),
        ({"language": "", "automatic_captions": {"en": [1]}}, ("en", True)),
        ({"language": "en-US", "subtitles": {"en-US": [1]}}, ("en-US", False)),
        ({}, None),
    ],
)
def test_choose_subtitle_preference(info, expected):
    assert yt.choose_subtitle(info) == expected


def test_vtt_to_text_drops_timing_tags_and_rolling_duplicates():
    assert yt.vtt_to_text(_VTT) == "All right, so here we are in front of the elephants"


def test_youtube_read_metadata_and_manual_subtitles():
    fake = _FakeYtDlp()
    result = yt.read("https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PL1", run=fake)
    first = fake.calls[0]
    assert first[:2] == ["yt-dlp", "-J"] and "--no-playlist" in first
    assert first[-1] == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    sub_call = fake.calls[1]
    assert "--write-subs" in sub_call and "--load-info-json" in sub_call
    assert sub_call[sub_call.index("--sub-langs") + 1] == "en"
    assert result.metadata["date"] == "2005-04-24"
    assert result.metadata["duration"] == "0:19"
    assert result.metadata["subtitles"] == "en (manual)"
    assert "## Transcript (en, manual)" in result.body
    assert "elephants" in result.body
    assert result.notes == []


def test_youtube_subtitle_429_retries_once_with_sleep_and_player_client():
    fake = _FakeYtDlp(sub_outcomes=("429", "ok"))
    result = yt.read("https://youtu.be/jNQXAC9IVRw", run=fake)
    retry = fake.calls[2]
    assert retry[retry.index("--sleep-subtitles") + 1] == "5"
    assert retry[retry.index("--extractor-args") + 1] == "youtube:player_client=default"
    assert "--load-info-json" not in retry
    assert "elephants" in result.body


def test_youtube_subtitle_429_twice_returns_metadata_with_note():
    fake = _FakeYtDlp(sub_outcomes=("429", "429"))
    result = yt.read("https://youtu.be/jNQXAC9IVRw", run=fake)
    assert len(fake.calls) == 3
    assert result.title == "Me at the zoo"
    assert "Transcript" not in result.body
    assert "HTTP 429" in result.notes[0]


def test_youtube_no_subtitles_note():
    info = dict(_INFO, subtitles={}, automatic_captions={})
    fake = _FakeYtDlp(info=info)
    result = yt.read("https://youtu.be/x", run=fake)
    assert len(fake.calls) == 1
    assert result.notes == ["no subtitles available for this video"]


def test_youtube_extraction_error_is_actionable():
    def run(argv, timeout=None, env=None):
        return upstream.CommandResult(1, "", "ERROR: [youtube] x: Sign in to confirm you're not a bot")

    with pytest.raises(WebLensError) as info:
        yt.read("https://youtu.be/x", run=run)
    assert "youtube-cookies" in info.value.one_line()


def test_youtube_missing_ytdlp_raises_tool_missing():
    def run(argv, timeout=None, env=None):
        raise ToolMissingError("yt-dlp")

    with pytest.raises(ToolMissingError) as info:
        yt.read("https://youtu.be/x", run=run)
    assert info.value.one_line().startswith("yt-dlp not installed: python -m pip install")


# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/python/cpython", {"owner": "python", "repo": "cpython", "kind": "repo"}),
        ("https://github.com/python/cpython.git", {"owner": "python", "repo": "cpython", "kind": "repo"}),
        ("https://github.com/a/b/issues/12", {"owner": "a", "repo": "b", "kind": "issue", "number": "12"}),
        ("https://github.com/a/b/pull/7", {"owner": "a", "repo": "b", "kind": "pull", "number": "7"}),
        ("https://www.github.com/a/b/pull/7/", {"owner": "a", "repo": "b", "kind": "pull", "number": "7"}),
        ("https://github.com/a/b/blob/main/src/x.py",
         {"owner": "a", "repo": "b", "kind": "blob", "ref": "main", "path": "src/x.py"}),
    ],
)
def test_github_parse_url(url, expected):
    assert gh.parse_url(url) == expected


def test_github_parse_url_rejects_bare_owner():
    with pytest.raises(WebLensError):
        gh.parse_url("https://github.com/python")


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/features/copilot",
        "https://github.com/topics/rust",
        "https://github.com/orgs/python/repositories",
        "https://github.com/marketplace/actions/checkout",
        "https://github.com/sponsors/someone",
        "https://github.com/settings/tokens",
        "https://github.com/customer-stories/x",
        "https://github.com/python/cpython/tree/main/Lib",
        "https://github.com/python/cpython/releases",
        "https://github.com/python/cpython/releases/tag/v3.13.0",
        "https://github.com/python/cpython/wiki",
        "https://github.com/python/cpython/actions",
        "https://github.com/python/cpython/commits/main",
        "https://github.com/python/cpython/compare/a...b",
        "https://github.com/python/cpython/discussions/1",
        "https://github.com/python/cpython/pull/7/files",
        "https://github.com/python/cpython/issues",
        "https://github.com/python/cpython/blob/main",
        "https://gist.github.com/user/abc",
    ],
)
def test_github_only_exact_shapes_are_native(url):
    assert gh.is_native_url(url) is False
    with pytest.raises(WebLensError):
        gh.parse_url(url)


@pytest.mark.parametrize(
    ("url", "note"),
    [
        ("https://github.com/features/copilot", False),
        ("https://github.com/topics/rust", False),
        ("https://github.com/python/cpython/releases/tag/v3.13.0", True),
        ("https://github.com/python/cpython/tree/main/Lib", True),
    ],
)
def test_github_non_native_pages_are_read_as_web(url, note):
    fake = ReadResult(title="t", url=url, source="web", backend="Jina Reader", body="b")
    with patch.object(rd, "_read_web", return_value=fake) as web, \
            patch.object(gh, "read") as native:
        result = rd.read_url(url)
    native.assert_not_called()
    web.assert_called_once()
    if note:  # repo subpage: attributed to GitHub, with a note
        assert result.source == "github"
        assert "no native reader" in result.notes[0]
    else:  # github.com site page: an ordinary web page
        assert (result.source, result.notes) == ("web", [])


def test_github_native_shapes_use_the_native_reader():
    fake = ReadResult(title="t", url="u", source="github", body="b")
    for url in ("https://github.com/python/cpython", "https://github.com/a/b/issues/3",
                "https://github.com/a/b/pull/4", "https://github.com/a/b/blob/main/src/x.py"):
        with patch.object(gh, "read", return_value=fake) as native, patch.object(rd, "_read_web") as web:
            rd.read_url(url)
        native.assert_called_once()
        web.assert_not_called()


def _issue_routes(number: str, *, is_pr: bool) -> dict:
    issue = {"title": "T", "state": "open", "user": {"login": "u"}, "comments": 0, "labels": [],
             "body": "desc",
             "html_url": f"https://github.com/a/b/{'pull' if is_pr else 'issues'}/{number}"}
    if is_pr:
        issue["pull_request"] = {"url": "x"}
    routes = {f"repos/a/b/issues/{number}": issue}
    if is_pr:
        routes[f"repos/a/b/pulls/{number}"] = {"merged": False, "head": {"label": "a:f"},
                                              "base": {"label": "a:main"}}
    return routes


def _get_from(routes):
    def fake(url, **kw):
        key = url.removeprefix("https://api.github.com/")
        if key not in routes:
            raise AssertionError(f"unexpected API call {key}")
        return routes[key]
    return fake


def test_github_pull_url_that_is_an_issue_reads_the_issue():
    with patch("weblens.channels._http.get_json", side_effect=_get_from(_issue_routes("9", is_pr=False))):
        result = gh.read("https://github.com/a/b/pull/9", use_gh=False)
    assert result.metadata["type"] == "issue"
    assert "merged" not in result.metadata
    assert result.url == "https://github.com/a/b/issues/9"
    assert "#9 is an issue, not a pull request" in result.notes


def test_github_issue_url_that_is_a_pull_request_reads_the_pr():
    with patch("weblens.channels._http.get_json", side_effect=_get_from(_issue_routes("5", is_pr=True))):
        result = gh.read("https://github.com/a/b/issues/5", use_gh=False)
    assert result.metadata["type"] == "pull request"
    assert result.metadata["merged"] is False
    assert result.url == "https://github.com/a/b/pull/5"
    assert any("is a pull request" in n for n in result.notes)


def test_github_blob_directory_renders_a_listing():
    listing = [
        {"name": "sessions.py", "type": "file", "size": 30000},
        {"name": "__init__.py", "type": "file", "size": 4000},
        {"name": "adapters", "type": "dir"},
        {"name": "vendored", "type": "submodule"},
    ]
    routes = {"repos/psf/requests/contents/src/requests?ref=main": listing}
    with patch("weblens.channels._http.get_json", side_effect=_get_from(routes)):
        result = gh.read("https://github.com/psf/requests/blob/main/src/requests", use_gh=False)
    assert result.title == "psf/requests: src/requests/"
    assert result.url == "https://github.com/psf/requests/tree/main/src/requests"
    assert result.metadata == {"ref": "main", "type": "directory", "entries": 4}
    lines = result.body.splitlines()
    assert lines[0] == "## Directory src/requests/ (4 entries)"
    assert lines[2:] == ["- adapters/", "- __init__.py (4000 bytes)", "- sessions.py (30000 bytes)",
                         "- vendored (submodule)"]


def test_github_blob_file_still_decodes_content():
    content = base64.b64encode(b"print('hi')\n").decode()
    routes = {"repos/a/b/contents/x.py?ref=main": {"encoding": "base64", "content": content, "size": 12}}
    with patch("weblens.channels._http.get_json", side_effect=_get_from(routes)):
        result = gh.read("https://github.com/a/b/blob/main/x.py", use_gh=False)
    assert result.body == "print('hi')\n"
    assert result.metadata == {"ref": "main", "size": 12}


def _repo_routes():
    readme = base64.b64encode(b"# CPython\nhello").decode()
    return {
        "repos/python/cpython": {"full_name": "python/cpython", "html_url": "https://github.com/python/cpython",
                                 "description": "The Python programming language", "stargazers_count": 1,
                                 "language": "Python", "topics": ["a", "b"]},
        "repos/python/cpython/readme": {"encoding": "base64", "content": readme},
    }


def test_github_repo_read_via_public_api():
    routes = _repo_routes()

    def fake_get_json(url, allowed_hosts, **kw):
        assert allowed_hosts == frozenset({"api.github.com"})
        return routes[url.removeprefix("https://api.github.com/")]

    with patch("weblens.channels._http.get_json", side_effect=fake_get_json):
        result = gh.read("https://github.com/python/cpython", use_gh=False)
    assert result.backend == "GitHub REST API (public)"
    assert result.metadata["topics"] == "a, b"
    assert result.body == "# CPython\nhello"


def test_github_repo_read_via_gh_cli():
    routes = _repo_routes()
    calls = []

    def run(argv, timeout=None, env=None):
        calls.append(argv)
        assert env and env.get("GH_TELEMETRY") == "false"
        return upstream.CommandResult(0, json.dumps(routes[argv[-1]]), "")

    with patch("weblens.channels._http.get_json") as public:
        result = gh.read("https://github.com/python/cpython", run=run, use_gh=True)
    public.assert_not_called()
    assert calls[0][:2] == ["gh", "api"]
    assert result.backend == "gh CLI"


def test_github_gh_failure_falls_back_to_public_api():
    routes = _repo_routes()

    def run(argv, timeout=None, env=None):
        return upstream.CommandResult(1, "", "HTTP 401: Bad credentials")

    with patch("weblens.channels._http.get_json",
               side_effect=lambda url, **kw: routes[url.removeprefix("https://api.github.com/")]):
        result = gh.read("https://github.com/python/cpython", run=run, use_gh=True)
    assert result.backend == "GitHub REST API (public)"
    assert "fell back" in result.notes[0]


def test_github_rate_limit_is_actionable():
    headers = email.message.Message()
    headers["X-RateLimit-Remaining"] = "0"
    err = urllib.error.HTTPError("https://api.github.com/x", 403, "rate", headers, io.BytesIO(b""))
    with patch("weblens.channels._http.get_json", side_effect=err):
        with pytest.raises(WebLensError) as info:
            gh.read("https://github.com/python/cpython", use_gh=False)
    assert "rate limit" in info.value.one_line()
    assert "gh auth login" in info.value.one_line()


def test_github_pull_request_read():
    routes = {
        "repos/a/b/issues/7": {"title": "Fix", "state": "closed", "user": {"login": "u"},
                               "comments": 1, "labels": [{"name": "bug"}], "body": "desc",
                               "pull_request": {}, "html_url": "https://github.com/a/b/pull/7"},
        "repos/a/b/pulls/7": {"merged": True, "head": {"label": "a:f"}, "base": {"label": "a:main"},
                              "additions": 3, "deletions": 1, "changed_files": 2},
        "repos/a/b/issues/7/comments?per_page=30": [{"user": {"login": "r"}, "created_at": "d", "body": "lgtm"}],
    }
    with patch("weblens.channels._http.get_json",
               side_effect=lambda url, **kw: routes[url.removeprefix("https://api.github.com/")]):
        result = gh.read("https://github.com/a/b/pull/7", use_gh=False)
    assert result.title == "Fix (#7)"
    assert result.metadata["type"] == "pull request"
    assert result.metadata["merged"] is True
    assert result.metadata["labels"] == "bug"
    assert "### r · d\n\nlgtm" in result.body


def test_gh_ready_requires_binary_and_credentials(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch.object(upstream, "which", return_value=None):
        assert gh.gh_ready() is False
    with patch.object(upstream, "which", return_value="/bin/gh"), \
            patch.object(gh, "_saved_github_host_configured", return_value=False):
        assert gh.gh_ready() is False
        monkeypatch.setenv("GH_TOKEN", "x")
        assert gh.gh_ready() is True


# --------------------------------------------------------------------------- #
# upstream.run safety
# --------------------------------------------------------------------------- #


def test_upstream_run_uses_argv_without_shell():
    completed = MagicMock(returncode=0, stdout="out", stderr="")
    with patch.object(upstream, "which", return_value="/usr/bin/tool"), \
            patch("subprocess.run", return_value=completed) as sp:
        result = upstream.run(["tool", "a b; rm -rf /"])
    args, kwargs = sp.call_args
    assert args[0] == ["/usr/bin/tool", "a b; rm -rf /"]
    assert kwargs["shell"] is False
    assert result.ok and result.stdout == "out"


def test_upstream_run_missing_tool():
    with patch.object(upstream, "which", return_value=None), pytest.raises(ToolMissingError) as info:
        upstream.run(["gh", "api", "x"])
    assert info.value.one_line() == "gh not installed: brew install gh (or see https://cli.github.com), then `gh auth login`"


def test_upstream_run_timeout():
    import subprocess

    with patch.object(upstream, "which", return_value="/usr/bin/tool"), \
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("tool", 5)):
        with pytest.raises(WebLensError, match="timed out"):
            upstream.run(["tool"], timeout=5)


@pytest.mark.parametrize(
    "url",
    [
        "https://news.ycombinator.com/news",
        "https://en.wikipedia.org/w/index.php?search=x",
        "https://arxiv.org/list/cs.AI/recent",
        "https://stackoverflow.com/tags/python",
        "https://github.com/python",
        "https://gist.github.com/user/abc",
        "https://www.youtube.com/@jawed",
        "https://www.youtube.com/results?search_query=x",
    ],
)
def test_unsupported_page_shapes_on_native_sites_fall_back_to_jina(url):
    fake = ReadResult(title="t", url=url, source="web", body="b")
    with patch.object(rd, "_read_web", return_value=fake):
        result = rd.read_url(url)
    assert "no native reader" in result.notes[0]


def test_weblens_library_read_and_search_delegate():
    from weblens.core import WebLens
    from weblens.unified.models import SearchResponse

    lens = WebLens(config=MagicMock())
    fake = ReadResult(title="t", url="u", source="web")
    with patch("weblens.unified.read.read_url", return_value=fake) as read_url:
        assert lens.read("https://example.com", max_chars=5) is fake
    assert read_url.call_args.kwargs["max_chars"] == 5
    resp = SearchResponse(query="q", source="web")
    with patch("weblens.unified.search.search", return_value=resp) as search:
        assert lens.search("q", source="hackernews", limit=3) is resp
    assert search.call_args.kwargs["source"] == "hackernews"


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX executable bit")
def test_upstream_which_falls_back_to_interpreter_bin_dir(tmp_path, monkeypatch):
    tool = tmp_path / "yt-dlp"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr("sys.executable", str(tmp_path / "python"))
    assert upstream.which("yt-dlp") == str(tool)
    assert upstream.which("definitely-not-a-tool") is None
