"""``weblens search <query>``: one source, or ``all`` fanned out in parallel."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from weblens.channels import get_channel

from . import github as github_adapter
from . import upstream
from . import youtube as youtube_adapter
from .errors import ToolMissingError, UsageError, WebLensError, describe_exception
from .models import SearchResponse, SearchResult

SOURCES = (
    "web", "hackernews", "wikipedia", "arxiv", "stackoverflow", "youtube",
    "github", "v2ex", "reddit", "twitter", "all",
)
ALL_SOURCES = ("web", "hackernews", "wikipedia", "stackoverflow", "arxiv")
MAX_LIMIT = 50
_SNIPPET = 300

#: (results, notes) — every source adapter returns this.
Found = tuple[list[SearchResult], list[str]]


class _Unavailable(WebLensError):
    """A source's backend is not usable (triggers a documented fallback)."""


def _clip(text: Any, n: int = _SNIPPET) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _clean(extra: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in extra.items() if v not in (None, "", [])}


def _date(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _channel(name: str) -> Any:
    channel = get_channel(name)
    if channel is None:  # pragma: no cover - registry is static
        raise WebLensError(f"channel {name} is not registered", "reinstall weblens")
    return channel


# --------------------------------------------------------------------------- #
# Web (Exa via mcporter)
# --------------------------------------------------------------------------- #

def parse_exa_text(text: str) -> list[SearchResult]:
    results = []
    for block in re.split(r"\n-{3,}\n", text or ""):
        fields: dict[str, str] = {}
        highlights: list[str] = []
        in_highlights = False
        for line in block.strip().splitlines():
            if in_highlights:
                highlights.append(line)
                continue
            key, sep, value = line.partition(":")
            if sep and key in ("Title", "URL", "Published", "Author"):
                fields[key] = value.strip()
            elif line.startswith("Highlights:") or line.startswith("Text:"):
                in_highlights = True
                rest = line.partition(":")[2].strip()
                if rest:
                    highlights.append(rest)
        if not fields.get("URL"):
            continue
        title = fields.get("Title", "")
        body = [h for h in highlights if h.strip() and h.strip() not in (title, "...")]
        body = [h.lstrip("# ").strip() for h in body if h.lstrip("# ").strip() != title]
        results.append(SearchResult(
            title=title, url=fields["URL"], source="web", snippet=_clip(" ".join(body)),
            extra=_clean({k.lower(): v for k, v in fields.items()
                          if k in ("Published", "Author") and v != "N/A"}),
        ))
    return results


def exa_search(query: str, limit: int, run: Callable[..., Any] | None = None) -> list[SearchResult]:
    run = run or upstream.run
    try:
        proc = run(
            ["mcporter", "call", "exa.web_search_exa",
             "--args", json.dumps({"query": query, "numResults": limit}),
             "--output", "json", "--timeout", "45000"],
            timeout=60,
        )
    except ToolMissingError as exc:
        raise _Unavailable(exc.message, exc.hint) from exc
    if not proc.ok:
        raise _Unavailable(
            f"Exa search via mcporter failed ({upstream.last_error_line(proc.stderr or proc.stdout)})",
            "mcporter config add exa https://mcp.exa.ai/mcp --scope home",
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"content": [{"type": "text", "text": proc.stdout}]}
    if isinstance(payload, dict) and payload.get("isError"):
        raise _Unavailable("Exa returned an error", "check `mcporter list exa`")
    texts = [c.get("text", "") for c in (payload.get("content") or []) if isinstance(c, dict)] \
        if isinstance(payload, dict) else []
    return parse_exa_text("\n---\n".join(texts))[:limit]


def _search_web(query: str, limit: int, *, fallback: bool = True) -> Found:
    try:
        return exa_search(query, limit), []
    except _Unavailable as exc:
        if not fallback:
            raise
        note = (f"web search unavailable ({exc.one_line()}); "
                "fell back to hackernews + wikipedia")
    results: list[SearchResult] = []
    notes = [note]
    for name in ("hackernews", "wikipedia"):
        try:
            found, extra_notes = _simple(name)(query, limit)
            results += found
            notes += extra_notes
        except Exception as exc:  # keep the other half
            notes.append(f"{name} failed: {describe_exception(exc, name).one_line()}")
    return results, notes


# --------------------------------------------------------------------------- #
# Built-in public API sources
# --------------------------------------------------------------------------- #

def _search_hackernews(query: str, limit: int) -> Found:
    hits = _channel("hackernews").search(query, limit=limit)
    return [SearchResult(
        title=h.get("title", ""), url=h.get("url") or h.get("hn_url", ""), source="hackernews",
        snippet=_clip(h.get("text")),
        extra=_clean({"points": h.get("points"), "comments": h.get("comments_count"),
                      "author": h.get("author"), "date": (h.get("created_at") or "")[:10],
                      "hn_url": h.get("hn_url")}),
    ) for h in hits], []


def _search_wikipedia(query: str, limit: int) -> Found:
    hits = _channel("wikipedia").search(query, limit=limit)
    return [SearchResult(
        title=h.get("title", ""), url=h.get("url", ""), source="wikipedia",
        snippet=_clip(h.get("snippet")),
        extra=_clean({"words": h.get("wordcount"), "date": (h.get("timestamp") or "")[:10]}),
    ) for h in hits], []


def _search_arxiv(query: str, limit: int) -> Found:
    hits = _channel("arxiv").search(query, limit=limit)
    out = []
    for h in hits:
        authors = h.get("authors") or []
        out.append(SearchResult(
            title=h.get("title", ""), url=h.get("url", ""), source="arxiv",
            snippet=_clip(h.get("summary")),
            extra=_clean({"author": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                          "date": (h.get("published") or "")[:10],
                          "category": h.get("primary_category"), "pdf": h.get("pdf_url")}),
        ))
    return out, []


def _search_stackoverflow(query: str, limit: int) -> Found:
    hits = _channel("stackoverflow").search(query, limit=limit)
    return [SearchResult(
        title=h.get("title", ""), url=h.get("url", ""), source="stackoverflow",
        snippet=", ".join(h.get("tags") or []),
        extra=_clean({"score": h.get("score"), "answers": h.get("answer_count"),
                      "answered": h.get("is_answered"), "author": h.get("author"),
                      "date": _date(h.get("creation_date"))}),
    ) for h in hits], []


def _search_youtube(query: str, limit: int, config: Any = None) -> Found:
    return youtube_adapter.search(query, limit, config=config), []


def _search_github(query: str, limit: int, config: Any = None) -> Found:
    return github_adapter.search(query, limit, config=config)


# --------------------------------------------------------------------------- #
# Sources without a search API / upstream-CLI sources
# --------------------------------------------------------------------------- #

def _site_search(query: str, limit: int, site: str, source: str, why: str) -> Found:
    try:
        results = exa_search(f"site:{site} {query}", limit)
    except _Unavailable as exc:
        raise WebLensError(
            f"{source} search unavailable: {why}",
            f"install a {source} backend (see `weblens doctor`) or configure Exa: "
            "mcporter config add exa https://mcp.exa.ai/mcp --scope home",
        ) from exc
    for r in results:
        r.source = source
    return results, [f"{why}; used Exa web search restricted to site:{site}"]


def _search_v2ex(query: str, limit: int) -> Found:
    return _site_search(query, limit, "v2ex.com", "v2ex", "V2EX has no public search API")


def upstream_search_argv(source: str, backend: str, query: str, limit: int) -> list[str] | None:
    """Documented upstream search command for (source, active backend)."""
    if source == "reddit":
        if backend == "OpenCLI":
            return ["opencli", "reddit", "search", query, "-f", "yaml"]
        if backend == "rdt-cli":
            return ["rdt", "search", query, "--limit", str(limit), "--yaml"]
    if source == "twitter":
        if backend == "twitter-cli":
            return ["twitter", "search", query, "-n", str(limit), "--yaml"]
        if backend == "OpenCLI":
            return ["opencli", "twitter", "search", query, "-f", "yaml"]
    return None


_LIST_KEYS = ("results", "items", "data", "posts", "tweets", "list")


def results_from_structured(data: Any, source: str, limit: int) -> list[SearchResult]:
    """Map loosely-structured CLI output (YAML/JSON) onto SearchResult."""
    items = data
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                items = data[key]
                break
    if not isinstance(items, list):
        return []
    out = []
    for it in items[:limit]:
        if not isinstance(it, dict):
            continue
        text = it.get("text") or it.get("full_text") or it.get("selftext") or it.get("content") or ""
        author = it.get("author") or it.get("user") or it.get("screen_name") or ""
        if isinstance(author, dict):
            author = author.get("screen_name") or author.get("name") or author.get("username") or ""
        url = it.get("url") or it.get("link") or it.get("permalink") or ""
        if url.startswith("/r/"):
            url = "https://www.reddit.com" + url
        out.append(SearchResult(
            title=_clip(it.get("title") or text, 120), url=url, source=source,
            snippet=_clip(text) if it.get("title") else "",
            extra=_clean({"author": author, "score": it.get("score") or it.get("likes"),
                          "comments": it.get("num_comments") or it.get("replies"),
                          "date": it.get("created_at") or it.get("created") or it.get("date")}),
        ))
    return out


def _search_upstream(source: str, query: str, limit: int, config: Any) -> Found:
    channel = _channel(source)
    try:
        channel.check(config)
    except Exception:
        channel.active_backend = None
    backend = channel.active_backend or ""
    argv = upstream_search_argv(source, backend, query, limit) if backend else None
    if argv is None:
        site = {"reddit": "reddit.com", "twitter": "x.com"}[source]
        return _site_search(query, limit, site, source, f"no working {source} backend")
    env = None
    if source == "twitter":
        from weblens.channels.twitter import twitter_cli_child_env

        env = twitter_cli_child_env(config)
    proc = upstream.run(argv, timeout=120, env=env)
    if not proc.ok:
        raise WebLensError(
            f"{argv[0]} search failed ({upstream.last_error_line(proc.stderr or proc.stdout)})",
            "check login/health with `weblens doctor`",
        )
    results = results_from_structured(upstream.parse_structured(proc.stdout), source, limit)
    notes = [f"{source} backend: {backend}"]
    if not results and proc.stdout.strip():
        results = [SearchResult(title=f"{source} results (raw {backend} output)", url="",
                                source=source, snippet=proc.stdout.strip()[:4000])]
    return results, notes


def _simple(source: str) -> Callable[[str, int], Found]:
    """Look adapters up at call time (keeps them patchable in tests)."""
    fn: Callable[[str, int], Found] = globals()[f"_search_{source}"]
    return fn


def _run_source(source: str, query: str, limit: int, config: Any, *, in_all: bool = False) -> Found:
    if source == "web":
        return _search_web(query, limit, fallback=not in_all)
    if source in ("reddit", "twitter"):
        return _search_upstream(source, query, limit, config)
    if source in ("youtube", "github"):
        # Config-aware adapters (saved YouTube cookie browser / GitHub token).
        adapter: Callable[[str, int, Any], Found] = globals()[f"_search_{source}"]
        return adapter(query, limit, config)
    return _simple(source)(query, limit)


def search(query: str, source: str = "web", limit: int = 10, *, config: Any = None,
           max_workers: int = 5) -> SearchResponse:
    """Run a search; raises :class:`WebLensError` (UsageError for bad input)."""
    query = " ".join((query or "").split())
    if not query:
        raise UsageError("empty search query", 'e.g. weblens search "rust async"')
    if query.startswith("-"):
        raise UsageError("query must not start with '-'", "rephrase or quote differently")
    source = (source or "web").lower()
    if source not in SOURCES:
        raise UsageError(f"unknown source {source!r}", f"choose one of: {', '.join(SOURCES)}")
    if not 1 <= int(limit) <= MAX_LIMIT:
        raise UsageError(f"--limit must be 1-{MAX_LIMIT}", "e.g. --limit 10")

    response = SearchResponse(query=query, source=source)
    if source != "all":
        response.sources = [source]
        try:
            results, notes = _run_source(source, query, limit, config)
        except WebLensError:
            raise
        except Exception as exc:
            raise describe_exception(exc, f"{source} search") from exc
        response.results, response.notes = results, notes
        return response

    response.sources = list(ALL_SOURCES)

    def _one(name: str) -> tuple[str, Found | None, str]:
        try:
            return name, _run_source(name, query, limit, config, in_all=True), ""
        except Exception as exc:
            return name, None, describe_exception(exc, f"{name} search").one_line()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        outcomes = list(pool.map(_one, ALL_SOURCES))
    for name, found, error in outcomes:
        if found is None:
            response.errors[name] = error
            continue
        response.results.extend(found[0])
        response.notes.extend(found[1])
    if len(response.errors) == len(ALL_SOURCES):
        raise WebLensError("all search sources failed", "; ".join(response.errors.values())[:400])
    return response
