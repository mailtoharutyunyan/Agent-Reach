"""Tests for the shared bounded HTTPS helper used by the public-API channels.

No network: ``_http._open`` is patched to return canned responses.
"""

from __future__ import annotations

import gzip
import io
import socket
import urllib.error
import urllib.request
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from weblens import __version__
from weblens.channels import _http

_HOSTS = frozenset({"api.example.org"})


class _Resp(io.BytesIO):
    def __init__(self, body: bytes, encoding: str = "", status: int = 200):
        super().__init__(body)
        self.status = status
        self.headers = Message()
        if encoding:
            self.headers["Content-Encoding"] = encoding


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.org/x",
        "https://evil.test/x",
        "https://api.example.org.evil.test/x",
        "https://user:pw@api.example.org/x",
        "https://api.example.org:8443/x",
        "ftp://api.example.org/x",
    ],
)
def test_validate_url_rejects_off_allowlist(url):
    with pytest.raises(ValueError):
        _http.validate_url(url, _HOSTS)


def test_validate_url_accepts_allowlisted_https():
    _http.validate_url("https://API.example.org:443/x?q=1", _HOSTS)


def test_get_bytes_sends_versioned_user_agent_and_gzip():
    seen = {}

    def fake_open(req, timeout, allowed):
        seen["ua"] = req.get_header("User-agent")
        seen["enc"] = req.get_header("Accept-encoding")
        seen["timeout"] = timeout
        return _Resp(b"{}")

    with patch.object(_http, "_open", fake_open):
        status, body = _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS, timeout=3)
    assert (status, body) == (200, b"{}")
    assert seen == {"ua": f"weblens/{__version__}", "enc": "gzip", "timeout": 3}


def test_get_bytes_rejects_before_opening():
    with patch.object(_http, "_open") as opened, pytest.raises(ValueError):
        _http.get_bytes("https://evil.test/x", allowed_hosts=_HOSTS)
    opened.assert_not_called()


def test_gzip_body_is_inflated_with_or_without_header():
    payload = gzip.compress(b'{"ok": true}')
    for encoding in ("gzip", ""):
        with patch.object(_http, "_open", return_value=_Resp(payload, encoding)):
            assert _http.get_json("https://api.example.org/x", allowed_hosts=_HOSTS) == {"ok": True}


def test_raw_size_cap():
    with patch.object(_http, "_open", return_value=_Resp(b"x" * 11)), pytest.raises(ValueError):
        _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS, max_bytes=10)


def test_inflated_size_cap_blocks_gzip_bombs():
    bomb = gzip.compress(b"0" * 100_000)
    assert len(bomb) < 1000
    with patch.object(_http, "_open", return_value=_Resp(bomb, "gzip")), pytest.raises(ValueError):
        _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS, max_bytes=1000)


def test_http_error_raises_by_default_and_returns_body_on_request():
    def fake_open(req, timeout, allowed):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad", Message(), io.BytesIO(gzip.compress(b'{"error_id": 400}'))
        )

    with patch.object(_http, "_open", fake_open):
        with pytest.raises(urllib.error.HTTPError):
            _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS)
        status, body = _http.get_bytes(
            "https://api.example.org/x", allowed_hosts=_HOSTS, error_body=True
        )
    assert status == 400
    assert body == b'{"error_id": 400}'


def test_redirect_handler_rejects_off_allowlist_targets():
    handler = _http._AllowlistRedirectHandler(_HOSTS)
    import urllib.request

    req = urllib.request.Request("https://api.example.org/a")
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, "Found", Message(), "https://evil.test/b")
    ok = handler.redirect_request(req, None, 302, "Found", Message(), "https://api.example.org/b")
    assert ok is not None and ok.full_url == "https://api.example.org/b"


def test_html_to_text():
    assert _http.html_to_text("a<p>b &amp; <i>c</i><br>d") == "a\nb & c\nd"
    assert _http.html_to_text(None) == ""


# --------------------------------------------------------------------------- #
# Total wall-clock deadline (slow-trickle servers)
# --------------------------------------------------------------------------- #


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class _Trickle(io.BufferedIOBase):
    """A response that delivers one byte per recv, each taking *step* seconds.

    ``read()`` would block until *n* bytes arrived; the helper must use
    ``read1`` so the deadline is checked between recvs.
    """

    def __init__(self, clock: _Clock, total: int = 10_000, step: float = 1.0, ctype: str = ""):
        self.clock, self.left, self.step = clock, total, step
        self.status = 200
        self.url = "https://feeds.example/final"
        self.headers = Message()
        if ctype:
            self.headers["Content-Type"] = ctype
        self.recvs = 0

    def read1(self, size=-1):
        if self.left <= 0:
            return b""
        self.clock.t += self.step
        self.left -= 1
        self.recvs += 1
        return b"<" if self.recvs == 1 else b"x"

    def read(self, size=-1):
        raise AssertionError("a blocking read() would defeat the deadline")


