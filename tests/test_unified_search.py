"""`weblens search` sources, fan-out and fallbacks (no network)."""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import patch

import pytest

from weblens.channels import get_channel
from weblens.unified import search as sr
from weblens.unified import upstream
from weblens.unified import youtube as yt
from weblens.unified.errors import ToolMissingError, UsageError, WebLensError
from weblens.unified.models import SearchResult

_EXA_TEXT = (
    "Title: Rust Book async\nURL: https://doc.rust-lang.org/book/ch17.html\n"
    "Published: N/A\nAuthor: N/A\nHighlights:\nRust Book async\n\n# Fundamentals\nMany operations take a while.\n"
    "\n---\n"
    "Title: Async book\nURL: https://rust-lang.github.io/async-book/\nPublished: 2024-01-01\n"
    "Author: Rust team\nHighlights:\nThis book is a guide."
)


def _exa_proc(text=_EXA_TEXT):
    return upstream.CommandResult(0, json.dumps({"content": [{"type": "text", "text": text}]}), "")


def _r(source, title="t"):
    return SearchResult(title=title, url=f"https://{source}.example/{title}", source=source)


# --- input validation ---------------------------------------------------------

@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"query": "  "}, "empty"),
        ({"query": "-rf"}, "must not start"),
        ({"query": "x", "source": "bing"}, "unknown source"),
        ({"query": "x", "limit": 0}, "--limit"),
        ({"query": "x", "limit": 51}, "--limit"),
    ],
)
def test_search_usage_errors(kwargs, match):
    with pytest.raises(UsageError, match=match) as info:
        sr.search(**kwargs)
    assert info.value.exit_code == 2


# --- Exa / web ------------------------------------------------------------------

def test_parse_exa_text():
    results = sr.parse_exa_text(_EXA_TEXT)
    assert [r.url for r in results] == [
        "https://doc.rust-lang.org/book/ch17.html", "https://rust-lang.github.io/async-book/"]
    assert results[0].snippet == "Fundamentals Many operations take a while."
    assert results[0].extra == {}
    assert results[1].extra == {"published": "2024-01-01", "author": "Rust team"}


def test_exa_search_passes_query_as_json_args_not_shell():
    calls = []

    def run(argv, timeout=None, env=None):
        calls.append(argv)
        return _exa_proc()

    results = sr.exa_search("it's `rm -rf` $(x)", 5, run=run)
    argv = calls[0]
    assert argv[:3] == ["mcporter", "call", "exa.web_search_exa"]
    assert json.loads(argv[argv.index("--args") + 1]) == {"query": "it's `rm -rf` $(x)", "numResults": 5}
    assert len(results) == 2


def test_web_search_uses_exa():
    with patch.object(upstream, "run", return_value=_exa_proc()):
        response = sr.search("rust async")
    assert response.source == "web"
    assert all(r.source == "web" for r in response.results)
    assert response.notes == []


def test_web_search_falls_back_to_hn_and_wikipedia_when_mcporter_missing():
    with patch.object(upstream, "run", side_effect=ToolMissingError("mcporter")), \
            patch.object(sr, "_search_hackernews", return_value=([_r("hackernews")], [])), \
            patch.object(sr, "_search_wikipedia", return_value=([_r("wikipedia")], [])):
        response = sr.search("rust async")
    assert {r.source for r in response.results} == {"hackernews", "wikipedia"}
    assert "fell back to hackernews + wikipedia" in response.notes[0]
    assert "mcporter not installed" in response.notes[0]


def test_web_search_falls_back_when_exa_call_fails():
    bad = upstream.CommandResult(1, "", "Error: server exa not found")
    with patch.object(upstream, "run", return_value=bad), \
            patch.object(sr, "_search_hackernews", return_value=([], [])), \
            patch.object(sr, "_search_wikipedia", side_effect=RuntimeError("boom")):
        response = sr.search("rust")
    assert "fell back" in response.notes[0]
    assert any("wikipedia failed" in n for n in response.notes)


# --- native sources -----------------------------------------------------------------

def test_hackernews_source_shape():
    hits = [{"title": "Why async Rust", "url": "https://a.example", "hn_url": "https://news.ycombinator.com/item?id=1",
             "points": 603, "comments_count": 482, "author": "t", "created_at": "2021-03-10T00:00:00Z", "text": ""}]
    with patch.object(type(get_channel("hackernews")), "search", return_value=hits):
        response = sr.search("rust async", source="hackernews", limit=3)
    r = response.results[0]
    assert (r.title, r.url, r.source) == ("Why async Rust", "https://a.example", "hackernews")
    assert r.extra["points"] == 603 and r.extra["date"] == "2021-03-10"


