# -*- coding: utf-8 -*-
"""BOSS Zhipin — search jobs and fetch JDs via boss-agent-cli + a real Chrome over CDP.

The backend is boss-agent-cli (reusing an already-logged-in real Chrome through the CDP debug port). Headless is off-limits
(it triggers code 36 risk control), so check() only does a four-layer read-only probe: it never instantiates BossClient or launches a browser.

Scraping goes through the boss-agent-cli public API (search_jobs + job_card_browser + browser_source="existing-browser");
see skill/references/career.md for usage. check() is only a health check for "installed or not + CDP link ready +
login cookie present in the browser or not"; it does not search.

Two separate login-state stores (the health check must tell them apart; lesson learned the hard way). Both are required, but they authenticate different channels:

- `~/.boss-agent/auth/session.enc` (`boss status` / `status --live` only validate this one)
  1. It is a hard gate: `_get_browser()` unconditionally calls `get_token()` and raises `AuthRequired` if it can't be read,
     so don't delete it — CDP search would fail before even connecting to the browser;
  2. But it is **not the credential used for search**: once CDP connects to the real Chrome it reuses `contexts[0]`, and its cookies
     are only injected in the "no context at all" branch, which never actually takes effect;
  3. The httpx channel (low-risk ops: status/detail/cities/`job_card_httpx`) really does use its
     cookies + stoken; code 37's `force_refresh()` also writes back to it.
- The browser cookies inside the dedicated Chrome profile: the credentials actually carried by high-risk ops such as
  search/greet in CDP mode.

So a valid session.enc + a logged-out browser = `boss status` reports logged in but search reports
`AUTH_EXPIRED`. Layer 4 asks the CDP browser itself directly (Storage.getCookies) and treats the browser as the source of truth.
"""

import base64
import hashlib
import json
import os
import platform
import socket
import struct
import urllib.request
from urllib.parse import urlparse

from weblens.probe import probe_command
from weblens.utils.url import host_matches

from .base import Channel

_CDP_URL = "http://localhost:9222"
_CDP_TIMEOUT = 5


def _chrome_launch_command(system: str | None = None) -> str:
    """Return a dedicated-profile Chrome command for the current OS."""
    system = system or platform.system()
    common = (
        "--remote-debugging-address=127.0.0.1 "
        "--remote-debugging-port=9222 "
    )
    url = '"https://www.zhipin.com/web/geek/job"'
    if system == "Darwin":
        return (
            'open -na "Google Chrome" --args '
            + common
            + '--user-data-dir="$HOME/.boss-chrome-profile" '
            + url
        )
    if system == "Windows":
        return (
            "Start-Process chrome.exe -ArgumentList "
            "'--remote-debugging-address=127.0.0.1',"
            "'--remote-debugging-port=9222',"
            '"--user-data-dir=$env:USERPROFILE\\.boss-chrome-profile",'
            "'https://www.zhipin.com/web/geek/job'"
        )
    return (
        "google-chrome "
        + common
        + '--user-data-dir="$HOME/.boss-chrome-profile" '
        + url
    )


