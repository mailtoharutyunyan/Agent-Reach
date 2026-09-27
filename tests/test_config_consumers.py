"""Saved config is actually consumed: YouTube cookie browser, GitHub token,
feed sniffing for feed-less URLs, install help text (all mocked, no network)."""

from __future__ import annotations

import gzip
import io
import json
import sys
from email.message import Message
from unittest.mock import patch

import pytest

import weblens.cli as cli
from weblens.channels import _http
from weblens.commands import install as install_cmd
from weblens.config import Config
from weblens.unified import github as gh
from weblens.unified import read as rd
from weblens.unified import upstream
from weblens.unified import youtube as yt
from weblens.unified.errors import WebLensError
from weblens.unified.models import ReadResult


class _Cfg:
    def __init__(self, **data):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)


# --------------------------------------------------------------------------- #
# YouTube cookies
# --------------------------------------------------------------------------- #

_INFO = {"title": "T", "webpage_url": "https://www.youtube.com/watch?v=x",
         "language": "en", "subtitles": {"en": [{"ext": "vtt"}]}, "automatic_captions": {}}


class _Recorder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout=None, env=None):
        self.calls.append(list(argv))
        if "-J" in argv and any(a.startswith("ytsearch") for a in argv):
            return upstream.CommandResult(0, json.dumps({"entries": [{"id": "a", "title": "A"}]}), "")
        if "-J" in argv:
            return upstream.CommandResult(0, json.dumps(_INFO), "")
        return upstream.CommandResult(0, "", "")  # no subtitle file written


@pytest.mark.parametrize(
    ("value", "expected"),
    [("chrome", "chrome"), (" Firefox ", "firefox"), ("whale", "whale"),
     ("chrome:Profile 1", "chrome:Profile 1")],
)
def test_parse_cookie_source_accepts_supported_browsers(value, expected):
    assert yt.parse_cookie_source(value) == expected


@pytest.mark.parametrize("value", ["", "netscape", "--exec", "chrome:", "chrome:a\nb"])
def test_parse_cookie_source_rejects_everything_else(value):
    with pytest.raises(ValueError):
        yt.parse_cookie_source(value)


def test_youtube_read_passes_cookies_from_browser_to_every_ytdlp_call():
    run = _Recorder()
    yt.read("https://youtu.be/x", run=run, config=_Cfg(youtube_cookies_from="firefox"))
    assert len(run.calls) == 2
    for argv in run.calls:
        assert argv[argv.index("--cookies-from-browser") + 1] == "firefox"
    # the source URL / info json always stays last
    assert run.calls[0][-1] == "https://youtu.be/x"


def test_youtube_search_passes_cookies_and_omits_them_when_unset():
    run = _Recorder()
    yt.search("q", 3, run=run, config=_Cfg(youtube_cookies_from="safari"))
    assert run.calls[0][run.calls[0].index("--cookies-from-browser") + 1] == "safari"
    assert run.calls[0][-1] == "ytsearch3:q"
    run2 = _Recorder()
    yt.search("q", 3, run=run2, config=_Cfg())
    assert "--cookies-from-browser" not in run2.calls[0]


def test_youtube_reads_saved_config_when_none_passed():
    Config().set("youtube_cookies_from", "brave")
    run = _Recorder()
    yt.read("https://youtu.be/x", run=run)
    assert "brave" in run.calls[0]


def test_youtube_invalid_saved_browser_is_actionable():
    with pytest.raises(WebLensError) as info:
        yt.read("https://youtu.be/x", run=_Recorder(), config=_Cfg(youtube_cookies_from="lynx"))
    assert "weblens configure youtube-cookies <browser>" in info.value.one_line()


def test_youtube_sign_in_hint_depends_on_cookie_config():
    def run(argv, timeout=None, env=None):
        return upstream.CommandResult(1, "", "ERROR: Sign in to confirm you're not a bot")

    with pytest.raises(WebLensError) as unset:
        yt.read("https://youtu.be/x", run=run, config=_Cfg())
    assert "weblens configure youtube-cookies <browser>" in unset.value.one_line()
    with pytest.raises(WebLensError) as used:
        yt.read("https://youtu.be/x", run=run, config=_Cfg(youtube_cookies_from="chrome"))
    assert "cookies from chrome were used" in used.value.one_line()