def test_wikipedia_arxiv_stackoverflow_shapes():
    with patch.object(type(get_channel("wikipedia")), "search",
                      return_value=[{"title": "Async", "url": "u", "snippet": "s", "wordcount": 5}]):
        assert sr.search("x", source="wikipedia").results[0].extra == {"words": 5}
    paper = {"title": "P", "url": "u", "summary": "abs", "authors": ["a", "b", "c", "d"],
             "published": "2021-01-01T00:00:00Z", "primary_category": "cs.PL"}
    with patch.object(type(get_channel("arxiv")), "search", return_value=[paper]):
        r = sr.search("x", source="arxiv").results[0]
        assert r.extra["author"] == "a, b, c et al." and r.extra["date"] == "2021-01-01"
    q = {"title": "Q", "url": "u", "tags": ["rust"], "score": 5, "answer_count": 3,
         "is_answered": True, "author": "x", "creation_date": 1593302400}
    with patch.object(type(get_channel("stackoverflow")), "search", return_value=[q]):
        r = sr.search("x", source="stackoverflow").results[0]
        assert r.snippet == "rust" and r.extra["date"] == "2020-06-28"


def test_youtube_search_uses_ytsearch_prefix():
    calls = []
    payload = {"entries": [{"id": "abc", "title": "Intro to async", "url": "https://www.youtube.com/watch?v=abc",
                            "channel": "Let's Get Rusty", "duration": 837, "view_count": 124800}]}

    def run(argv, timeout=None, env=None):
        calls.append(argv)
        return upstream.CommandResult(0, json.dumps(payload), "")

    results = yt.search("rust async", 3, run=run)
    assert calls[0][-1] == "ytsearch3:rust async"
    assert "--flat-playlist" in calls[0]
    assert results[0].extra == {"channel": "Let's Get Rusty", "duration": "13:57", "views": 124800}


def test_github_search_via_public_api():
    data = {"items": [{"full_name": "tokio-rs/tokio", "html_url": "https://github.com/tokio-rs/tokio",
                       "description": "runtime", "stargazers_count": 30000, "language": "Rust"}]}
    with patch("weblens.unified.github.gh_ready", return_value=False), \
            patch("weblens.channels._http.get_json", return_value=data) as gj:
        response = sr.search("rust async", source="github", limit=5)
    assert "search/repositories?q=rust+async&per_page=5" in gj.call_args.args[0]
    assert response.results[0].extra["stars"] == 30000
    assert "GitHub REST API (public)" in response.notes[0]


def test_v2ex_uses_exa_site_search_or_explains():
    with patch.object(upstream, "run", return_value=_exa_proc()) as run:
        response = sr.search("python", source="v2ex")
    assert json.loads(run.call_args.args[0][4])["query"] == "site:v2ex.com python"
    assert all(r.source == "v2ex" for r in response.results)
    with patch.object(upstream, "run", side_effect=ToolMissingError("mcporter")):
        with pytest.raises(WebLensError, match="V2EX has no public search API"):
            sr.search("python", source="v2ex")


# --- upstream-CLI sources ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("source", "backend", "argv"),
    [
        ("reddit", "OpenCLI", ["opencli", "reddit", "search", "q", "-f", "yaml"]),
        ("reddit", "rdt-cli", ["rdt", "search", "q", "--limit", "5", "--yaml"]),
        ("twitter", "twitter-cli", ["twitter", "search", "q", "-n", "5", "--yaml"]),
        ("twitter", "OpenCLI", ["opencli", "twitter", "search", "q", "-f", "yaml"]),
        ("twitter", "bird CLI (legacy)", None),
    ],
)
def test_upstream_search_argv(source, backend, argv):
    assert sr.upstream_search_argv(source, backend, "q", 5) == argv


def test_results_from_structured_maps_common_keys():
    data = {"posts": [{"title": "Hi", "selftext": "body", "permalink": "/r/rust/comments/1/x",
                       "author": "u", "score": 10, "num_comments": 2}]}
    r = sr.results_from_structured(data, "reddit", 10)[0]
    assert r.url == "https://www.reddit.com/r/rust/comments/1/x"
    assert r.extra == {"author": "u", "score": 10, "comments": 2}
    tweets = [{"text": "hello world", "user": {"screen_name": "jack"}, "url": "https://x.com/jack/status/1"}]
    t = sr.results_from_structured(tweets, "twitter", 10)[0]
    assert (t.title, t.extra["author"]) == ("hello world", "jack")
    assert sr.results_from_structured("plain text", "twitter", 10) == []