def _cdp_json(path: str):
    """GET a local CDP endpoint (system proxy disabled); return the parsed JSON, or None on failure.

    CDP only binds to the loopback address (127.0.0.1), so a direct connection is fine; an empty ProxyHandler
    explicitly bypasses any configured system/global proxy — routing a localhost probe through a proxy is pointless
    and may get blocked. This is a deliberate localhost-only assumption and cannot be overridden by the config proxy.
    """
    req = urllib.request.Request(f"{_CDP_URL}{path}", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=_CDP_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _has_zhipin_page(pages) -> bool:
    """Whether the CDP /json tab list contains a reusable zhipin.com tab (exact hostname check)."""
    for page in pages or []:
        if page.get("type") == "page" and host_matches(page.get("url", ""), "zhipin.com"):
            return True
    return False


_SECURITY_CHECK_MARKERS = ("security-check", "zhipin-security", "_security_check")


def _security_check_blocks_all(pages) -> bool:
    """Whether all existing zhipin tabs are stuck on the anti-bot security check page (not the login page)."""
    zhipin_urls = [
        page.get("url", "")
        for page in (pages or [])
        if page.get("type") == "page" and host_matches(page.get("url", ""), "zhipin.com")
    ]
    if not zhipin_urls:
        return False
    return all(
        any(marker in url.lower() for marker in _SECURITY_CHECK_MARKERS)
        for url in zhipin_urls
    )


_WS_ACCEPT_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _read_ws_text_frame(sock: socket.socket, initial: bytes = b""):
    """Read the next text frame and return (payload, leftover).

    leftover is the extra bytes received by this recv that belong to later frames; the caller should pass them
    back as ``initial`` for the next frame (a single recv may return multiple frames). Returns (None, leftover)
    on a close frame or a dropped connection. Ping/pong frames are ignored.
    """
    buf = initial
    while True:
        while len(buf) < 2:
            chunk = sock.recv(4096)
            if not chunk:
                return None, buf
            buf += chunk
        opcode = buf[0] & 0x0F
        length = buf[1] & 0x7F
        header_len = 2
        if length == 126:
            while len(buf) < header_len + 2:
                chunk = sock.recv(4096)
                if not chunk:
                    return None, buf
                buf += chunk
            length = struct.unpack(">H", buf[header_len:header_len + 2])[0]
            header_len += 2
        elif length == 127:
            while len(buf) < header_len + 8:
                chunk = sock.recv(4096)
                if not chunk:
                    return None, buf
                buf += chunk
            length = struct.unpack(">Q", buf[header_len:header_len + 8])[0]
            header_len += 8
        while len(buf) < header_len + length:
            chunk = sock.recv(4096)
            if not chunk:
                return None, buf
            buf += chunk
        payload = buf[header_len:header_len + length]
        buf = buf[header_len + length:]
        if opcode == 0x8:  # close
            return None, buf
        if opcode in (0x1, 0x2, 0x0):  # text / binary / continuation
            return payload, buf
        # ping(0x9)/pong(0xA) etc.: ignore and read the next frame


def _send_ws_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    header = bytes([0x81])  # FIN + text
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        header += bytes([0x80 | 127]) + struct.pack(">Q", n)
    sock.sendall(header + mask + masked)


def _cdp_zhipin_login_cookie() -> bool | None:
    """Read-only probe for the zhipin.com login cookie (wt2) inside the dedicated Chrome browser.

    True = present; False = absent (browser not logged in; CDP search will report AUTH_EXPIRED);
    None = probe failed (CDP WebSocket unreachable, etc.), login state unknown.
    This only proves the browser profile has logged in; it does not verify the cookie is valid server-side.
    """
    version = _cdp_json("/json/version")
    ws_url = (version or {}).get("webSocketDebuggerUrl")
    if not ws_url:
        return None
    parsed = urlparse(ws_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    try:
        with socket.create_connection((host, port), timeout=_CDP_TIMEOUT) as sock:
            sock.settimeout(_CDP_TIMEOUT)
            key = base64.b64encode(os.urandom(16)).decode()
            # IPv6 literals need square brackets in the Host header (urlparse().hostname strips them)
            host_header = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
            handshake = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            sock.sendall(handshake.encode())
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = sock.recv(4096)
                if not chunk:
                    return None
                response += chunk
            head, _, rest = response.partition(b"\r\n\r\n")
            status_line = head.split(b"\r\n", 1)[0]
            # Parse the status code token exactly: accept "HTTP/1.1 101" (reason phrase may be empty), reject bogus codes like 1019
            if status_line.split()[1:2] != [b"101"]:
                return None
            accept = base64.b64encode(
                hashlib.sha1((key + _WS_ACCEPT_GUID).encode()).digest()
            ).decode()
            if accept not in head.decode("latin-1"):
                return None
            _send_ws_text(sock, json.dumps({"id": 1, "method": "Storage.getCookies"}))
            # Chrome may push event frames (no id) first; keep reading frames until the id==1 response arrives (capped to avoid an infinite loop).
            # leftover carries extra bytes from the previous recv so no data is lost when one recv returns multiple frames.
            buf = rest
            for _ in range(16):
                payload, buf = _read_ws_text_frame(sock, initial=buf)
                if payload is None:
                    return None
                data = json.loads(payload.decode("utf-8"))
                if data.get("id") != 1:
                    continue  # event frames etc.: skip and read the next frame
                if "result" not in data:
                    return None
                for cookie in data["result"].get("cookies", []):
                    if cookie.get("name") == "wt2" and "zhipin" in cookie.get("domain", ""):
                        return True
                return False
            return None
    except Exception:
        return None


class BossChannel(Channel):
    name = "boss"
    description = "BOSS Zhipin job search and JDs"
    backends = ["boss-agent-cli (CDP)"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "zhipin.com")

    def check(self, config=None):
        self.active_backend = None

        # Layer 1: is boss-agent-cli installed?
        probe = probe_command("boss", ["--version"], timeout=10)
        if probe.status == "missing":
            return "off", (
                "boss-agent-cli is not installed. Get the user's permission first, then run:\n"
                "  weblens install --system --channels=boss\n"
                "After installing, the user logs in to zhipin.com manually in the dedicated Chrome."
            )
        if probe.status == "broken":
            return "error", (
                "The boss command exists but cannot run — the installation is broken. Reinstall:\n"
                "  weblens install --system --channels=boss"
            )
        if not probe.ok:
            return "warn", f"boss command probe failed ({probe.status}); please check the installation"

        # Layer 2: is the CDP port reachable?
        if _cdp_json("/json/version") is None:
            return "off", (
                "CDP debug port is unreachable. Start a debug Chrome first:\n"
                f"  {_chrome_launch_command()}\n"
                "  Then have the user log in to zhipin.com manually in that window.\n"
                "Bind to 127.0.0.1 only; any process that can reach port 9222 has full control of this Chrome."
            )

        # Layer 3: is there a reusable BOSS tab?
        pages = _cdp_json("/json")
        if pages is None:
            return "warn", "CDP port is reachable but /json tab enumeration failed"
        if not _has_zhipin_page(pages):
            return "warn", (
                "CDP is reachable but no existing zhipin.com tab was found (this does not mean logged out: cookies may still be there, "
                "and boss-agent-cli will open a new tab itself). Logging in to zhipin.com in Chrome first is recommended."
            )

        # Layer 4: login cookie (wt2) inside the browser. The browser is the source of truth — `boss status` only validates
        # the local session.enc, and neither state implies the other.
        browser_cookie = _cdp_zhipin_login_cookie()
        if browser_cookie is False:
            return "warn", (
                "CDP link is ready, but there is no zhipin.com login cookie (wt2) in the dedicated Chrome browser"
                " — the browser is not logged in, so search will report AUTH_EXPIRED. Note that the logged_in reported by `boss status` "
                "only reflects the local session.enc credential, not whether the browser is logged in. Have the user visually "
                "confirm and log in to zhipin.com in that Chrome window (this should be the first step after launching the CDP Chrome), then run "
                "`boss --cdp-url http://localhost:9222 login --cdp` to sync the login state."
            )

        cookie_note = (
            "login cookie (wt2) present in the browser" if browser_cookie else "browser login cookie probe failed, login state unknown"
        )

        if _security_check_blocks_all(pages):
            return "warn", (
                f"CDP link is ready, but all existing zhipin tabs are stuck on the security check page"
                " (security-check / zhipin-security). This is a BOSS anti-bot challenge unrelated to login"
                " — it appears even when logged in and does not mean logged out; do not ask the user to log in again because of it,"
                " just have the user solve the slider manually. "
                f"Browser login state for reference: {cookie_note}. "
                "Do not use `boss status` to judge the CDP browser login state (it only validates the local session.enc)."
            )

        # All four probe layers passed: CDP link is ready; mark the backend actually in service (base contract)
        self.active_backend = self.backends[0]
        return "warn", (
            f"CDP link is ready (port 9222 reachable + reusable zhipin tab present, {cookie_note}). "
            "Doctor does not actually run a search, nor verify cookie validity server-side or the upstream boss-agent-cli #403-#407 API; "
            "first run `boss --cdp-url http://localhost:9222 login --cdp` to sync the existing login state; "
            "when searching use `boss --browser-source existing-browser --cdp-url http://localhost:9222 search ...`, "
            "so that it stops immediately instead of falling back to headless when CDP is unavailable. "
            "If search reports AUTH_EXPIRED, follow the login runbook (user logs in in the dedicated window + login --cdp); "
            "do not interpret it as a security check issue."
        )
