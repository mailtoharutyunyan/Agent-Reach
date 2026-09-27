"""``weblens read <url>``: route a URL to the most specific adapter.

Routing order: a platform channel whose native reader supports the URL shape
(most specific first); else a feed-shaped URL (``/feed``, ``.rss``, ``.atom``,
``/feeds/…``, ``?format=rss`` — see ``weblens.channels.rss.is_feed_url``) goes
to feedparser, even on platform hosts (``news.ycombinator.com/rss``,
``github.com/<owner>/<repo>/releases.atom``); else the platform channel; else
the generic ``web`` channel. If a feed read fails for any reason the URL is
read by the channel that would otherwise have handled it, with a note.
Before handing an unclaimed URL to Jina Reader, a cheap content sniff
(Content-Type / root element of the first few KB) detects feeds with
feed-less URLs such as ``https://hnrss.org/frontpage``.
Adapters that depend on an optional upstream CLI fall back to Jina with
a note when that CLI is not the channel's active backend.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from weblens.channels import get_all_channels, get_channel
from weblens.channels.base import Channel
from weblens.channels.rss import is_feed_url
from weblens.utils.text import scrub_url_credentials
from weblens.utils.url import normalize_public_http_url

from . import github as github_adapter
from . import upstream
from . import youtube as youtube_adapter
from .errors import UsageError, WebLensError, describe_exception
from .models import ReadResult

#: Explicit most-specific-first order; unlisted channels come after these,
#: then ``rss``, then ``web``.
ROUTE_ORDER = [
    "hackernews", "wikipedia", "arxiv", "stackoverflow", "youtube", "github",
    "v2ex", "reddit", "twitter", "bilibili", "xiaohongshu",
]
_LAST = ("rss", "web")
_NEVER = {"exa_search"}  # search-only


def _iso(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _clean(meta: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in meta.items() if v not in (None, "", [])}


def ordered_channels() -> list[Channel]:
    channels = {ch.name: ch for ch in get_all_channels() if ch.name not in _NEVER}
    ordered = [channels[n] for n in ROUTE_ORDER if n in channels]
    ordered += [ch for n, ch in channels.items() if n not in ROUTE_ORDER and n not in _LAST]
    ordered += [channels[n] for n in _LAST if n in channels]
    return ordered


def _is_native(channel_name: str, url: str) -> bool:
    shape = _NATIVE_SHAPES.get(channel_name)
    try:
        return shape is not None and bool(shape(url))
    except Exception:
        return False


def route(url: str, *, feeds: bool = True) -> Channel:
    """The channel that reads *url* (see the module docstring for the order).

    ``feeds=False`` skips the feed-shape rule — the fallback after a failed
    feed read.
    """
    platform: Channel | None = None
    for channel in ordered_channels():
        if channel.name in _LAST:
            continue
        try:
            if channel.can_handle(url):
                platform = channel
                break
        except Exception:
            continue
    if feeds and (platform is None or not _is_native(platform.name, url)) and is_feed_url(url):
        rss = get_channel("rss")
        if rss is not None:
            return rss
    if platform is not None:
        return platform
    web = get_channel("web")
    assert web is not None
    return web


# --------------------------------------------------------------------------- #
# Native channel adapters
# --------------------------------------------------------------------------- #

def _read_hackernews(channel: Any, url: str, config: Any) -> ReadResult:
    item = channel.read(url)
    sections = []
    if item.get("text"):
        sections.append(item["text"])
    comments = item.get("comments") or []
    if comments:
        rendered = []
        for c in comments:
            indent = "  " * (max(1, c.get("depth", 1)) - 1)
            text = (c.get("text") or "").replace("\n", " ")
            rendered.append(f"{indent}- **{c.get('author', '?')}**: {text}")
        sections.append(f"## Comments ({len(comments)} shown)\n\n" + "\n".join(rendered))
    link = item.get("url") if item.get("url") != item.get("hn_url") else ""
    return ReadResult(
        title=item.get("title") or f"HN item {item.get('id')}",
        url=item.get("hn_url") or url,
        source="hackernews",
        backend="HN Firebase API",
        body="\n\n".join(sections),
        metadata=_clean({
            "link": link,
            "type": item.get("type"),
            "points": item.get("score"),
            "author": item.get("author"),
            "date": _iso(item.get("time")),
            "comments": item.get("comments_count"),
        }),
    )


_WIKI_DEFAULT_CHARS = 200_000


def _read_wikipedia(channel: Any, url: str, config: Any, max_chars: int | None = None) -> ReadResult:
    limit = max_chars or _WIKI_DEFAULT_CHARS
    article = channel.read(url, max_chars=limit)
    result = ReadResult(
        title=article.get("title", ""),
        url=article.get("url") or url,
        source="wikipedia",
        backend="MediaWiki API",
        body=article.get("text", ""),
        metadata=_clean({"language": article.get("lang")}),
    )
    if article.get("truncated"):
        result.truncated = True
        if max_chars is None:
            result.notes.append(f"article truncated at {limit} characters; pass --max-chars to change")
    return result


def _read_arxiv(channel: Any, url: str, config: Any) -> ReadResult:
    paper = channel.read(url)
    return ReadResult(
        title=paper.get("title", ""),
        url=paper.get("url") or url,
        source="arxiv",
        backend="arXiv API",
        body=f"## Abstract\n\n{paper.get('summary', '')}",
        metadata=_clean({
            "id": paper.get("id"),
            "authors": ", ".join(paper.get("authors") or []),
            "published": paper.get("published"),
            "updated": paper.get("updated"),
            "categories": ", ".join(paper.get("categories") or []),
            "comment": paper.get("comment"),
            "doi": paper.get("doi"),
            "pdf": paper.get("pdf_url"),
        }),
    )


def _read_stackoverflow(channel: Any, url: str, config: Any) -> ReadResult:
    q = channel.read(url)
    parts = [q.get("body", "")]
    for a in q.get("answers") or []:
        mark = " ✓ accepted" if a.get("is_accepted") else ""
        parts.append(
            f"## Answer by {a.get('author', '?')} (score {a.get('score', 0)}{mark})\n\n{a.get('body', '')}"
        )
    return ReadResult(
        title=q.get("title", ""),
        url=q.get("url") or url,
        source="stackoverflow",
        backend="Stack Exchange API",
        body="\n\n".join(parts),
        metadata=_clean({
            "score": q.get("score"),
            "answers": q.get("answer_count"),
            "author": q.get("author"),
            "date": _iso(q.get("creation_date")),
            "tags": ", ".join(q.get("tags") or []),
        }),
    )


_V2EX_TOPIC_RE = re.compile(r"^/t/(\d+)")
_V2EX_MAX_REPLIES = 100


def _read_v2ex(channel: Any, url: str, config: Any) -> ReadResult:
    match = _V2EX_TOPIC_RE.match(urlsplit(url).path)
    if not match:
        result = _read_web(url, config)
        result.notes.insert(0, "only V2EX topic URLs (/t/<id>) have native support; read via Jina Reader")
        return result
    topic = channel.get_topic(int(match.group(1)))
    parts = [topic.get("content", "")]
    replies = (topic.get("replies") or [])[:_V2EX_MAX_REPLIES]
    if replies:
        parts.append(f"## Replies ({len(replies)} shown)")
        parts.append("\n".join(
            f"- **{r.get('author', '?')}**: {(r.get('content') or '').strip()}" for r in replies
        ))
    return ReadResult(
        title=topic.get("title", ""),
        url=topic.get("url") or url,
        source="v2ex",
        backend="V2EX API",
        body="\n\n".join(parts),
        metadata=_clean({
            "node": topic.get("node_title") or topic.get("node_name"),
            "author": topic.get("author"),
            "date": _iso(topic.get("created")),
            "replies": topic.get("replies_count"),
        }),
    )


def _read_youtube(channel: Any, url: str, config: Any) -> ReadResult:
    return youtube_adapter.read(url, config=config)


def _read_github(channel: Any, url: str, config: Any) -> ReadResult:
    return github_adapter.read(url, config=config)


# --------------------------------------------------------------------------- #
# RSS / Atom
# --------------------------------------------------------------------------- #

_FEED_ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"
_FEED_MAX_BYTES = 5 * 1024 * 1024
#: Wall-clock cap for downloading a whole feed (per attempt).
_FEED_TOTAL_TIMEOUT = 30
_SNIFF_BYTES = 8192
_SNIFF_TIMEOUT = 8
_FEED_CONTENT_TYPES = ("application/rss+xml", "application/atom+xml", "application/rdf+xml")
_FEED_ROOT_RE = re.compile(rb"<(?:rss|feed|rdf:rdf)[\s>/]", re.IGNORECASE)
#: Extensions that are never feeds — skip the sniff request for these.
_NO_SNIFF_EXT = (
    ".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".mp3", ".mp4", ".webm", ".zip", ".md", ".txt", ".json", ".csv",
)


def looks_like_feed(content_type: str, head: bytes) -> bool:
    """RSS/Atom by Content-Type, or by the document's root element."""
    ctype = content_type.split(";", 1)[0].strip().lower()
    if ctype in _FEED_CONTENT_TYPES:
        return True
    if ctype and "xml" not in ctype and ctype != "text/plain" \
            and ctype != "application/octet-stream":
        return False  # text/html, images, JSON, …
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not text.startswith(b"<"):
        return False
    # Root element (possibly after <?xml …?>, stylesheet PIs and comments).
    return bool(_FEED_ROOT_RE.search(text[:_SNIFF_BYTES * 4]))