def test_get_bytes_enforces_total_deadline_on_trickling_response(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_http, "_now", clock)
    resp = _Trickle(clock)
    with patch.object(_http, "_open", return_value=resp) as opened, \
            pytest.raises(_http.DeadlineExceeded):
        _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS, timeout=3)
    assert opened.call_count == 1  # a deadline overrun is not retried
    assert 5 <= resp.recvs <= 7  # default budget = 2 x timeout = 6 s


def test_get_bytes_explicit_total_timeout(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_http, "_now", clock)
    resp = _Trickle(clock)
    with patch.object(_http, "_open", return_value=resp), pytest.raises(_http.DeadlineExceeded):
        _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS, timeout=3, total_timeout=2)
    assert resp.recvs <= 3


def test_deadline_counts_time_spent_before_the_body(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_http, "_now", clock)

    def slow_open(req, timeout, allowed):  # connect + headers took 7 s
        clock.t += 7
        return _Trickle(clock, total=1)

    with patch.object(_http, "_open", slow_open), pytest.raises(_http.DeadlineExceeded):
        _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS, timeout=3)


def test_fast_response_within_deadline_is_returned(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_http, "_now", clock)
    resp = _Trickle(clock, total=4, step=0.5)
    with patch.object(_http, "_open", return_value=resp):
        assert _http.get_bytes("https://api.example.org/x", allowed_hosts=_HOSTS, timeout=3) == (200, b"<xxx")


def test_deadline_is_a_timeout_for_error_messages():
    from weblens.unified.errors import describe_exception

    assert not _http.is_transient(_http.DeadlineExceeded("slow"))
    assert "timed out" in describe_exception(_http.DeadlineExceeded("slow"), "read").one_line()


def test_fetch_public_enforces_total_deadline(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_http, "_now", clock)
    resp = _Trickle(clock)
    with patch.object(_http, "_check_public_host", lambda url: url), \
            patch.object(_http, "_open_public", return_value=resp), \
            pytest.raises(_http.DeadlineExceeded):
        _http.fetch_public("https://feeds.example/rss", timeout=5, total_timeout=30)
    assert 30 <= resp.recvs <= 32


def test_fetch_public_if_sniff_uses_its_own_timeout(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_http, "_now", clock)
    resp = _Trickle(clock)
    with patch.object(_http, "_check_public_host", lambda url: url), \
            patch.object(_http, "_open_public", return_value=resp), \
            pytest.raises(_http.DeadlineExceeded):
        _http.fetch_public_if("https://feeds.example/x", lambda c, h: True, sniff_bytes=100,
                              timeout=8, total_timeout=30)
    assert resp.recvs <= 9  # stopped by the 8 s sniff deadline, not the 30 s download cap


def test_fetch_public_if_full_download_uses_total_timeout(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_http, "_now", clock)
    resp = _Trickle(clock, ctype="application/rss+xml")
    with patch.object(_http, "_check_public_host", lambda url: url), \
            patch.object(_http, "_open_public", return_value=resp), \
            pytest.raises(_http.DeadlineExceeded):
        _http.fetch_public_if("https://feeds.example/x", lambda c, h: True, sniff_bytes=4,
                              timeout=8, total_timeout=30)
    assert 30 <= resp.recvs <= 32


# --------------------------------------------------------------------------- #
# DNS rebinding: connect only to addresses validated at connect time
# --------------------------------------------------------------------------- #

_PUBLIC_A = "93.184.216.34"
_PUBLIC_B = "93.184.216.35"


def _addrinfo(ip: str, port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


class _FakeSock:
    """Stands in for a TCP socket; replies with canned HTTP per peer IP."""

    instances: list[_FakeSock] = []
    replies: dict[str, bytes] = {}
    peer_override: str | None = None

    def __init__(self, family=None, type=None, proto=None):
        self.connected_to = None
        self.sent = b""
        self.closed = False
        _FakeSock.instances.append(self)

    def settimeout(self, _t):
        pass

    def bind(self, _addr):
        pass

    def setsockopt(self, *_args):
        pass

    def connect(self, sockaddr):
        self.connected_to = sockaddr

    def getpeername(self):
        return (_FakeSock.peer_override or self.connected_to[0], self.connected_to[1])

    def sendall(self, data):
        self.sent += data

    def makefile(self, _mode):
        return io.BytesIO(_FakeSock.replies[self.connected_to[0]])

    def close(self):
        self.closed = True


@pytest.fixture
def fake_net(monkeypatch):
    """No proxies, fake sockets; tests set ``resolve`` answers per (host, call)."""
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(_http, "_proxy_handlers", lambda: [urllib.request.ProxyHandler({})])
    _FakeSock.instances, _FakeSock.replies, _FakeSock.peer_override = [], {}, None
    answers: dict[str, list[str]] = {}
    calls: list[str] = []

    def getaddrinfo(host, port, *args, **kwargs):
        calls.append(host)
        queue = answers[host]
        ip = queue.pop(0) if len(queue) > 1 else queue[0]
        return _addrinfo(ip, port)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "socket", _FakeSock)
    monkeypatch.setattr(socket, "create_connection",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("unpinned connect")))
    return SimpleNamespace(answers=answers, calls=calls)