def test_unified_read_and_search_forward_config_to_youtube():
    from weblens.unified import search as sr

    cfg = _Cfg(youtube_cookies_from="edge")
    with patch.object(yt, "read", return_value=ReadResult(title="t", url="u", source="youtube")) as rd_yt:
        rd.read_url("https://www.youtube.com/watch?v=abc", config=cfg)
    assert rd_yt.call_args.kwargs["config"] is cfg
    with patch.object(yt, "search", return_value=[]) as sr_yt:
        sr.search("q", source="youtube", limit=2, config=cfg)
    assert sr_yt.call_args.kwargs["config"] is cfg


def _configure(monkeypatch, *argv):
    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(sys, "argv", ["weblens", "configure", *argv])
    cli.main()


def test_configure_youtube_cookies_validates_and_saves(monkeypatch, capsys):
    _configure(monkeypatch, "youtube-cookies", "Chrome")
    assert Config().data["youtube_cookies_from"] == "chrome"
    assert "--cookies-from-browser chrome" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        _configure(monkeypatch, "youtube-cookies", "netscape")
    assert exc.value.code == 2
    assert Config().data["youtube_cookies_from"] == "chrome"


# --------------------------------------------------------------------------- #
# GitHub token
# --------------------------------------------------------------------------- #

_TOKEN = "ghp_configSecret123"


def _capture_get_json(seen):
    def fake(url, allowed_hosts, **kw):
        seen.append(kw.get("extra_headers"))
        path = url.removeprefix("https://api.github.com/")
        if path.endswith("/readme"):
            return {"encoding": "base64", "content": ""}
        return {"full_name": "a/b"}

    return fake