def _sniff_feed(url: str) -> tuple[str, bytes] | None:
    """Cheap feed detection for URLs no channel claimed: ``(final_url, body)`` or None.

    One small read decides; a feed is then downloaded from the same response
    (no second request) and non-feeds cost only the sniffed prefix. Any error
    returns None so the caller falls back to Jina Reader.
    """
    if urlsplit(url).path.lower().endswith(_NO_SNIFF_EXT):
        return None
    from weblens.channels import _http

    try:
        return _http.fetch_public_if(
            url, looks_like_feed, accept=_FEED_ACCEPT, sniff_bytes=_SNIFF_BYTES,
            timeout=_SNIFF_TIMEOUT, max_bytes=_FEED_MAX_BYTES,
            total_timeout=_FEED_TOTAL_TIMEOUT,
        )
    except Exception:
        return None


def _read_rss(channel: Any, url: str, config: Any) -> ReadResult:
    from weblens.channels import _http

    final_url, body = _http.fetch_public(
        url, accept=_FEED_ACCEPT, max_bytes=_FEED_MAX_BYTES, total_timeout=_FEED_TOTAL_TIMEOUT,
    )
    return _parse_feed(final_url, body)


def _parse_feed(final_url: str, body: bytes) -> ReadResult:
    try:
        import feedparser
    except ImportError as exc:
        raise WebLensError("feedparser not installed", "pip install feedparser") from exc

    feed = feedparser.parse(body)
    entries = feed.get("entries") or []
    if not entries and not (feed.get("feed") or {}).get("title"):
        raise _NotAFeed()
    meta = feed.get("feed") or {}
    lines = []
    for entry in entries[:30]:
        date = entry.get("published") or entry.get("updated") or ""
        summary = _strip_html(entry.get("summary") or "")[:400]
        lines.append(
            f"### {entry.get('title', '(untitled)')}\n"
            f"{entry.get('link', '')}" + (f" · {date}" if date else "")
            + (f"\n\n{summary}" if summary else "")
        )
    return ReadResult(
        title=meta.get("title") or final_url,
        url=final_url,
        source="rss",
        backend="feedparser",
        body="\n\n".join(lines),
        metadata=_clean({
            "description": _strip_html(meta.get("subtitle") or ""),
            "site": meta.get("link"),
            "entries": len(entries),
            "updated": meta.get("updated"),
        }),
    )


