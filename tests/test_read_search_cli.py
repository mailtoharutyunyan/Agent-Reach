"""CLI wiring for `weblens read` / `weblens search`: parsing, output, exit codes."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from weblens.cli import main
from weblens.unified.errors import ToolMissingError, UsageError
from weblens.unified.models import ReadResult, SearchResponse, SearchResult


def _main(argv):
    with patch("sys.argv", ["weblens", *argv]):
        main()


def _exit_code(argv) -> int:
    with pytest.raises(SystemExit) as info:
        _main(argv)
    return info.value.code


# --- parsing ----------------------------------------------------------------------

def test_read_parses_flags_and_dispatches():
    with patch("weblens.cli._cmd_read") as cmd:
        _main(["read", "https://example.com", "--json", "--max-chars", "100"])
    args = cmd.call_args.args[0]
    assert (args.url, args.json, args.max_chars) == ("https://example.com", True, 100)


def test_search_defaults():
    with patch("weblens.cli._cmd_search") as cmd:
        _main(["search", "rust async"])
    args = cmd.call_args.args[0]
    assert (args.query, args.source, args.limit, args.json) == ("rust async", "web", 10, False)


def test_search_short_flags():
    with patch("weblens.cli._cmd_search") as cmd:
        _main(["search", "q", "-s", "all", "-n", "3", "--json"])
    args = cmd.call_args.args[0]
    assert (args.source, args.limit, args.json) == ("all", 3, True)


@pytest.mark.parametrize(
    "argv",
    [
        ["read"],
        ["read", "https://example.com", "--max-chars", "0"],
        ["read", "https://example.com", "--max-chars", "abc"],
        ["search"],
        ["search", "q", "--source", "bing"],
        ["search", "q", "--limit", "0"],
        ["search", "q", "--limit", "51"],
    ],
)
def test_bad_usage_exits_2(argv, capsys):
    assert _exit_code(argv) == 2


# --- output -------------------------------------------------------------------------

def test_read_text_output(capsys):
    result = ReadResult(title="Example", url="https://example.com", source="web",
                        backend="Jina Reader", body="Hello", metadata={"published": "Mon"},
                        notes=["a note"])
    with patch("weblens.unified.read.read_url", return_value=result) as read_url:
        _main(["read", "https://example.com", "--max-chars", "50"])
    assert read_url.call_args.kwargs["max_chars"] == 50
    out = capsys.readouterr().out
    assert out.startswith("# Example\n")
    assert "- source: web via Jina Reader" in out
    assert "- published: Mon" in out
    assert "- note: a note" in out
    assert out.rstrip().endswith("Hello")


def test_read_json_output(capsys):
    result = ReadResult(title="Example", url="https://example.com", source="web", body="Hello")
    with patch("weblens.unified.read.read_url", return_value=result):
        _main(["read", "https://example.com", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["title"] == "Example" and data["body"] == "Hello" and data["truncated"] is False


def test_search_text_and_json_output(capsys):
    response = SearchResponse(
        query="rust", source="all", sources=["web", "hackernews"],
        results=[SearchResult("A", "https://a", "web", "snip", {"author": "x"})],
        errors={"hackernews": "hackernews search failed: timed out"},
    )
    with patch("weblens.unified.search.search", return_value=response):
        _main(["search", "rust", "--source", "all"])
    out = capsys.readouterr().out
    assert "## web (1)" in out and "1. A" in out and "author: x" in out
    assert "## hackernews (0)" in out and "error: hackernews search failed" in out

    with patch("weblens.unified.search.search", return_value=response):
        _main(["search", "rust", "--source", "all", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["groups"]["web"][0]["title"] == "A"
    assert data["errors"]["hackernews"].endswith("timed out")


# --- errors -------------------------------------------------------------------------

def test_runtime_error_is_one_line_exit_1(capsys):
    with patch("weblens.unified.read.read_url", side_effect=ToolMissingError("yt-dlp")):
        assert _exit_code(["read", "https://youtu.be/x"]) == 1
    err = capsys.readouterr().err
    assert err.strip() == 'error: yt-dlp not installed: python -m pip install -U "yt-dlp[default]"'
    assert "Traceback" not in err


def test_usage_error_from_core_exits_2(capsys):
    with patch("weblens.unified.read.read_url", side_effect=UsageError("invalid URL 'x'", "pass a public http(s) URL")):
        assert _exit_code(["read", "x"]) == 2
    assert capsys.readouterr().err.startswith("error: invalid URL")


def test_unexpected_exception_is_summarised_without_traceback(capsys):
    with patch("weblens.unified.search.search", side_effect=RuntimeError("kaboom")):
        assert _exit_code(["search", "q"]) == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "kaboom" in err and "--debug" in err


def test_debug_flag_shows_traceback():
    with patch("weblens.unified.search.search", side_effect=RuntimeError("kaboom")):
        with pytest.raises(RuntimeError, match="kaboom"):
            _main(["--debug", "search", "q"])


@pytest.mark.parametrize(
    "argv",
    [
        ["read", "https://example.com", "--debug"],
        ["read", "--debug", "https://example.com"],
        ["--debug", "read", "https://example.com"],
        ["search", "q", "--debug"],
    ],
)
def test_debug_flag_works_before_or_after_the_subcommand(argv):
    with patch("weblens.unified.read.read_url", side_effect=RuntimeError("kaboom")), \
            patch("weblens.unified.search.search", side_effect=RuntimeError("kaboom")):
        with pytest.raises(RuntimeError, match="kaboom"):
            _main(argv)


@pytest.mark.parametrize(
    ("argv", "debug", "verbose"),
    [
        (["read", "https://e.com"], False, False),
        (["--debug", "read", "https://e.com"], True, False),
        (["read", "https://e.com", "--debug"], True, False),
        (["-v", "read", "https://e.com"], False, True),
        (["read", "https://e.com", "-v"], False, True),
        (["doctor", "--debug", "--json"], True, False),
    ],
)
def test_global_flags_parse_in_either_position(argv, debug, verbose):
    # A subcommand that was not given a flag must not reset one given before it.
    with patch("weblens.cli._run_command") as run, patch("weblens.cli._cmd_doctor") as doctor, \
            patch("weblens.cli._configure_logging") as logging:
        _main(argv)
    args = (run.call_args or doctor.call_args).args[1 if run.called else 0]
    assert (args.debug, args.verbose) == (debug, verbose)
    logging.assert_called_once_with(debug or verbose)


def test_error_messages_scrub_credentials(capsys):
    with patch("weblens.unified.read.read_url",
               side_effect=RuntimeError("GET https://u:secret@h.example/x?token=abc failed")):
        _exit_code(["read", "https://example.com"])
    err = capsys.readouterr().err
    assert "secret" not in err and "abc" not in err


def test_real_read_invalid_url_end_to_end(capsys):
    assert _exit_code(["read", "http://localhost/admin"]) == 2
    assert "invalid URL" in capsys.readouterr().err
