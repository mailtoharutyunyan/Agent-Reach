"""YouTube via yt-dlp: metadata + subtitles as plain text; search via ytsearchN:.

When ``weblens configure youtube-cookies <browser>`` has saved
``youtube_cookies_from``, every yt-dlp call gets
``--cookies-from-browser <browser>`` (signed-in / age-restricted videos)."""

from __future__ import annotations

import html
import json
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import upstream
from .errors import WebLensError
from .models import ReadResult, SearchResult

#: Query parameters that turn a watch URL into a playlist / radio request.
_PLAYLIST_PARAMS = frozenset({"list", "index", "start_radio", "pp", "playnext", "rv"})
_SUB_WAIT_SECONDS = 5
#: Documented yt-dlp extractor arg ("default" = yt-dlp's own default clients;
#: overrides any player_client pinned in the user's yt-dlp config).
_FALLBACK_EXTRACTOR_ARGS = "youtube:player_client=default"
_BASE_ARGS = ["--no-playlist", "--no-warnings"]

#: Browsers yt-dlp's ``--cookies-from-browser`` supports.
SUPPORTED_BROWSERS = frozenset({
    "brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale",
})
COOKIES_CONFIG_KEY = "youtube_cookies_from"
_MAX_PROFILE_CHARS = 512

Runner = Callable[..., upstream.CommandResult]


def parse_cookie_source(value: Any) -> str:
    """Validate ``<browser>[:<profile>]``; return it normalized or raise ValueError."""
    text = str(value or "").strip()
    browser, sep, profile = text.partition(":")
    browser = browser.strip().lower()
    if browser not in SUPPORTED_BROWSERS:
        raise ValueError(
            f"unsupported browser {browser!r}; choose one of: "
            + ", ".join(sorted(SUPPORTED_BROWSERS))
        )
    if sep and (not profile or len(profile) > _MAX_PROFILE_CHARS
                or any(ord(ch) < 32 for ch in profile)):
        raise ValueError("invalid browser profile after ':'")
    return f"{browser}:{profile}" if sep else browser


def cookie_args(config: Any = None) -> list[str]:
    """``--cookies-from-browser`` args from saved config, or ``[]`` when unset."""
    if config is None:
        try:
            from weblens.config import Config

            config = Config(read_only=True)
        except Exception:
            return []
    try:
        data = getattr(config, "data", None)
        raw = data.get(COOKIES_CONFIG_KEY) if isinstance(data, dict) else None
    except Exception:
        raw = None
    if not raw:
        return []
    try:
        source = parse_cookie_source(raw)
    except ValueError as exc:
        raise WebLensError(
            f"invalid {COOKIES_CONFIG_KEY} in config ({exc})",
            "run `weblens configure youtube-cookies <browser>`, e.g. chrome",
        ) from None
    return ["--cookies-from-browser", source]


