"""Hacker News — official Firebase API (stories/items/users) + Algolia (search)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from weblens.utils.url import host_matches

from . import _http
from .base import Channel

_FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
_ALLOWED_HOSTS = frozenset({"hacker-news.firebaseio.com", "hn.algolia.com"})
_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_WORKERS = 8
_MAX_LIMIT = 100
_STORY_KINDS = {"top", "new", "best", "ask", "show", "job"}
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _get_json(url: str) -> Any:
    return _http.get_json(
        url,
        allowed_hosts=_ALLOWED_HOSTS,
        timeout=_TIMEOUT,
        max_bytes=_MAX_RESPONSE_BYTES,
    )


def _item_id(value: int | str) -> int:
    try:
        item_id = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"invalid Hacker News item id: {value!r}") from exc
    if item_id <= 0:
        raise ValueError(f"invalid Hacker News item id: {value!r}")
    return item_id


def _clamp(limit: int, maximum: int = _MAX_LIMIT) -> int:
    return max(1, min(int(limit), maximum))


def _hn_url(item_id: int | str) -> str:
    return f"https://news.ycombinator.com/item?id={quote(str(item_id), safe='')}"


def _fetch_item(item_id: int) -> dict:
    data = _get_json(f"{_FIREBASE_BASE}/item/{item_id}.json")
    return data if isinstance(data, dict) else {}


def _fetch_items(ids: list[int]) -> list[dict]:
    """Fetch items concurrently, preserving order and skipping failures."""
    if not ids:
        return []

    def _safe(item_id: int) -> dict:
        try:
            return _fetch_item(item_id)
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(ids))) as pool:
        return list(pool.map(_safe, ids))


def _shape_story(item: dict) -> dict:
    item_id = item.get("id", 0)
    return {
        "id": item_id,
        "title": item.get("title", ""),
        "url": item.get("url") or _hn_url(item_id),
        "hn_url": _hn_url(item_id),
        "score": item.get("score", 0),
        "comments_count": item.get("descendants", 0),
        "author": item.get("by", ""),
        "time": item.get("time", 0),
        "type": item.get("type", ""),
        "text": _http.html_to_text(item.get("text")),
    }


def _shape_comment(item: dict, depth: int, parent: int) -> dict:
    return {
        "id": item.get("id", 0),
        "parent": parent,
        "depth": depth,
        "author": item.get("by", ""),
        "text": _http.html_to_text(item.get("text")),
        "time": item.get("time", 0),
    }


class HackerNewsChannel(Channel):
    name = "hackernews"
    description = "Hacker News stories, comments and search"
    backends = ["HN Firebase API + Algolia (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "news.ycombinator.com")

    # ------------------------------------------------------------------ #
    # Health check — zero-cost, no network (public keyless API)
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        self.active_backend = self.backends[0]
        return "ok", "Public API (top/new/best stories, items + comments, Algolia search)"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def get_stories(self, kind: str = "top", limit: int = 20) -> list[dict]:
        """List front-page stories.

        Args:
            kind:  one of top, new, best, ask, show, job
            limit: max stories (1-100)

        Returns a list of dicts with keys:
          id, title, url, hn_url, score, comments_count, author, time, type, text
        """
        kind = (kind or "top").lower()
        if kind not in _STORY_KINDS:
            raise ValueError(f"kind must be one of {', '.join(sorted(_STORY_KINDS))}")
        ids = _get_json(f"{_FIREBASE_BASE}/{kind}stories.json") or []
        ids = [i for i in ids if isinstance(i, int)][: _clamp(limit)]
        return [_shape_story(item) for item in _fetch_items(ids) if item]

    def get_item(
        self,
        item_id: int | str,
        comment_limit: int = 50,
        max_depth: int = 2,
    ) -> dict:
        """Get a story (or any item) with its comment tree, breadth-first.

        Args:
            item_id:       HN item id (from news.ycombinator.com/item?id=<id>)
            comment_limit: max comments fetched in total (0-200)
            max_depth:     comment nesting depth to walk (1 = top-level only)

        Returns the story dict (see get_stories) plus ``comments``: a flat list of
        dicts with keys id, parent, depth, author, text, time — deleted/dead
        comments are skipped.
        """
        iid = _item_id(item_id)
        item = _fetch_item(iid)
        if not item:
            raise ValueError(f"Hacker News item {iid} not found")
        result = _shape_story(item)
        result["parent"] = item.get("parent")

        budget = max(0, min(int(comment_limit), 200))
        comments: list[dict] = []
        frontier: list[tuple[int, int, int]] = [
            (kid, 1, iid) for kid in item.get("kids") or []
        ]
        while frontier and budget > 0:
            # Frontier is kept in breadth-first order: children are appended
            # after all of the current level, so shallow comments win the budget.
            batch, frontier = frontier[:budget], frontier[budget:]
            fetched = _fetch_items([kid for kid, _d, _p in batch])
            for (kid, depth, parent), child in zip(batch, fetched, strict=True):
                if not child or child.get("deleted") or child.get("dead"):
                    continue
                comments.append(_shape_comment(child, depth, parent))
                budget -= 1
                if depth < max_depth:
                    frontier.extend((k, depth + 1, kid) for k in child.get("kids") or [])
        result["comments"] = comments
        return result

    def get_user(self, username: str) -> dict:
        """Get a user profile: id, karma, about, created, submitted_count."""
        if not _USERNAME_RE.match(username or ""):
            raise ValueError(f"invalid Hacker News username: {username!r}")
        data = _get_json(f"{_FIREBASE_BASE}/user/{quote(username, safe='')}.json")
        if not isinstance(data, dict):
            raise ValueError(f"Hacker News user {username!r} not found")
        return {
            "id": data.get("id", username),
            "karma": data.get("karma", 0),
            "about": _http.html_to_text(data.get("about")),
            "created": data.get("created", 0),
            "submitted_count": len(data.get("submitted") or []),
            "url": f"https://news.ycombinator.com/user?id={quote(username, safe='')}",
        }

    def search(
        self,
        query: str,
        limit: int = 10,
        sort: str = "relevance",
        tags: str = "story",
    ) -> list[dict]:
        """Full-text search via Algolia HN Search.

        Args:
            query: search terms
            limit: max hits (1-100)
            sort:  "relevance" (default) or "date" (newest first)
            tags:  Algolia tag filter: story, comment, ask_hn, show_hn, poll, ...
                   or "" for everything

        Returns a list of dicts with keys:
          id, title, url, hn_url, points, comments_count, author, created_at, text
        """
        endpoint = "search_by_date" if sort == "date" else "search"
        params: dict[str, Any] = {"query": query, "hitsPerPage": _clamp(limit)}
        if tags:
            params["tags"] = tags
        data = _get_json(f"{_ALGOLIA_BASE}/{endpoint}?{urlencode(params)}") or {}
        results = []
        for hit in data.get("hits") or []:
            object_id = hit.get("objectID", "")
            results.append(
                {
                    "id": int(object_id) if str(object_id).isdigit() else object_id,
                    "title": hit.get("title") or hit.get("story_title") or "",
                    "url": hit.get("url") or hit.get("story_url") or _hn_url(object_id),
                    "hn_url": _hn_url(object_id),
                    "points": hit.get("points") or 0,
                    "comments_count": hit.get("num_comments") or 0,
                    "author": hit.get("author", ""),
                    "created_at": hit.get("created_at", ""),
                    "text": _http.html_to_text(hit.get("story_text") or hit.get("comment_text")),
                }
            )
        return results

    def read(self, url: str) -> dict:
        """Read a news.ycombinator.com item URL (story + comments)."""
        if not self.can_handle(url):
            raise ValueError("not a Hacker News URL")
        ids = parse_qs(urlsplit(url).query).get("id") or []
        if not ids:
            raise ValueError("Hacker News URL has no ?id=<item id>")
        return self.get_item(ids[0])