def test_rebinding_between_check_and_connect_is_blocked(fake_net):
    # Pre-flight lookup says public; the lookup at connect time rebinds to a private IP.
    fake_net.answers["feeds.example.com"] = [_PUBLIC_A, "10.0.0.5"]
    with pytest.raises(ValueError, match="public"):
        _http.fetch_public("http://feeds.example.com/rss")
    assert fake_net.calls == ["feeds.example.com", "feeds.example.com"]
    assert _FakeSock.instances == []  # never opened a socket, let alone to 10.0.0.5


def test_connection_goes_to_the_validated_address(fake_net):
    fake_net.answers["feeds.example.com"] = [_PUBLIC_A]
    _FakeSock.replies[_PUBLIC_A] = b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\n<rss/>"
    assert _http.fetch_public("http://feeds.example.com/rss") == ("http://feeds.example.com/rss", b"<rss/>")
    [sock] = _FakeSock.instances
    assert sock.connected_to == (_PUBLIC_A, 80)
    assert b"Host: feeds.example.com\r\n" in sock.sent  # Host header keeps the hostname


def test_non_public_peer_after_connect_is_rejected(fake_net):
    fake_net.answers["feeds.example.com"] = [_PUBLIC_A]
    _FakeSock.peer_override = "127.0.0.1"
    with pytest.raises(ValueError, match="public"):
        _http.fetch_public("http://feeds.example.com/rss")
    assert all(s.closed for s in _FakeSock.instances)


def test_mixed_public_and_private_answers_are_rejected(fake_net, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [
        *_addrinfo(_PUBLIC_A, port), *_addrinfo("192.168.1.2", port)])
    with pytest.raises(ValueError):
        _http._connect_public("feeds.example.com", 443, 5)
    assert _FakeSock.instances == []


def test_every_redirect_hop_repeats_the_connect_time_check(fake_net):
    fake_net.answers["a.example"] = [_PUBLIC_A]
    fake_net.answers["b.example"] = [_PUBLIC_B, "169.254.169.254"]  # rebinds after the redirect check
    _FakeSock.replies[_PUBLIC_A] = (b"HTTP/1.1 302 Found\r\nLocation: http://b.example/feed\r\n"
                                    b"Content-Length: 0\r\n\r\n")
    with pytest.raises(ValueError, match="public"):
        _http.fetch_public("http://a.example/feed")
    assert [s.connected_to for s in _FakeSock.instances] == [(_PUBLIC_A, 80)]


def test_redirect_to_a_public_host_is_followed_with_pinning(fake_net):
    fake_net.answers["a.example"] = [_PUBLIC_A]
    fake_net.answers["b.example"] = [_PUBLIC_B]
    _FakeSock.replies[_PUBLIC_A] = (b"HTTP/1.1 301 Moved\r\nLocation: http://b.example/feed\r\n"
                                    b"Content-Length: 0\r\n\r\n")
    _FakeSock.replies[_PUBLIC_B] = b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\n<rss/>"
    assert _http.fetch_public("http://a.example/feed") == ("http://b.example/feed", b"<rss/>")
    assert [s.connected_to for s in _FakeSock.instances] == [(_PUBLIC_A, 80), (_PUBLIC_B, 80)]


def test_https_pins_the_ip_but_verifies_tls_for_the_hostname(fake_net):
    fake_net.answers["feeds.example.com"] = [_PUBLIC_A]
    wrapped = {}

    class _Ctx:
        def wrap_socket(self, sock, server_hostname=None):
            wrapped.update(sock=sock, server_hostname=server_hostname)
            return sock

    conn = _http._PinnedHTTPSConnection("feeds.example.com", 443, timeout=5, context=_Ctx())
    conn.connect()
    assert wrapped["server_hostname"] == "feeds.example.com"  # SNI + certificate hostname check
    assert wrapped["sock"].connected_to == (_PUBLIC_A, 443)