@pytest.fixture
def no_env_token(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


def test_github_rest_uses_saved_config_token(no_env_token):
    seen: list = []
    with patch("weblens.channels._http.get_json", side_effect=_capture_get_json(seen)):
        result = gh.read("https://github.com/a/b", use_gh=False, config=_Cfg(github_token=_TOKEN))
    assert seen and all(h == {"Authorization": f"Bearer {_TOKEN}"} for h in seen)
    assert result.backend == "GitHub REST API (token)"
    assert _TOKEN not in json.dumps(result.to_dict() if hasattr(result, "to_dict") else vars(result),
                                    default=str)


def test_github_rest_reads_saved_config_when_none_passed(no_env_token):
    Config().set("github_token", _TOKEN)
    seen: list = []
    with patch("weblens.channels._http.get_json", side_effect=_capture_get_json(seen)):
        gh.search("x", 1, use_gh=False)
    assert seen == [{"Authorization": f"Bearer {_TOKEN}"}]


def test_github_env_token_beats_config(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fromEnv")
    seen: list = []
    with patch("weblens.channels._http.get_json", side_effect=_capture_get_json(seen)):
        gh.read("https://github.com/a/b", use_gh=False, config=_Cfg(github_token=_TOKEN))
    assert seen[0] == {"Authorization": "Bearer ghp_fromEnv"}


def test_github_without_token_stays_unauthenticated(no_env_token):
    seen: list = []
    with patch("weblens.channels._http.get_json", side_effect=_capture_get_json(seen)):
        result = gh.read("https://github.com/a/b", use_gh=False, config=_Cfg())
    assert seen[0] is None
    assert result.backend == "GitHub REST API (public)"


def test_github_malformed_token_is_ignored_without_echoing_it(no_env_token):
    bad = "ghp_x\r\nX-Injected: 1"
    seen: list = []
    with patch("weblens.channels._http.get_json", side_effect=_capture_get_json(seen)):
        result = gh.read("https://github.com/a/b", use_gh=False, config=_Cfg(github_token=bad))
    assert seen[0] is None
    assert any("github_token" in n for n in result.notes)
    assert all(bad not in n for n in result.notes)


def test_github_rejected_token_error_does_not_leak_it(no_env_token):
    import urllib.error

    err = urllib.error.HTTPError("https://api.github.com/repos/a/b", 401, "Bad credentials",
                                 Message(), io.BytesIO(b""))
    with patch("weblens.channels._http.get_json", side_effect=err), pytest.raises(WebLensError) as info:
        gh.read("https://github.com/a/b", use_gh=False, config=_Cfg(github_token=_TOKEN))
    assert "401" in info.value.one_line()
    assert _TOKEN not in info.value.one_line()


def test_get_bytes_sends_extra_headers_to_allowlisted_host_only():
    seen = {}

    class _Resp(io.BytesIO):
        status = 200
        headers = Message()

    def fake_open(req, timeout, allowed):
        seen["auth"] = req.get_header("Authorization")
        return _Resp(b"{}")

    with patch.object(_http, "_open", fake_open):
        _http.get_bytes("https://api.github.com/x", allowed_hosts={"api.github.com"},
                        extra_headers={"Authorization": "Bearer t"})
    assert seen["auth"] == "Bearer t"
    with patch.object(_http, "_open") as opened, pytest.raises(ValueError):
        _http.get_bytes("https://evil.test/x", allowed_hosts={"api.github.com"},
                        extra_headers={"Authorization": "Bearer t"})
    opened.assert_not_called()


def test_doctor_does_not_print_saved_github_token(capsys, monkeypatch, no_env_token):
    Config().set("github_token", _TOKEN)
    from weblens.channels.github import GitHubChannel

    with patch("weblens.channels.github.probe_command") as probe:
        probe.return_value.status = "ok"
        probe.return_value.ok = True
        status, message = GitHubChannel().check(Config(read_only=True))
    assert _TOKEN not in message
    assert _TOKEN not in json.dumps(Config(read_only=True).to_dict())


# --------------------------------------------------------------------------- #
# Feed sniffing
# --------------------------------------------------------------------------- #

_FEED = (b'<?xml version="1.0" encoding="UTF-8"?>\n<?xml-stylesheet href="s.xsl"?>\n'
         b'<rss version="2.0"><channel><title>Hacker News: Front Page</title>'
         b"<link>https://news.ycombinator.com/</link>"
         b"<item><title>Story</title><link>https://example.com/s</link></item>"
         b"</channel></rss>")


@pytest.mark.parametrize(
    ("ctype", "head", "expected"),
    [
        ("application/rss+xml; charset=utf-8", b"", True),
        ("application/atom+xml", b"", True),
        ("text/xml", _FEED, True),
        ("application/xml", b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">', True),
        ("", b"\xef\xbb\xbf  <rss version='2.0'>", True),
        ("application/xml", b'<?xml version="1.0"?><urlset>', False),  # sitemap
        ("text/html", _FEED, False),
        ("text/html", b"<!doctype html><html>", False),
        ("application/json", b'{"rss": 1}', False),
    ],
)
def test_looks_like_feed(ctype, head, expected):
    assert rd.looks_like_feed(ctype, head) is expected


def test_unclaimed_feed_url_is_parsed_as_feed_without_jina():
    with patch.object(rd, "_sniff_feed", return_value=("https://hnrss.org/frontpage", _FEED)), \
            patch.object(rd, "_read_web") as web:
        result = rd.read_url("https://hnrss.org/frontpage")
    web.assert_not_called()
    assert result.source == "rss"
    assert result.title == "Hacker News: Front Page"
    assert "### Story" in result.body


def test_unclaimed_non_feed_falls_back_to_jina():
    fake = ReadResult(title="page", url="u", source="web", body="b")
    with patch.object(rd, "_sniff_feed", return_value=None), \
            patch.object(rd, "_read_web", return_value=fake) as web:
        result = rd.read_url("https://example.com/page")
    web.assert_called_once()
    assert result.source == "web"


def test_sniff_skips_obvious_non_feed_extensions(no_feed_sniff):
    with patch.object(_http, "fetch_public_if") as fetch:
        assert no_feed_sniff("https://example.com/a.html") is None
    fetch.assert_not_called()


def test_sniff_swallows_network_errors(no_feed_sniff):
    with patch.object(_http, "fetch_public_if", side_effect=OSError("down")):
        assert no_feed_sniff("https://example.com/x") is None


class _StreamResp(io.BytesIO):
    def __init__(self, body: bytes, ctype: str = "", encoding: str = ""):
        super().__init__(body)
        self.url = "https://feeds.example/final"
        self.headers = Message()
        if ctype:
            self.headers["Content-Type"] = ctype
        if encoding:
            self.headers["Content-Encoding"] = encoding
        self.reads: list[int] = []

    def read(self, size=-1):
        self.reads.append(size)
        return super().read(size)

    def read1(self, size=-1):  # _http streams bodies with read1 (one recv per call)
        self.reads.append(size)
        return super().read1(size)


def _public_ok(url):
    return url


def test_fetch_public_if_reads_feed_from_the_same_response():
    body = _FEED + b" " * 20000
    resp = _StreamResp(body, "text/xml")
    with patch.object(_http, "_check_public_host", _public_ok), \
            patch.object(_http, "_open_public", return_value=resp) as opened:
        got = _http.fetch_public_if("https://feeds.example/x", rd.looks_like_feed, sniff_bytes=256)
    assert opened.call_count == 1
    assert got == ("https://feeds.example/final", body)


def test_fetch_public_if_stops_after_prefix_for_non_feeds():
    resp = _StreamResp(b"<!doctype html>" + b"x" * 100000, "text/html")
    with patch.object(_http, "_check_public_host", _public_ok), \
            patch.object(_http, "_open_public", return_value=resp):
        assert _http.fetch_public_if("https://e.example/", rd.looks_like_feed, sniff_bytes=64) is None
    assert resp.reads == [64]


def test_fetch_public_if_handles_gzip_and_size_cap():
    resp = _StreamResp(gzip.compress(_FEED), "", "gzip")
    with patch.object(_http, "_check_public_host", _public_ok), \
            patch.object(_http, "_open_public", return_value=resp):
        assert _http.fetch_public_if("https://f.example/", rd.looks_like_feed)[1] == _FEED
    big = _StreamResp(_FEED + b" " * 5000, "application/rss+xml")
    with patch.object(_http, "_check_public_host", _public_ok), \
            patch.object(_http, "_open_public", return_value=big), pytest.raises(ValueError):
        _http.fetch_public_if("https://f.example/", rd.looks_like_feed, max_bytes=1000)


def test_fetch_public_if_rejects_non_public_hosts_before_opening():
    with patch.object(_http, "_open_public") as opened, pytest.raises(ValueError):
        _http.fetch_public_if("http://127.0.0.1/feed", rd.looks_like_feed)
    opened.assert_not_called()


# --------------------------------------------------------------------------- #
# install --channels help
# --------------------------------------------------------------------------- #


def test_install_channels_help_lists_every_accepted_channel(monkeypatch, capsys):
    from argparse import Namespace

    with pytest.raises(SystemExit):
        install_cmd._cmd_install(Namespace(env="auto", proxy="", system=False, safe=True,
                                           dry_run=True, channels="__bogus__"))
    err = capsys.readouterr().err
    accepted = {c.strip() for c in err.split("Supported:", 1)[1].split(",")}
    assert "opencli" in accepted

    monkeypatch.setattr(sys, "argv", ["weblens", "install", "--help"])
    monkeypatch.setenv("COLUMNS", "400")
    with pytest.raises(SystemExit):
        cli.main()
    help_text = " ".join(capsys.readouterr().out.split())
    listed = help_text.split("to install (", 1)[1].split(")", 1)[0]
    assert {c.strip() for c in listed.split(",")} == accepted