def _strip_html(value: str) -> str:
    from weblens.channels._http import html_to_text

    return html_to_text(value)


class _NotAFeed(Exception):
    pass


# --------------------------------------------------------------------------- #
# Upstream-CLI platforms (reddit / twitter / bilibili / xiaohongshu)
# --------------------------------------------------------------------------- #

def _reddit_post_id(url: str) -> str | None:
    match = re.search(r"/comments/([A-Za-z0-9]+)", urlsplit(url).path)
    return match.group(1) if match else None


def _bili_id(url: str) -> str | None:
    match = re.search(r"(BV[0-9A-Za-z]{10})", urlsplit(url).path)
    return match.group(1) if match else None


def upstream_read_argv(channel_name: str, backend: str, url: str) -> list[str] | None:
    """Documented upstream read command for (channel, active backend), or None."""
    if channel_name == "reddit":
        post = _reddit_post_id(url)
        if not post:
            return None
        if backend == "OpenCLI":
            return ["opencli", "reddit", "read", post, "-f", "yaml"]
        if backend == "rdt-cli":
            return ["rdt", "read", post, "--yaml"]
    if channel_name == "twitter":
        is_article = "/i/article/" in url or "/article/" in urlsplit(url).path
        if backend == "twitter-cli":
            return ["twitter", "article" if is_article else "tweet", url, "--yaml"]
        if backend == "OpenCLI" and is_article:
            return ["opencli", "twitter", "article", url, "-f", "yaml"]
    if channel_name == "bilibili" and backend == "bili-cli":
        bvid = _bili_id(url)
        return ["bili", "video", bvid] if bvid else None
    if channel_name == "xiaohongshu" and backend == "OpenCLI":
        return ["opencli", "xiaohongshu", "note", url, "-f", "yaml"]
    return None