def test_proxied_connections_connect_to_the_proxy(monkeypatch):
    seen = {}

    def create_connection(address, timeout=None, source_address=None):
        seen["address"] = address
        return "proxy-socket"

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(_http, "_connect_public",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pinned")))
    conn = _http._PinnedHTTPConnection("10.1.2.3", 3128, via_proxy=True)
    assert conn._create_connection(("10.1.2.3", 3128), 5) == "proxy-socket"
    assert seen["address"] == ("10.1.2.3", 3128)


def test_open_public_uses_pinned_handlers_for_all_hops(monkeypatch):
    built = []
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *handlers: built.extend(handlers) or SimpleNamespace(open=lambda *a, **k: "resp"))
    assert _http._open_public(urllib.request.Request("https://e.example/"), 5) == "resp"
    kinds = {type(h) for h in built}
    assert {_http._PinnedHTTPHandler, _http._PinnedHTTPSHandler, _http._PublicRedirectHandler} <= kinds


# --------------------------------------------------------------------------- #
# Saved proxy (`weblens configure proxy`); environment variables win
# --------------------------------------------------------------------------- #

_PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")


@pytest.fixture
def no_env_proxy(monkeypatch):
    for name in _PROXY_VARS:
        monkeypatch.delenv(name, raising=False)


def _save_proxy(value):
    from weblens.config import Config

    Config().set("proxy", value)


def test_saved_proxy_is_used_when_env_has_none(no_env_proxy):
    assert _http.saved_proxy() is None
    _save_proxy("127.0.0.1:8080")
    assert _http.saved_proxy() == "http://127.0.0.1:8080"
    [handler] = _http._proxy_handlers()
    assert handler.proxies == {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}
    assert _http.proxy_env()["HTTPS_PROXY"] == "http://127.0.0.1:8080"


@pytest.mark.parametrize("name", ["HTTPS_PROXY", "http_proxy", "ALL_PROXY"])
def test_env_proxy_takes_precedence_over_saved(no_env_proxy, monkeypatch, name):
    _save_proxy("http://saved:1")
    monkeypatch.setenv(name, "http://env:2")
    assert _http.saved_proxy() is None
    assert _http._proxy_handlers() == []  # urllib's default ProxyHandler reads the env
    assert _http.proxy_env() == {}


def test_no_proxy_alone_does_not_hide_the_saved_proxy(no_env_proxy, monkeypatch):
    _save_proxy("http://saved:1")
    monkeypatch.setenv("NO_PROXY", "example.com")
    assert _http.saved_proxy() == "http://saved:1"


def test_socks_proxy_goes_to_child_processes_only(no_env_proxy):
    _save_proxy("socks5://127.0.0.1:1080")
    assert _http._proxy_handlers() == []
    assert _http.proxy_env()["HTTPS_PROXY"] == "socks5://127.0.0.1:1080"


def test_get_bytes_opener_includes_the_saved_proxy(no_env_proxy, monkeypatch):
    _save_proxy("http://127.0.0.1:8080")
    built = []
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *handlers: built.extend(handlers) or SimpleNamespace(
                            open=lambda *a, **k: _Resp(b"{}")))
    assert _http.get_json("https://api.example.org/x", allowed_hosts=_HOSTS) == {}
    proxies = [h for h in built if isinstance(h, urllib.request.ProxyHandler)]
    assert proxies and proxies[0].proxies["https"] == "http://127.0.0.1:8080"


def test_upstream_tools_get_the_saved_proxy_but_env_wins(no_env_proxy, monkeypatch):
    from unittest.mock import MagicMock

    from weblens.unified import upstream

    _save_proxy("http://127.0.0.1:8080")
    completed = MagicMock(returncode=0, stdout="", stderr="")
    with patch.object(upstream, "which", return_value="/usr/bin/tool"), \
            patch("subprocess.run", return_value=completed) as sp:
        upstream.run(["tool"])
        assert sp.call_args.kwargs["env"]["HTTPS_PROXY"] == "http://127.0.0.1:8080"
        monkeypatch.setenv("HTTPS_PROXY", "http://env:3128")
        upstream.run(["tool"])
        assert sp.call_args.kwargs["env"]["HTTPS_PROXY"] == "http://env:3128"
        assert "http_proxy" not in sp.call_args.kwargs["env"]


def test_jina_reader_honors_the_saved_proxy(no_env_proxy, monkeypatch):
    from weblens.channels.web import WebChannel

    _save_proxy("http://127.0.0.1:8080")
    built = []
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *handlers: built.extend(handlers) or SimpleNamespace(
                            open=lambda *a, **k: _Resp(b"Title: T\n\nMarkdown Content:\nok")))
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("bypassed the proxy")))
    assert "ok" in WebChannel().read("https://example.com/")
    assert any(isinstance(h, urllib.request.ProxyHandler) for h in built)


def test_network_error_hint_mentions_env_and_saved_proxy():
    from weblens.unified.errors import describe_exception

    line = describe_exception(urllib.error.URLError("offline"), "read").one_line()
    assert "HTTPS_PROXY" in line and "weblens configure proxy" in line
