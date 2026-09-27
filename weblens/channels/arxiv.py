"""arXiv — public export API (Atom), parsed with feedparser.

arXiv asks API clients to keep to roughly one request every 3 seconds; each
method here makes exactly one request, so callers looping over many queries
should pace themselves.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode, urlsplit

from weblens.utils.url import host_matches

from . import _http
from .base import Channel

_API_URL = "https://export.arxiv.org/api/query"
_ALLOWED_HOSTS = frozenset({"export.arxiv.org"})
_TIMEOUT = 20
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_LIMIT = 100
_SORTS = {"relevance", "lastUpdatedDate", "submittedDate"}
_FIELD_PREFIX_RE = re.compile(r"\b(?:ti|au|abs|co|jr|cat|rn|id|all):", re.IGNORECASE)
# New-style (2007+) "2401.01234v2" and old-style "hep-th/9901001v1" / "math.GT/0309136".
_ID_RE = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$"
)


def _validate_id(arxiv_id: str) -> str:
    value = (arxiv_id or "").strip()
    if value.lower().startswith("arxiv:"):
        value = value[len("arxiv:"):]
    if not _ID_RE.match(value):
        raise ValueError(f"invalid arXiv id: {arxiv_id!r}")
    return value


def _build_search_query(query: str) -> str:
    """Pass arXiv field syntax through; AND free-text terms across all fields.

    arXiv ORs bare space-separated words, so "retrieval augmented generation"
    would match nearly anything. Quoted phrases are kept as one phrase term.
    """
    if _FIELD_PREFIX_RE.search(query):
        return query
    if '"' in query:
        return f"all:{query}"
    return " AND ".join(f"all:{term}" for term in query.split())


def _fetch_feed(params: dict[str, Any]) -> Any:
    import feedparser

    _status, body = _http.get_bytes(
        f"{_API_URL}?{urlencode(params)}",
        allowed_hosts=_ALLOWED_HOSTS,
        accept="application/atom+xml",
        timeout=_TIMEOUT,
        max_bytes=_MAX_RESPONSE_BYTES,
    )
    return feedparser.parse(body)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _shape_entry(entry: Any) -> dict:
    entry_id = entry.get("id", "") or ""
    short_id = entry_id.rsplit("/abs/", 1)[-1] if "/abs/" in entry_id else entry_id
    pdf_url = ""
    for link in entry.get("links") or []:
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break
    primary = entry.get("arxiv_primary_category") or {}
    return {
        "id": short_id,
        "title": _clean(entry.get("title")),
        "authors": [a.get("name", "") for a in entry.get("authors") or [] if a.get("name")],
        "summary": _clean(entry.get("summary")),
        "published": entry.get("published", ""),
        "updated": entry.get("updated", ""),
        "primary_category": primary.get("term", "") if isinstance(primary, dict) else "",
        "categories": [t.get("term", "") for t in entry.get("tags") or [] if t.get("term")],
        "comment": _clean(entry.get("arxiv_comment")),
        "doi": entry.get("arxiv_doi", ""),
        "url": entry.get("link", "") or f"https://arxiv.org/abs/{short_id}",
        "pdf_url": pdf_url,
    }


def _entries(feed: Any) -> list[dict]:
    results = []
    for entry in feed.get("entries") or []:
        if "api/errors" in (entry.get("id", "") or ""):
            raise ValueError(f"arXiv API error: {_clean(entry.get('summary'))}")
        results.append(_shape_entry(entry))
    return results


class ArxivChannel(Channel):
    name = "arxiv"
    description = "arXiv papers: search and metadata"
    backends = ["arXiv API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "arxiv.org")

    # ------------------------------------------------------------------ #
    # Health check — feedparser import only, no network (like rss)
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        try:
            import feedparser  # noqa: F401
        except ImportError:
            self.active_backend = None
            return "off", "feedparser is not installed. Install: pip install feedparser"
        except Exception as e:
            self.active_backend = None
            return "error", f"feedparser import failed: {e}\nFix: pip install --force-reinstall feedparser"
        self.active_backend = self.backends[0]
        return "ok", "Public API (paper search, metadata/abstract by id)"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        limit: int = 10,
        sort: str = "relevance",
        start: int = 0,
    ) -> list[dict]:
        """Search papers.

        Args:
            query: free text (searched in all fields) or arXiv field syntax,
                   e.g. "ti:transformer AND cat:cs.CL", "au:hinton"
            limit: max results (1-100)
            sort:  relevance | lastUpdatedDate | submittedDate (descending)
            start: result offset for paging

        Returns a list of dicts with keys:
          id, title, authors, summary, published, updated, primary_category,
          categories, comment, doi, url, pdf_url
        """
        query = (query or "").strip()
        if not query:
            raise ValueError("arXiv query must not be empty")
        if sort not in _SORTS:
            raise ValueError(f"sort must be one of {', '.join(sorted(_SORTS))}")
        search_query = _build_search_query(query)
        feed = _fetch_feed(
            {
                "search_query": search_query,
                "start": max(0, int(start)),
                "max_results": max(1, min(int(limit), _MAX_LIMIT)),
                "sortBy": sort,
                "sortOrder": "descending",
            }
        )
        return _entries(feed)

    def get_paper(self, arxiv_id: str) -> dict:
        """Get one paper's metadata + abstract by id (e.g. "1706.03762", "hep-th/9901001v1")."""
        value = _validate_id(arxiv_id)
        results = _entries(_fetch_feed({"id_list": value, "max_results": 1}))
        if not results or not results[0].get("title"):
            raise ValueError(f"arXiv paper {value!r} not found")
        return results[0]

    def read(self, url: str) -> dict:
        """Read an arxiv.org /abs/<id> or /pdf/<id> URL (returns metadata + abstract)."""
        if not self.can_handle(url):
            raise ValueError("not an arXiv URL")
        path = urlsplit(url).path
        for prefix in ("/abs/", "/pdf/", "/html/"):
            if path.startswith(prefix):
                arxiv_id = path[len(prefix):].rstrip("/")
                if arxiv_id.endswith(".pdf"):
                    arxiv_id = arxiv_id[: -len(".pdf")]
                return self.get_paper(arxiv_id)
        raise ValueError("arXiv URL must look like /abs/<id> or /pdf/<id>")