def clean_url(url: str) -> str:
    """Drop playlist/radio params so yt-dlp reads exactly one video."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k not in _PLAYLIST_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _fmt_duration(seconds: Any) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _fmt_date(value: Any) -> str:
    value = str(value or "")
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if re.fullmatch(r"\d{8}", value) else value


def _find_lang(tracks: dict[str, Any], lang: str) -> str | None:
    if not lang:
        return None
    if lang in tracks:
        return lang
    for key in sorted(tracks):
        if key.startswith(lang + "-") and not key.endswith("-orig"):
            return key
    return None


def choose_subtitle(info: dict[str, Any]) -> tuple[str, bool] | None:
    """Pick ``(lang, is_auto)``: manual before auto, English before original."""
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat" and v}
    auto = {k: v for k, v in (info.get("automatic_captions") or {}).items() if v}
    original = str(info.get("language") or "").split("-")[0].lower()

    for lang in ("en", original):
        key = _find_lang(manual, lang)
        if key:
            return key, False
    candidates: list[str] = []
    if original in ("", "en"):
        candidates += ["en-orig", "en"]
    if original:
        candidates += [f"{original}-orig", original]
    candidates.append("en")  # machine translation as a last resort
    for key in candidates:
        if key in auto:
            return key, True
    return None


def vtt_to_text(vtt: str) -> str:
    """Flatten WebVTT to plain text, dropping cue timing and rolling duplicates."""
    lines: list[str] = []
    recent: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if (
            not line
            or line == "WEBVTT"
            or "-->" in line
            or line.isdigit()
            or line.startswith(("Kind:", "Language:", "NOTE", "STYLE", "REGION"))
        ):
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if not line or line in recent:
            continue
        lines.append(line)
        recent = (recent + [line])[-3:]
    paragraphs = [" ".join(lines[i:i + 12]) for i in range(0, len(lines), 12)]
    return "\n\n".join(paragraphs)


def _extract_info(url: str, run: Runner, extra: list[str] | None = None) -> dict[str, Any]:
    extra = extra or []
    result = run(["yt-dlp", "-J", "--skip-download", *_BASE_ARGS, *extra, url],
                 timeout=90)
    if not result.ok:
        raise _ytdlp_error(result.stderr, extra)
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WebLensError("yt-dlp returned invalid JSON", "upgrade yt-dlp: "
                           'python -m pip install -U "yt-dlp[default]"') from exc
    if not isinstance(info, dict):
        raise WebLensError("yt-dlp returned no video info", "check the URL")
    return info


def _cookie_browser(extra: list[str] | None) -> str:
    if extra and "--cookies-from-browser" in extra:
        idx = extra.index("--cookies-from-browser")
        if idx + 1 < len(extra):
            return extra[idx + 1].split(":", 1)[0]
    return ""


def _ytdlp_error(stderr: str, extra: list[str] | None = None) -> WebLensError:
    line = upstream.last_error_line(stderr)
    low = line.lower()
    browser = _cookie_browser(extra)
    if "sign in" in low or "confirm you" in low:
        if browser:
            hint = (f"YouTube wants a signed-in session; cookies from {browser} were used — "
                    f"log into youtube.com in {browser} (or switch with "
                    "`weblens configure youtube-cookies <browser>`)")
        else:
            hint = ("YouTube wants a signed-in session; run "
                    "`weblens configure youtube-cookies <browser>` (e.g. chrome) "
                    "while logged into youtube.com in that browser")
    elif browser and "cookie" in low:
        hint = (f"yt-dlp could not read {browser} cookies; close {browser} or pick another "
                "browser with `weblens configure youtube-cookies <browser>`")
    elif "429" in low:
        hint = "YouTube rate limited this IP; wait a few minutes and retry"
    elif "unavailable" in low or "private" in low:
        hint = "the video is private, removed or region-locked"
    else:
        hint = 'upgrade yt-dlp: python -m pip install -U "yt-dlp[default]"'
    return WebLensError(f"yt-dlp failed ({line})", hint)


def _download_subs(
    run: Runner, lang: str, is_auto: bool, *, info_json: Path | None, url: str,
    tmp: Path, extra: list[str],
) -> tuple[str | None, str]:
    """Return ``(text, stderr)``; text is None when no subtitle file appeared."""
    source = ["--load-info-json", str(info_json)] if info_json else [url]
    argv = [
        "yt-dlp", "--skip-download", *_BASE_ARGS,
        "--write-auto-subs" if is_auto else "--write-subs",
        "--sub-langs", lang, "--sub-format", "vtt/best",
        "-P", str(tmp), "-o", "subs.%(ext)s", *extra, *source,
    ]
    result = run(argv, timeout=120)
    files = sorted(p for p in tmp.glob("subs.*") if p.suffix != ".json")
    if not files:
        return None, result.stderr
    raw = files[0].read_text(encoding="utf-8", errors="replace")
    return (vtt_to_text(raw) if files[0].suffix == ".vtt" else raw), result.stderr


def read(url: str, run: Runner | None = None, config: Any = None) -> ReadResult:
    run = run or upstream.run
    url = clean_url(url)
    cookies = cookie_args(config)
    info = _extract_info(url, run, cookies)
    webpage = info.get("webpage_url") or url
    result = ReadResult(
        title=info.get("title") or "",
        url=webpage,
        source="youtube",
        backend="yt-dlp",
        metadata={
            k: v for k, v in {
                "channel": info.get("channel") or info.get("uploader") or "",
                "date": _fmt_date(info.get("upload_date")),
                "duration": _fmt_duration(info.get("duration")),
                "views": info.get("view_count"),
                "likes": info.get("like_count"),
                "language": info.get("language") or "",
            }.items() if v not in (None, "")
        },
    )
    sections = []
    description = (info.get("description") or "").strip()
    if description:
        sections.append(f"## Description\n\n{description}")

    choice = choose_subtitle(info)
    if choice is None:
        result.notes.append("no subtitles available for this video")
    else:
        lang, is_auto = choice
        with tempfile.TemporaryDirectory(prefix="weblens-yt-") as tmpdir:
            tmp = Path(tmpdir)
            info_json = tmp / "info.json"
            info_json.write_text(json.dumps(info), encoding="utf-8")
            text, stderr = _download_subs(
                run, lang, is_auto, info_json=info_json, url=webpage, tmp=tmp, extra=cookies
            )
            if text is None and "429" in stderr:
                # Rate limited on the subtitle endpoint: one slower retry with a
                # fresh extraction using yt-dlp's default player clients.
                text, stderr = _download_subs(
                    run, lang, is_auto, info_json=None, url=webpage, tmp=tmp,
                    extra=["--sleep-subtitles", str(_SUB_WAIT_SECONDS),
                           "--extractor-args", _FALLBACK_EXTRACTOR_ARGS, *cookies],
                )
                if text is None:
                    result.notes.append(
                        "subtitles skipped: YouTube rate limited subtitle downloads "
                        "(HTTP 429); retry in a few minutes"
                    )
            elif text is None:
                result.notes.append(
                    f"subtitles skipped: {upstream.last_error_line(stderr)}"
                )
        if text:
            kind = "auto-generated" if is_auto else "manual"
            result.metadata["subtitles"] = f"{lang} ({kind})"
            sections.append(f"## Transcript ({lang}, {kind})\n\n{text}")
    result.body = "\n\n".join(sections)
    return result


def search(query: str, limit: int, run: Runner | None = None,
           config: Any = None) -> list[SearchResult]:
    run = run or upstream.run
    limit = max(1, min(int(limit), 50))
    cookies = cookie_args(config)
    proc = run(["yt-dlp", "-J", "--flat-playlist", "--no-warnings", *cookies,
                f"ytsearch{limit}:{query}"], timeout=90)
    if not proc.ok:
        raise _ytdlp_error(proc.stderr, cookies)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise WebLensError("yt-dlp returned invalid JSON", "upgrade yt-dlp") from exc
    results = []
    for entry in (data.get("entries") or [])[:limit]:
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id") or ""
        url = entry.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
        extra = {
            k: v for k, v in {
                "channel": entry.get("channel") or entry.get("uploader"),
                "duration": _fmt_duration(entry.get("duration")),
                "views": entry.get("view_count"),
            }.items() if v not in (None, "")
        }
        results.append(SearchResult(
            title=entry.get("title") or "", url=url, source="youtube",
            snippet=(entry.get("description") or "")[:300], extra=extra,
        ))
    return results