def test_reddit_search_runs_active_backend():
    ch = get_channel("reddit")

    def fake_check(self, config=None):
        self.active_backend = "rdt-cli"
        return "ok", ""

    out = upstream.CommandResult(0, "- title: A\n  url: https://www.reddit.com/r/x/1\n", "")
    with patch.object(type(ch), "check", fake_check), patch.object(upstream, "run", return_value=out) as run:
        response = sr.search("q", source="reddit", limit=5)
    assert run.call_args.args[0] == ["rdt", "search", "q", "--limit", "5", "--yaml"]
    assert response.results[0].title == "A"


def test_twitter_search_without_backend_uses_exa_site_search():
    ch = get_channel("twitter")

    def fake_check(self, config=None):
        self.active_backend = None
        return "off", ""

    with patch.object(type(ch), "check", fake_check), patch.object(upstream, "run", return_value=_exa_proc()) as run:
        response = sr.search("q", source="twitter")
    assert json.loads(run.call_args.args[0][4])["query"] == "site:x.com q"
    assert "no working twitter backend" in response.notes[0]


# --- all: parallel fan-out ------------------------------------------------------------------

def test_all_fans_out_in_parallel_and_groups():
    started: list[str] = []
    barrier = threading.Barrier(len(sr.ALL_SOURCES), timeout=5)

    def fake_run_source(name, query, limit, config, *, in_all=False):
        assert in_all is True
        started.append(name)
        barrier.wait()  # deadlocks (-> BrokenBarrierError) unless all run concurrently
        return [_r(name)], [f"{name} note"] if name == "web" else []

    with patch.object(sr, "_run_source", side_effect=fake_run_source):
        response = sr.search("rust", source="all", limit=2)
    assert sorted(started) == sorted(sr.ALL_SOURCES)
    groups = response.grouped()
    assert list(groups) == list(sr.ALL_SOURCES)
    assert all(len(v) == 1 for v in groups.values())
    data = response.to_dict()
    assert set(data["groups"]) == set(sr.ALL_SOURCES)
    assert data["notes"] == ["web note"]


def test_all_reports_per_source_errors_without_failing():
    def fake_run_source(name, query, limit, config, *, in_all=False):
        if name == "arxiv":
            raise TimeoutError()
        return [_r(name)], []

    with patch.object(sr, "_run_source", side_effect=fake_run_source):
        response = sr.search("rust", source="all")
    assert "arxiv" in response.errors and "timed out" in response.errors["arxiv"]
    assert len(response.results) == 4


def test_all_fails_when_every_source_fails():
    with patch.object(sr, "_run_source", side_effect=RuntimeError("down")):
        with pytest.raises(WebLensError, match="all search sources failed"):
            sr.search("rust", source="all")


def test_all_does_not_duplicate_hn_wikipedia_when_exa_missing():
    with patch.object(upstream, "run", side_effect=ToolMissingError("mcporter")), \
            patch.object(sr, "_search_hackernews", return_value=([_r("hackernews")], [])) as hn, \
            patch.object(sr, "_search_wikipedia", return_value=([_r("wikipedia")], [])), \
            patch.object(sr, "_search_stackoverflow", return_value=([], [])), \
            patch.object(sr, "_search_arxiv", return_value=([], [])):
        response = sr.search("rust", source="all")
    assert hn.call_count == 1
    assert "web" in response.errors and "mcporter not installed" in response.errors["web"]


def test_single_source_error_is_raised():
    with patch.object(type(get_channel("hackernews")), "search", side_effect=TimeoutError()):
        with pytest.raises(WebLensError, match="hackernews search failed: timed out"):
            sr.search("x", source="hackernews")


def test_fan_out_is_faster_than_serial():
    def slow(name, query, limit, config, *, in_all=False):
        time.sleep(0.2)
        return [], []

    with patch.object(sr, "_run_source", side_effect=slow):
        start = time.monotonic()
        sr.search("x", source="all")
    assert time.monotonic() - start < 0.2 * len(sr.ALL_SOURCES) * 0.8
