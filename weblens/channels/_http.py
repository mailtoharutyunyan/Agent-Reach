"""Shared bounded HTTPS helper for zero-config public-API channels.

Used by the Hacker News, Wikipedia, arXiv and Stack Exchange channels. Every
request goes through ``get_bytes`` which enforces:

  - HTTPS only, to an explicit per-channel host allowlist (port 443, no userinfo)
  - redirects re-validated against the same allowlist
  - a per-read timeout, a total wall-clock deadline per request (the body is
    read in chunks, so a slowly trickling server cannot hold a request open
    indefinitely) and a hard response-size cap (also applied after gzip
    inflation)
  - a descriptive ``weblens/<version>`` User-Agent
  - bounded retry (exponential backoff + jitter, honoring ``Retry-After``)
    for HTTP 429/502/503/504 and transient network errors
  - the proxy saved by ``weblens configure proxy`` when no ``HTTP(S)_PROXY`` /
    ``ALL_PROXY`` environment variable is set (environment variables win)

``fetch_public`` is the arbitrary-host variant (RSS feeds): public HTTP(S)
only, every hop's host must resolve to globally routable addresses, and each
direct connection is made to an address validated at connect time (no second
DNS lookup, so DNS rebinding cannot swap in a private address).
``fetch_public_if`` adds a cheap content sniff (feed detection) on top.
"""

from __future__ import annotations

import email.utils
import functools
import html
import http.client
import io
import ipaddress
import json
import os
import random
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Collection, Mapping
from typing import Any, TypeVar
from urllib.parse import urlsplit

from weblens import __version__
from weblens.utils.url import normalize_public_http_url

USER_AGENT = f"weblens/{__version__}"
DEFAULT_TIMEOUT = 15
DEFAULT_MAX_BYTES = 2 * 1024 * 1024

#: HTTP statuses worth retrying (rate limit / gateway trouble).
RETRY_STATUSES = frozenset({429, 502, 503, 504})
MAX_ATTEMPTS = 3
MAX_TOTAL_WAIT = 20.0
BASE_DELAY = 1.0
MAX_DELAY = 10.0

#: Sleeper used between attempts; tests patch this (or pass ``sleeper=``).
_sleep: Callable[[float], None] = time.sleep
#: Clock for the per-request wall-clock deadline; tests patch this.
_now: Callable[[], float] = time.monotonic
#: Largest single read while streaming a body (one recv where possible).
_CHUNK = 64 * 1024
_PUBLIC_ONLY = "only public HTTP(S) URLs are allowed"

_T = TypeVar("_T")


