"""User-facing errors: one line saying what failed and how to fix it."""

from __future__ import annotations

import urllib.error

from weblens.utils.text import scrub_url_credentials

#: How to install each upstream tool (shown when it is missing).
INSTALL_HINTS: dict[str, str] = {
    "gh": "brew install gh (or see https://cli.github.com), then `gh auth login`",
    "yt-dlp": 'python -m pip install -U "yt-dlp[default]"',
    "mcporter": (
        "npm install -g mcporter && "
        "mcporter config add exa https://mcp.exa.ai/mcp --scope home"
    ),
    "opencli": "weblens install --system --channels opencli",
    "twitter": "pipx install twitter-cli",
    "rdt": "pipx install 'git+https://github.com/public-clis/rdt-cli.git'",
    "bili": "pipx install bilibili-cli",
    "feedparser": "pip install feedparser",
}


class WebLensError(Exception):
    """A failure the user can act on. ``exit_code`` 1 = runtime, 2 = usage."""

    exit_code = 1

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def one_line(self) -> str:
        text = self.message if not self.hint else f"{self.message}: {self.hint}"
        return " ".join(scrub_url_credentials(text).split())


class UsageError(WebLensError):
    """Bad input (invalid URL, unknown source, bad flag value)."""

    exit_code = 2


class ToolMissingError(WebLensError):
    """An upstream CLI is not installed."""

    def __init__(self, tool: str) -> None:
        super().__init__(f"{tool} not installed", INSTALL_HINTS.get(tool, f"install {tool}"))
        self.tool = tool


def describe_exception(exc: BaseException, what: str) -> WebLensError:
    """Turn an arbitrary exception into an actionable :class:`WebLensError`."""
    if isinstance(exc, WebLensError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return WebLensError(
                f"{what} failed: rate limited (HTTP 429)", "wait a minute and retry"
            )
        if exc.code in (401, 403):
            return WebLensError(
                f"{what} failed: access denied (HTTP {exc.code})",
                "the resource may be private or need login; run `weblens doctor`",
            )
        if exc.code == 404:
            return WebLensError(f"{what} failed: not found (HTTP 404)", "check the URL")
        return WebLensError(f"{what} failed: HTTP {exc.code}", "retry later")
    if isinstance(exc, urllib.error.URLError):
        return WebLensError(
            f"{what} failed: network error ({exc.reason})",
            "check your connection; behind a proxy, set HTTPS_PROXY or save one with "
            "`weblens configure proxy`",
        )
    if isinstance(exc, TimeoutError):
        return WebLensError(f"{what} failed: timed out", "retry, or check your network")
    if isinstance(exc, ValueError):
        return WebLensError(f"{what} failed: {exc}", "check the input")
    return WebLensError(f"{what} failed: {exc}", "re-run with --debug for details")
