"""``weblens check-update`` / ``weblens watch`` — GitHub release checks."""

import re
import time

# Remote release text is attacker-influenceable (a compromised repo/release can
# carry prompt-injection aimed at the agent reading this output), so it is
# bounded, stripped of control characters, and labelled as untrusted.
RELEASE_NOTES_MAX_CHARS = 500
RELEASE_NOTES_LABEL = "Release notes (from GitHub, untrusted):"
_CONTROL_CHARS_RE = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]"
)


def _strip_control_chars(text: str) -> str:
    """Remove control/bidi characters but keep newlines and tabs."""
    return _CONTROL_CHARS_RE.sub("", text.replace("\r\n", "\n"))


def _sanitize_remote_line(value, max_chars: int = 120) -> str:
    """Single-line, bounded, control-free rendering of a remote string."""
    text = _strip_control_chars(str(value or "")).replace("\n", " ").replace("\t", " ")
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text


def _format_release_notes(body, max_lines: int = 20) -> list[str]:
    """Render remote release notes as bounded, clearly-labelled untrusted text."""
    if not isinstance(body, str):
        return []
    text = _strip_control_chars(body).strip()
    if not text:
        return []
    truncated = len(text) > RELEASE_NOTES_MAX_CHARS
    text = text[:RELEASE_NOTES_MAX_CHARS]
    lines = text.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    rendered = [RELEASE_NOTES_LABEL]
    rendered.extend(f"  | {line.rstrip()}" for line in lines)
    if truncated:
        rendered.append("  | … (truncated)")
    return rendered


def _classify_update_error(exc):
    """Classify update-check errors for user-friendly diagnostics."""
    import requests

    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        msg = str(exc).lower()
        dns_markers = [
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "getaddrinfo failed",
            "name resolution",
            "dns",
        ]
        if any(marker in msg for marker in dns_markers):
            return "dns"
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "http"
    return "unknown"


def _update_error_text(kind):
    """Map internal error kinds to user-facing text."""
    mapping = {
        "timeout": "network timeout",
        "dns": "DNS resolution failed",
        "rate_limit": "GitHub API rate limit",
        "connection": "network connection failed",
        "server_error": "GitHub service temporarily unavailable",
        "http": "HTTP request failed",
        "unknown": "unknown network error",
    }
    return mapping.get(kind, "request failed")


def _classify_github_response_error(resp):
    """Classify non-200 GitHub responses that merit special handling."""
    if resp is None:
        return "unknown"
    if resp.status_code == 429:
        return "rate_limit"
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "")
        if remaining == "0":
            return "rate_limit"
        try:
            message = resp.json().get("message", "").lower()
            if "rate limit" in message:
                return "rate_limit"
        except Exception:
            pass
    if 500 <= resp.status_code < 600:
        return "server_error"
    return None


def _github_get_with_retry(url, timeout=10, retries=3, sleeper=time.sleep):
    """GET GitHub API with retry/backoff and basic error classification."""
    import requests

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            if attempt >= retries:
                return None, _classify_update_error(exc), attempt
            sleeper(2 ** (attempt - 1))
            continue

        err_kind = _classify_github_response_error(resp)
        if err_kind in ("rate_limit", "server_error"):
            if attempt >= retries:
                return None, err_kind, attempt
            delay = 2 ** (attempt - 1)
            retry_after = resp.headers.get("Retry-After")
            if err_kind == "rate_limit" and retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except Exception:
                    pass
            sleeper(delay)
            continue

        return resp, None, attempt

    return None, "unknown", retries


#: Full update = package + upstream tools + skill. The one-liner walks an
#: agent through all three (docs/update.md); bare pip only updates the package.
_UPDATE_INSTRUCTIONS = (
    "How to update (recommended: copy this sentence to your AI Agent; it fully updates the package + upstream tools + skill):\n"
    "  Update WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md\n"
    "Update the package only (without upstream tools and skill):\n"
    "  pip install --upgrade https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip"
)


def _is_newer_version(remote: str, local: str) -> bool:
    """True if remote is strictly newer than local (semantic compare).

    A plain != would tell users "update available" when their local build is
    AHEAD of the latest release (e.g. installed from main during a release
    window) — and walk them into a downgrade.
    """
    def parse(v):
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except ValueError:
            return None

    remote_version, local_version = parse(remote), parse(local)
    if remote_version is None or local_version is None:
        return remote != local  # unparseable — fall back to old behavior
    return remote_version > local_version