def retry_after_seconds(headers: Any, now: float | None = None) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date)."""
    if headers is None:
        return None
    try:
        value = headers.get("Retry-After")
    except Exception:
        return None
    if not value:
        return None
    value = str(value).strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    current = time.time() if now is None else now
    return max(0.0, when.timestamp() - current)


class DeadlineExceeded(TimeoutError):
    """A response did not finish within its request's total time budget.

    Not retried: a server that trickles bytes would just do it again.
    """


def is_transient(exc: BaseException) -> bool:
    """Return whether *exc* is a retryable HTTP status or transient network error."""
    if isinstance(exc, DeadlineExceeded):
        return False
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRY_STATUSES
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return isinstance(reason, BaseException) and _is_transient_network(reason)
    return _is_transient_network(exc)


def _is_transient_network(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionError, http.client.IncompleteRead)):
        return True
    return isinstance(exc, ssl.SSLError) and "EOF" in str(exc)


def _retry_delay(exc: BaseException, attempt: int, base_delay: float, rng: Callable[[], float]) -> float:
    if isinstance(exc, urllib.error.HTTPError):
        hinted = retry_after_seconds(exc.headers)
        if hinted is not None:
            return hinted
    backoff = min(MAX_DELAY, base_delay * (2 ** (attempt - 1)))
    return backoff + rng() * base_delay


def call_with_retries(
    fn: Callable[[], _T],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    max_total_wait: float = MAX_TOTAL_WAIT,
    base_delay: float = BASE_DELAY,
    sleeper: Callable[[float], None] | None = None,
    rng: Callable[[], float] = random.random,
    retryable: Callable[[BaseException], bool] = is_transient,
) -> _T:
    """Run *fn*, retrying transient failures with exponential backoff + jitter.

    ``Retry-After`` on an HTTP error is honored exactly; if it (or the next
    backoff) would push the total wait past *max_total_wait*, the last error
    is raised instead of sleeping.
    """
    waited = 0.0
    attempt = 1
    while True:
        try:
            return fn()
        except Exception as exc:
            if attempt >= max_attempts or not retryable(exc):
                raise
            delay = _retry_delay(exc, attempt, base_delay, rng)
            if waited + delay > max_total_wait:
                raise
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            (sleeper or _sleep)(delay)
            waited += delay
            attempt += 1


def validate_url(url: str, allowed_hosts: Collection[str]) -> None:
    """Reject anything that is not HTTPS to one of *allowed_hosts*."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid API URL") from exc
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in allowed_hosts
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"only HTTPS requests to {', '.join(sorted(allowed_hosts))} are allowed")


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only when the target stays on the allowlist."""

    def __init__(self, allowed_hosts: Collection[str]) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self._allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# --------------------------------------------------------------------------- #
# Proxy: env vars first, then the proxy saved by `weblens configure proxy`
# --------------------------------------------------------------------------- #

_PROXY_ENV_NAMES = ("https_proxy", "http_proxy", "all_proxy")


def _env_proxy_set() -> bool:
    return any(os.environ.get(name) or os.environ.get(name.upper()) for name in _PROXY_ENV_NAMES)


def saved_proxy() -> str | None:
    """The proxy saved in ``~/.weblens/config.yaml``, unless proxy env vars are set.

    ``HTTPS_PROXY`` / ``HTTP_PROXY`` / ``ALL_PROXY`` (any case) take precedence:
    when one is set this returns None and the standard environment handling
    applies. A bare ``host:port`` is treated as ``http://host:port``.
    """
    if _env_proxy_set():
        return None
    try:
        from weblens.config import Config

        data = Config(read_only=True).data
        value = data.get("proxy") or data.get("bilibili_proxy")  # legacy key
    except Exception:
        return None
    value = str(value or "").strip()
    if not value or any(ch.isspace() or ord(ch) < 0x20 for ch in value):
        return None
    return value if "://" in value else f"http://{value}"


def proxy_env() -> dict[str, str]:
    """``HTTP(S)_PROXY`` variables for child processes, from the saved proxy.

    Empty when no proxy is saved or the environment already names one.
    """
    proxy = saved_proxy()
    if not proxy:
        return {}
    return {name: proxy for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")}


def _proxy_handlers() -> list[urllib.request.BaseHandler]:
    """An explicit ProxyHandler for the saved proxy; [] keeps urllib's default.

    urllib's default ProxyHandler already honors the environment (and system
    settings). urllib cannot speak SOCKS, so a saved ``socks5://`` proxy is
    only passed to child processes (see :func:`proxy_env`).
    """
    proxy = saved_proxy()
    if not proxy or urlsplit(proxy).scheme.lower() not in {"http", "https"}:
        return []
    return [urllib.request.ProxyHandler({"http": proxy, "https": proxy})]


def urlopen(req: urllib.request.Request, timeout: float) -> Any:
    """``urllib.request.urlopen`` that also honors the saved proxy."""
    handlers = _proxy_handlers()
    if not handlers:
        return urllib.request.urlopen(req, timeout=timeout)
    return urllib.request.build_opener(*handlers).open(req, timeout=timeout)


def _open(req: urllib.request.Request, timeout: float, allowed_hosts: Collection[str]):
    """Open *req* with the allowlist-enforcing redirect handler (patched in tests)."""
    opener = urllib.request.build_opener(*_proxy_handlers(), _AllowlistRedirectHandler(allowed_hosts))
    return opener.open(req, timeout=timeout)


def _inflate(raw: bytes, encoding: str, max_bytes: int) -> bytes:
    """Decompress gzip/deflate bodies without exceeding *max_bytes*."""
    encoding = (encoding or "").lower().strip()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        wbits = 16 + zlib.MAX_WBITS
    elif encoding == "deflate":
        wbits = zlib.MAX_WBITS
    else:
        return raw
    decoder = zlib.decompressobj(wbits)
    out = decoder.decompress(raw, max_bytes + 1)
    if len(out) > max_bytes or decoder.unconsumed_tail:
        raise ValueError(f"API response exceeds the {max_bytes} byte safety limit")
    return out


def _budget(timeout: float, total_timeout: float | None) -> float:
    """Total seconds one request may take: explicit, else twice the read timeout."""
    return float(total_timeout) if total_timeout is not None else 2.0 * float(timeout)


def _chunk_reader(resp: Any) -> Callable[[int], bytes]:
    """``read1`` (at most one recv per call) where available, else ``read``.

    ``HTTPResponse.read(n)`` keeps receiving until it has *n* bytes, so a
    server trickling one byte per socket timeout could stretch a single call
    almost indefinitely; ``read1`` returns whatever one recv delivered.
    """
    for candidate in (resp, getattr(resp, "fp", None)):  # HTTPError wraps the response in .fp
        if isinstance(candidate, io.BufferedIOBase):
            return candidate.read1
    return resp.read


def _read_until(resp: Any, limit: int, deadline: float) -> bytes:
    """Read up to *limit* bytes (or EOF) in chunks; fail once *deadline* passes."""
    read = _chunk_reader(resp)
    chunks: list[bytes] = []
    total = 0
    while total < limit:
        if _now() > deadline:
            raise DeadlineExceeded("response took longer than the total time limit")
        chunk = read(min(_CHUNK, limit - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _read_bounded(resp: Any, max_bytes: int, deadline: float) -> bytes:
    raw = _read_until(resp, max_bytes + 1, deadline)
    if len(raw) > max_bytes:
        raise ValueError(f"API response exceeds the {max_bytes} byte safety limit")
    headers = getattr(resp, "headers", None)
    encoding = headers.get("Content-Encoding", "") if headers is not None else ""
    return _inflate(raw, encoding or "", max_bytes)


def get_bytes(
    url: str,
    *,
    allowed_hosts: Collection[str],
    accept: str = "application/json",
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    error_body: bool = False,
    extra_headers: Mapping[str, str] | None = None,
    total_timeout: float | None = None,
) -> tuple[int, bytes]:
    """GET *url* and return ``(status, body)`` with all safety limits applied.

    With ``error_body=True`` an HTTP error status returns its (bounded,
    inflated) body instead of raising, for APIs that report errors as JSON.
    ``extra_headers`` (e.g. ``Authorization``) are sent only to allowlisted
    hosts — redirects are re-validated against the same allowlist.
    Each attempt must finish within *total_timeout* seconds (default: twice
    *timeout*) or :class:`DeadlineExceeded` is raised.
    """
    validate_url(url, allowed_hosts)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Encoding": "gzip",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    budget = _budget(timeout, total_timeout)

    def _attempt() -> tuple[int, bytes]:
        deadline = _now() + budget
        with _open(req, timeout, allowed_hosts) as resp:
            status = getattr(resp, "status", 200) or 200
            return status, _read_bounded(resp, max_bytes, deadline)

    try:
        return call_with_retries(_attempt)
    except urllib.error.HTTPError as exc:
        if not error_body:
            raise
        try:
            body = _read_bounded(exc, max_bytes, _now() + budget)
        finally:
            exc.close()
        return exc.code, body


def get_json(url: str, *, allowed_hosts: Collection[str], **kwargs: Any) -> Any:
    """GET *url* and decode a JSON body (raises on HTTP errors)."""
    _status, body = get_bytes(url, allowed_hosts=allowed_hosts, **kwargs)
    return json.loads(body.decode("utf-8"))


def _is_global_ip(value: Any) -> bool:
    try:
        return ipaddress.ip_address(str(value).split("%", 1)[0]).is_global
    except ValueError:
        return False


def _check_public_host(url: str) -> str:
    """Normalize *url* and require its host to resolve only to global addresses.

    A pre-flight check (fails before any request is built). The connection
    itself re-resolves and pins a validated address — see :func:`_connect_public`.
    """
    url = normalize_public_http_url(url)
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise urllib.error.URLError(f"cannot resolve {host}") from exc
    if not infos or not all(_is_global_ip(info[4][0]) for info in infos):
        raise ValueError(_PUBLIC_ONLY)
    return url


def _connect_public(
    host: str, port: int, timeout: Any, source_address: tuple[str, int] | None = None
) -> socket.socket:
    """Open a TCP connection to *host* only via addresses validated as public.

    The addresses are resolved and checked here, and the socket connects to
    exactly those sockaddrs — there is no second DNS lookup for a rebinding
    resolver to answer differently. The connected peer is checked again as
    defense in depth. Any non-global address aborts with ``ValueError``.
    """
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)  # gaierror is an OSError
    if not infos or not all(_is_global_ip(info[4][0]) for info in infos):
        raise ValueError(_PUBLIC_ONLY)
    last_error: OSError | None = None
    for family, socktype, proto, _canonname, sockaddr in infos:
        sock = socket.socket(family, socktype, proto)
        try:
            if isinstance(timeout, (int, float)):
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            peer = sock.getpeername()[0]
        except OSError as exc:
            sock.close()
            last_error = exc
            continue
        if not _is_global_ip(peer):
            sock.close()
            raise ValueError(_PUBLIC_ONLY)
        return sock
    raise last_error or OSError(f"cannot connect to {host}")


class _PinnedConnectionMixin:
    """Route ``connect()`` through :func:`_connect_public` for direct connections.

    TLS still wraps the socket with ``server_hostname=<URL host>``, so SNI,
    certificate and hostname verification (and the Host header) are unchanged.
    Through a proxy the proxy makes the final connection, so only the
    pre-flight :func:`_check_public_host` applies there.
    """

    def __init__(self, *args: Any, via_proxy: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._via_proxy = via_proxy
        self._create_connection = self._pinned_create_connection

    def _pinned_create_connection(
        self, address: tuple[str, int], timeout: Any = None,
        source_address: tuple[str, int] | None = None,
    ) -> socket.socket:
        if self._via_proxy or getattr(self, "_tunnel_host", None):
            return socket.create_connection(address, timeout, source_address)
        host, port = address
        return _connect_public(host, port, timeout, source_address)


class _PinnedHTTPConnection(_PinnedConnectionMixin, http.client.HTTPConnection):
    pass


class _PinnedHTTPSConnection(_PinnedConnectionMixin, http.client.HTTPSConnection):
    pass


def _via_proxy(req: urllib.request.Request) -> bool:
    return req.has_proxy() or bool(getattr(req, "_tunnel_host", None))


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPConnection, via_proxy=_via_proxy(req)), req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(
            functools.partial(_PinnedHTTPSConnection, via_proxy=_via_proxy(req)), req,
            context=getattr(self, "_context", None),
        )


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_public(req: urllib.request.Request, timeout: float):
    """Open *req* re-validating every redirect hop (patched in tests).

    Every hop (redirects included) connects through the pinned connection
    classes, so each one repeats the public-address check at connect time.
    """
    opener = urllib.request.build_opener(
        *_proxy_handlers(), _PublicRedirectHandler(), _PinnedHTTPHandler(), _PinnedHTTPSHandler(),
    )
    return opener.open(req, timeout=timeout)


def fetch_public(
    url: str,
    *,
    accept: str = "*/*",
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    total_timeout: float | None = None,
) -> tuple[str, bytes]:
    """GET an arbitrary *public* URL; returns ``(final_url, body)``.

    For user-supplied URLs whose host cannot be allowlisted in advance (feeds).
    Each attempt must finish within *total_timeout* (default twice *timeout*).
    """
    url = _check_public_host(url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Encoding": "gzip"},
    )
    budget = _budget(timeout, total_timeout)

    def _attempt() -> tuple[str, bytes]:
        deadline = _now() + budget
        with _open_public(req, timeout) as resp:
            final = getattr(resp, "url", None) or url
            return final, _read_bounded(resp, max_bytes, deadline)

    return call_with_retries(_attempt)


def _inflate_head(raw: bytes, encoding: str, limit: int) -> bytes:
    """Best-effort decompression of a response *prefix* (for sniffing only)."""
    encoding = (encoding or "").lower().strip()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        wbits = 16 + zlib.MAX_WBITS
    elif encoding == "deflate":
        wbits = zlib.MAX_WBITS
    else:
        return raw[:limit]
    try:
        return zlib.decompressobj(wbits).decompress(raw, limit)
    except zlib.error:
        return b""


def fetch_public_if(
    url: str,
    wanted: Callable[[str, bytes], bool],
    *,
    accept: str = "*/*",
    sniff_bytes: int = 8192,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    total_timeout: float | None = None,
) -> tuple[str, bytes] | None:
    """Sniff a public URL and download it fully only if ``wanted`` says so.

    Reads the first *sniff_bytes* (raw) and calls ``wanted(content_type,
    decoded_prefix)``. If it returns False the connection is closed and
    ``None`` is returned — the caller pays for one small read, not a full
    download. Otherwise the rest of the *same* response is read (bounded by
    *max_bytes*) and ``(final_url, body)`` is returned. Same public-host and
    per-redirect checks as :func:`fetch_public`; no retries (a sniff is an
    optimisation, callers fall back on any error).

    Deadlines: connecting and reading the prefix must finish within *timeout*
    seconds of the call; the full download within *total_timeout* (default
    twice *timeout*).
    """
    start = _now()
    sniff_deadline = start + float(timeout)
    full_deadline = start + max(float(timeout), _budget(timeout, total_timeout))
    url = _check_public_host(url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Encoding": "gzip"},
    )
    with _open_public(req, timeout) as resp:
        final = getattr(resp, "url", None) or url
        headers = getattr(resp, "headers", None)
        content_type = (headers.get("Content-Type", "") if headers is not None else "") or ""
        encoding = (headers.get("Content-Encoding", "") if headers is not None else "") or ""
        head = _read_until(resp, sniff_bytes, sniff_deadline)
        if not wanted(content_type, _inflate_head(head, encoding, sniff_bytes * 4)):
            return None
        raw = head + _read_until(resp, max(0, max_bytes + 1 - len(head)), full_deadline)
        if len(raw) > max_bytes:
            raise ValueError(f"response exceeds the {max_bytes} byte safety limit")
        return final, _inflate(raw, encoding, max_bytes)


_BLOCK_TAG_RE = re.compile(r"<\s*(?:br|/p|p|/div|/li|/pre|/h[1-6])\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def html_to_text(value: str | None) -> str:
    """Flatten an API HTML fragment (comment/answer body/snippet) to plain text."""
    if not value:
        return ""
    text = _BLOCK_TAG_RE.sub("\n", value)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return _BLANK_LINES_RE.sub("\n\n", text).strip()