def _read_via_upstream(channel: Channel, url: str, config: Any) -> ReadResult:
    try:
        channel.check(config)
    except Exception:
        channel.active_backend = None
    backend = channel.active_backend or ""
    argv = upstream_read_argv(channel.name, backend, url) if backend else None
    if argv is None:
        result = _read_web(url, config)
        why = (f"no working {channel.name} backend (see `weblens doctor`)" if not backend
               else f"{backend} has no read command for this URL")
        result.notes.insert(0, f"{why}; read via Jina Reader instead — content may be partial")
        return result
    env = None
    if channel.name == "twitter":
        from weblens.channels.twitter import twitter_cli_child_env

        env = twitter_cli_child_env(config)
    proc = upstream.run(argv, timeout=120, env=env)
    if not proc.ok:
        raise WebLensError(
            f"{argv[0]} failed ({upstream.last_error_line(proc.stderr or proc.stdout)})",
            f"check login/health with `weblens doctor`; command was: {' '.join(argv[:3])} …",
        )
    title = ""
    data = upstream.parse_structured(proc.stdout)
    if isinstance(data, dict):
        title = str(data.get("title") or data.get("text") or "")[:120]
    return ReadResult(
        title=title or url, url=url, source=channel.name, backend=backend,
        body=proc.stdout.strip(),
    )


# --------------------------------------------------------------------------- #
# Generic web (Jina Reader)
# --------------------------------------------------------------------------- #

_JINA_HEADER_RE = re.compile(r"^(Title|URL Source|Published Time):\s*(.*)$")


def parse_jina(text: str) -> tuple[str, dict[str, str], str]:
    """Split Jina Reader output into (title, metadata, markdown body)."""
    title, meta = "", {}
    body = text
    marker = "Markdown Content:"
    head, sep, rest = text.partition(marker)
    if sep:
        body = rest.lstrip("\n")
        for line in head.splitlines():
            match = _JINA_HEADER_RE.match(line.strip())
            if match:
                key, value = match.groups()
                if key == "Title":
                    title = value.strip()
                elif key == "Published Time" and value.strip():
                    meta["published"] = value.strip()
    return title, meta, body.strip()


def _read_web(url: str, config: Any) -> ReadResult:
    channel = get_channel("web")
    assert channel is not None
    text = channel.read(url)  # type: ignore[attr-defined]
    title, meta, body = parse_jina(text)
    return ReadResult(title=title or url, url=url, source="web", backend="Jina Reader",
                      body=body, metadata=meta)


def _read_web_or_feed(url: str, config: Any) -> ReadResult:
    """No channel matched: sniff for an RSS/Atom feed, else Jina Reader."""
    sniffed = _sniff_feed(url)
    if sniffed is None:
        return _read_web(url, config)
    try:
        result = _parse_feed(*sniffed)
    except Exception as exc:
        result = _read_web(url, config)
        result.notes.insert(0, f"{_feed_failure(exc, 'the response looked like a feed')}; "
                               f"read via {result.backend} instead")
        return result
    result.notes.append("detected an RSS/Atom feed by content sniffing")
    return result


