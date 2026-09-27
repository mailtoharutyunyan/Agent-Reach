"""Retry/backoff in the shared HTTP helper (no network; sleeper injected)."""

from __future__ import annotations

import email.message
import io
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from weblens.channels import _http
from weblens.channels.web import WebChannel


def _http_error(code: int, retry_after: str | None = None, body: bytes = b"") -> urllib.error.HTTPError:
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://api.example/x", code, "err", headers, io.BytesIO(body))


class _Resp:
    def __init__(self, body: bytes = b'{"ok": true}', status: int = 200) -> None:
        self._body = body
        self.status = status
        self.headers: dict[str, str] = {}

    def read(self, n: int = -1) -> bytes:
        # Stateful like a real response: bodies are now read in chunks until EOF.
        chunk, self._body = (self._body, b"") if n is None or n < 0 else (self._body[:n], self._body[n:])
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --- Retry-After parsing / classification ---------------------------------

def test_retry_after_seconds_parses_delta_and_date():
    assert _http.retry_after_seconds({"Retry-After": "7"}) == 7.0
    date = "Wed, 21 Oct 2015 07:28:10 GMT"
    now = 1445412480.0  # 10 s before that date
    assert _http.retry_after_seconds({"Retry-After": date}, now=now) == pytest.approx(10.0)
    assert _http.retry_after_seconds({"Retry-After": "soon"}) is None
    assert _http.retry_after_seconds({}) is None
    assert _http.retry_after_seconds(None) is None


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_http_error(429), True),
        (_http_error(502), True),
        (_http_error(503), True),
        (_http_error(504), True),
        (_http_error(500), False),
        (_http_error(404), False),
        (urllib.error.URLError(TimeoutError("timed out")), True),
        (urllib.error.URLError(ConnectionResetError()), True),
        (urllib.error.URLError("connection refused"), False),
        (urllib.error.URLError(socket.gaierror("no dns")), False),
        (TimeoutError(), True),
        (ConnectionResetError(), True),
        (ValueError("bad"), False),
    ],
)
def test_is_transient(exc, expected):
    assert _http.is_transient(exc) is expected


# --- call_with_retries ------------------------------------------------------

def test_retries_then_succeeds_with_exponential_backoff_and_jitter():
    calls = []
    delays: list[float] = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise _http_error(503)
        return "ok"

    assert _http.call_with_retries(fn, sleeper=delays.append, rng=lambda: 0.5) == "ok"
    assert len(calls) == 3
    assert delays == [1.5, 2.5]  # base*2^(n-1) + 0.5*base jitter


def test_gives_up_after_max_attempts():
    delays: list[float] = []
    fn = MagicMock(side_effect=_http_error(502))
    with pytest.raises(urllib.error.HTTPError):
        _http.call_with_retries(fn, sleeper=delays.append, rng=lambda: 0.0)
    assert fn.call_count == 3
    assert delays == [1.0, 2.0]


def test_non_retryable_error_raises_immediately():
    delays: list[float] = []
    fn = MagicMock(side_effect=_http_error(404))
    with pytest.raises(urllib.error.HTTPError):
        _http.call_with_retries(fn, sleeper=delays.append)
    assert fn.call_count == 1
    assert delays == []


def test_retry_after_is_honored():
    delays: list[float] = []
    fn = MagicMock(side_effect=[_http_error(429, retry_after="4"), "ok"])
    assert _http.call_with_retries(fn, sleeper=delays.append) == "ok"
    assert delays == [4.0]


def test_retry_after_beyond_total_budget_is_not_waited():
    delays: list[float] = []
    fn = MagicMock(side_effect=_http_error(429, retry_after="120"))
    with pytest.raises(urllib.error.HTTPError):
        _http.call_with_retries(fn, sleeper=delays.append)
    assert fn.call_count == 1
    assert delays == []


def test_total_wait_is_bounded():
    delays: list[float] = []
    fn = MagicMock(side_effect=_http_error(503, retry_after="15"))
    with pytest.raises(urllib.error.HTTPError):
        _http.call_with_retries(fn, sleeper=delays.append, max_attempts=5)
    assert sum(delays) <= _http.MAX_TOTAL_WAIT
    assert delays == [15.0]


def test_module_sleeper_is_used_by_default(no_retry_sleep):
    fn = MagicMock(side_effect=[TimeoutError(), "ok"])
    assert _http.call_with_retries(fn, rng=lambda: 0.0) == "ok"
    assert no_retry_sleep == [1.0]


# --- get_bytes / get_json integration --------------------------------------

def test_get_json_retries_transient_status(no_retry_sleep):
    responses = [_http_error(503), _http_error(429, retry_after="1"), _Resp()]

    def fake_open(req, timeout, allowed):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    with patch.object(_http, "_open", fake_open):
        assert _http.get_json("https://api.example/x", allowed_hosts={"api.example"}) == {"ok": True}
    assert len(no_retry_sleep) == 2
    assert no_retry_sleep[1] == 1.0


def test_get_bytes_error_body_after_retries_exhausted():
    def fake_open(req, timeout, allowed):
        raise _http_error(503, body=b'{"error": "down"}')

    with patch.object(_http, "_open", fake_open) as _:
        status, body = _http.get_bytes(
            "https://api.example/x", allowed_hosts={"api.example"}, error_body=True
        )
    assert status == 503
    assert body == b'{"error": "down"}'


# --- fetch_public (arbitrary hosts, e.g. feeds) ------------------------------

def test_fetch_public_rejects_hosts_resolving_to_private_addresses():
    with patch.object(socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 443))]), \
            patch.object(_http, "_open_public") as opened, pytest.raises(ValueError, match="public"):
        _http.fetch_public("https://feeds.example.com/rss")
    opened.assert_not_called()


def test_fetch_public_rejects_localhost_without_dns():
    with patch.object(socket, "getaddrinfo") as resolver, pytest.raises(ValueError):
        _http.fetch_public("http://localhost/feed")
    resolver.assert_not_called()


def test_fetch_public_returns_final_url_and_body():
    resp = _Resp(b"<rss/>")
    resp.url = "https://feeds.example.com/final"  # type: ignore[attr-defined]
    with patch.object(socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), \
            patch.object(_http, "_open_public", return_value=resp):
        assert _http.fetch_public("https://feeds.example.com/rss") == (
            "https://feeds.example.com/final", b"<rss/>")


# --- Jina (web.py) uses the same retry ------------------------------------------

def test_web_read_retries_jina_rate_limit(no_retry_sleep):
    ok = MagicMock()
    ok.__enter__.return_value.read.return_value = b"Title: X\n\nMarkdown Content:\nhello"
    with patch("urllib.request.urlopen", side_effect=[_http_error(429, retry_after="2"), ok]) as op:
        out = WebChannel().read("https://example.com")
    assert "hello" in out
    assert op.call_count == 2
    assert no_retry_sleep == [2.0]