def _cmd_check_update():
    """Check for newer versions on GitHub."""
    from weblens import __version__

    print(f"Current version: v{__version__}")
    release_url = "https://api.github.com/repos/YOUR_GITHUB_USER/weblens/releases/latest"
    commit_url = "https://api.github.com/repos/YOUR_GITHUB_USER/weblens/commits/main"

    # Fetch latest release with retry/backoff.
    resp, err, attempts = _github_get_with_retry(release_url, timeout=10, retries=3)
    if err:
        print(f"[!] Could not check for updates ({_update_error_text(err)}, retried {attempts} times)")
        return "error"

    if resp.status_code == 200:
        data = resp.json()
        latest = _sanitize_remote_line(data.get("tag_name", ""), 40).lstrip("v")
        body = data.get("body", "")

        if latest and _is_newer_version(latest, __version__):
            print(f"Latest version: v{latest} ← update available!")
            notes = _format_release_notes(body, max_lines=20)
            if notes:
                print()
                for line in notes:
                    print(line)
            print()
            print(_UPDATE_INSTRUCTIONS)
            return "update_available"
        print("✅ Already up to date")
        return "up_to_date"

    release_err = _classify_github_response_error(resp)
    if release_err == "rate_limit":
        print("[!] Could not check for updates (GitHub API rate limit; try again later)")
        return "error"

    # No releases yet, fall back to latest main commit.
    resp2, err2, attempts2 = _github_get_with_retry(commit_url, timeout=10, retries=2)
    if err2:
        print(f"[!] Could not check for updates ({_update_error_text(err2)}, retried {attempts + attempts2} times)")
        return "error"
    if resp2.status_code == 200:
        commit = resp2.json()
        sha = _sanitize_remote_line(commit.get("sha", ""), 7)
        msg = _sanitize_remote_line(
            commit.get("commit", {}).get("message", "").split("\n")[0]
        )
        date = _sanitize_remote_line(
            commit.get("commit", {}).get("committer", {}).get("date", ""), 10
        )
        print(f"Latest commit: {sha} ({date}) {msg}")
        print()
        print(_UPDATE_INSTRUCTIONS)
        return "unknown"

    commit_err = _classify_github_response_error(resp2)
    if commit_err == "rate_limit":
        print("[!] Could not check for updates (GitHub API rate limit; try again later)")
        return "error"

    print(f"[!] Could not check for updates (GitHub returned {resp2.status_code})")
    return "error"


def _cmd_watch():
    """Quick health check + update check, designed for scheduled tasks.

    Only outputs problems. If everything is fine, outputs a single line.
    """
    from weblens import __version__
    from weblens.config import Config
    from weblens.doctor import check_all

    config = Config(read_only=True)
    issues = []

    # Check channels
    results = check_all(config)
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Find broken channels (were working, now broken)
    for _key, r in results.items():
        if r["status"] in ("off", "error"):
            issues.append(f"[X] {r['name']}: {r['message']}")
        elif r["status"] == "warn":
            issues.append(f"[!] {r['name']}: {r['message']}")

    # Check for updates
    update_available = False
    new_version = ""
    release_body = ""
    resp, err, _attempts = _github_get_with_retry(
        "https://api.github.com/repos/YOUR_GITHUB_USER/weblens/releases/latest",
        timeout=10,
        retries=2,
    )
    if not err and resp and resp.status_code == 200:
        data = resp.json()
        latest = _sanitize_remote_line(data.get("tag_name", ""), 40).lstrip("v")
        if latest and _is_newer_version(latest, __version__):
            update_available = True
            new_version = latest
            release_body = data.get("body", "")

    # Output
    if not issues and not update_available:
        print(f"WebLens: all good ({ok}/{total} channels available, v{__version__} is up to date)")
        return

    print("WebLens monitoring report")
    print("=" * 40)
    print(f"Version: v{__version__}  |  Channels: {ok}/{total}")

    if issues:
        print()
        for issue in issues:
            print(f"  {issue}")

    if update_available:
        print()
        print(f"New version available: v{new_version}")
        for line in _format_release_notes(release_body, max_lines=10):
            print(f"  {line}")
        print("  Update (send this one sentence to your Agent for a full update):")
        print("    Update WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md")