def _feed_failure(exc: BaseException, what: str) -> str:
    """One-line reason a feed read failed (credentials scrubbed)."""
    if isinstance(exc, _NotAFeed):
        return f"{what}, but it is not a parseable RSS/Atom feed"
    if isinstance(exc, WebLensError):
        reason = exc.one_line()  # e.g. "feedparser not installed: pip install feedparser"
    else:
        reason = describe_exception(exc, "feed read").message.removeprefix("feed read failed: ")
    return f"{what}, but reading it as a feed failed ({scrub_url_credentials(reason)})"


def _read_feed_or_fallback(channel: Channel, url: str, config: Any,
                           max_chars: int | None) -> ReadResult:
    """Feed-shaped URL: feedparser; on *any* failure, the non-feed route + a note."""
    try:
        return _read_rss(channel, url, config)
    except Exception as exc:
        failure = _feed_failure(exc, "the URL looks like a feed")
    fallback = route(url, feeds=False)
    result = (_read_web(url, config) if fallback.name == "web"
              else _dispatch(fallback, url, config, max_chars))
    result.notes.insert(0, f"{failure}; read via {result.backend or result.source} instead")
    return result


_ADAPTERS: dict[str, Callable[[Any, str, Any], ReadResult]] = {
    "hackernews": _read_hackernews,
    "arxiv": _read_arxiv,
    "stackoverflow": _read_stackoverflow,
    "v2ex": _read_v2ex,
    "youtube": _read_youtube,
    "github": _read_github,
}
_UPSTREAM = {"reddit", "twitter", "bilibili", "xiaohongshu"}

#: URL shapes each native adapter understands; other pages on the same
#: site (listings, profiles, search pages) are read via Jina instead.
_NATIVE_SHAPES: dict[str, Callable[[str], bool]] = {
    "hackernews": lambda u: urlsplit(u).path == "/item" and "id=" in urlsplit(u).query,
    "wikipedia": lambda u: urlsplit(u).path.startswith("/wiki/"),
    "arxiv": lambda u: bool(re.match(r"^/(abs|pdf|html)/.+", urlsplit(u).path)),
    "stackoverflow": lambda u: bool(re.match(r"^/(questions|q)/\d+", urlsplit(u).path)),
    "youtube": lambda u: (
        (urlsplit(u).path == "/watch" and "v=" in urlsplit(u).query)
        or bool(re.match(r"^/(shorts|live|embed)/[\w-]+", urlsplit(u).path))
        or (urlsplit(u).hostname or "").endswith("youtu.be")
    ),
    "github": github_adapter.is_native_url,
}


def read_url(url: str, *, max_chars: int | None = None, config: Any = None) -> ReadResult:
    """Read *url* through the best adapter; raises :class:`WebLensError`."""
    try:
        url = normalize_public_http_url(url)
    except ValueError as exc:
        raise UsageError(f"invalid URL {url!r}", "pass a public http(s) URL") from exc
    if max_chars is not None and max_chars <= 0:
        raise UsageError("--max-chars must be positive", "e.g. --max-chars 20000")

    channel = route(url)
    name = channel.name
    try:
        if name == "rss":
            result = _read_feed_or_fallback(channel, url, config, max_chars)
        else:
            result = _dispatch(channel, url, config, max_chars)
    except WebLensError:
        raise
    except Exception as exc:
        raise describe_exception(exc, f"reading {name} URL") from exc
    return result.truncate(max_chars)


def _dispatch(channel: Channel, url: str, config: Any, max_chars: int | None) -> ReadResult:
    """Read *url* with a non-feed channel (native adapter, upstream CLI or Jina)."""
    name = channel.name
    if name == "github" and github_adapter.is_site_page(url):
        return _read_web(url, config)  # github.com/features/…, /topics/…: plain web pages
    if not _is_native(name, url) and name in _NATIVE_SHAPES:
        result = _read_web(url, config)
        result.notes.insert(0, f"this {name} page type has no native reader; read via Jina Reader")
        result.source = name
        return result
    if name == "wikipedia":
        return _read_wikipedia(channel, url, config, max_chars)
    if name in _ADAPTERS:
        return _ADAPTERS[name](channel, url, config)
    if name in _UPSTREAM:
        return _read_via_upstream(channel, url, config)
    if name == "web":
        return _read_web_or_feed(url, config)
    result = _read_web(url, config)
    result.notes.insert(
        0, f"{name} has no built-in reader; read via Jina Reader — for full content "
           f"use its upstream tool (see `weblens doctor`)"
    )
    result.source = name
    return result
