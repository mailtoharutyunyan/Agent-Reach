"""Wikipedia — REST summary API + MediaWiki action API (search, plain-text article)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote, urlencode, urlsplit

from weblens.utils.url import host_matches

from . import _http
from .base import Channel

_TIMEOUT = 15
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_LIMIT = 50
#: Wikipedia language/project subdomains: ``en``, ``simple``, ``zh-min-nan``,
#: ``be-tarask``, ``roa-rup``, ... API calls stay pinned to ``{lang}.wikipedia.org``.
_LANG_RE = re.compile(r"^[a-z][a-z0-9-]{1,19}$")
#: Hosts that are not a language edition; read as English.
_DEFAULT_LANG_HOSTS = frozenset({"wikipedia.org", "www.wikipedia.org", "m.wikipedia.org"})
_NOT_LANGS = frozenset({"www"})


def _validate_lang(lang: str) -> str:
    lang = (lang or "en").strip().lower()
    if not _LANG_RE.match(lang) or lang in _NOT_LANGS:
        raise ValueError(f"invalid Wikipedia language code: {lang!r}")
    return lang


def _lang_from_host(host: str) -> str:
    """``simple.wikipedia.org`` / ``simple.m.wikipedia.org`` → ``simple``; bare → ``en``."""
    host = host.lower().rstrip(".")
    if host in _DEFAULT_LANG_HOSTS:
        return "en"
    labels = host.split(".")
    if labels[-2:] != ["wikipedia", "org"] or len(labels) not in (3, 4) \
            or (len(labels) == 4 and labels[1] != "m"):
        raise ValueError(f"unsupported Wikipedia host: {host!r}")
    return _validate_lang(labels[0])


def _base(lang: str) -> str:
    return f"https://{lang}.wikipedia.org"


def _get_json(url: str, lang: str) -> Any:
    return _http.get_json(
        url,
        allowed_hosts=frozenset({f"{lang}.wikipedia.org"}),
        timeout=_TIMEOUT,
        max_bytes=_MAX_RESPONSE_BYTES,
    )


def _normalize_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise ValueError("Wikipedia title must not be empty")
    return title


def _page_url(lang: str, title: str) -> str:
    return f"{_base(lang)}/wiki/{quote(title.replace(' ', '_'), safe='')}"


class WikipediaChannel(Channel):
    name = "wikipedia"
    description = "Wikipedia article summaries, full text and search"
    backends = ["Wikipedia REST + MediaWiki API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "wikipedia.org")

    # ------------------------------------------------------------------ #
    # Health check — zero-cost, no network (public keyless API)
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        self.active_backend = self.backends[0]
        return "ok", "Public API (article summaries, plain-text articles, search; any language)"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def get_summary(self, title: str, lang: str = "en") -> dict:
        """Get an article's lead summary (REST page/summary, follows redirects).

        Returns a dict with keys:
          title, description, extract, url, lang, type, thumbnail, timestamp
        ``type`` is "standard", "disambiguation", ... as reported by Wikipedia.
        """
        lang = _validate_lang(lang)
        title = _normalize_title(title)
        encoded = quote(title.replace(" ", "_"), safe="")
        data = _get_json(f"{_base(lang)}/api/rest_v1/page/summary/{encoded}", lang) or {}
        canonical = data.get("title", title)
        return {
            "title": canonical,
            "description": data.get("description", ""),
            "extract": data.get("extract", ""),
            "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
            or _page_url(lang, canonical),
            "lang": lang,
            "type": data.get("type", ""),
            "thumbnail": (data.get("thumbnail") or {}).get("source", ""),
            "timestamp": data.get("timestamp", ""),
        }

    def get_article(self, title: str, lang: str = "en", max_chars: int = 50000) -> dict:
        """Get the full article as plain text (MediaWiki prop=extracts).

        Returns a dict with keys: title, url, lang, text, truncated
        """
        lang = _validate_lang(lang)
        title = _normalize_title(title)
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
            "format": "json",
            "formatversion": 2,
        }
        data = _get_json(f"{_base(lang)}/w/api.php?{urlencode(params)}", lang) or {}
        pages = (data.get("query") or {}).get("pages") or []
        page = pages[0] if pages else {}
        if not page or page.get("missing"):
            raise ValueError(f"Wikipedia ({lang}) has no article titled {title!r}")
        canonical = page.get("title", title)
        text = page.get("extract", "") or ""
        limit = max(1, int(max_chars))
        return {
            "title": canonical,
            "url": _page_url(lang, canonical),
            "lang": lang,
            "text": text[:limit],
            "truncated": len(text) > limit,
        }

    def search(self, query: str, lang: str = "en", limit: int = 10) -> list[dict]:
        """Full-text search (MediaWiki action=query&list=search).

        Returns a list of dicts with keys:
          title, pageid, snippet, url, wordcount, timestamp
        """
        lang = _validate_lang(lang)
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max(1, min(int(limit), _MAX_LIMIT)),
            "format": "json",
            "formatversion": 2,
        }
        data = _get_json(f"{_base(lang)}/w/api.php?{urlencode(params)}", lang) or {}
        results = []
        for hit in (data.get("query") or {}).get("search") or []:
            title = hit.get("title", "")
            results.append(
                {
                    "title": title,
                    "pageid": hit.get("pageid", 0),
                    "snippet": _http.html_to_text(hit.get("snippet")),
                    "url": _page_url(lang, title),
                    "wordcount": hit.get("wordcount", 0),
                    "timestamp": hit.get("timestamp", ""),
                }
            )
        return results

    def read(self, url: str, max_chars: int = 50000) -> dict:
        """Read a https://<lang>.wikipedia.org/wiki/<Title> URL as plain text."""
        if not self.can_handle(url):
            raise ValueError("not a Wikipedia URL")
        parsed = urlsplit(url)
        lang = _lang_from_host(parsed.hostname or "")
        if not parsed.path.startswith("/wiki/"):
            raise ValueError("Wikipedia URL must look like /wiki/<Title>")
        title = unquote(parsed.path[len("/wiki/"):]).replace("_", " ")
        return self.get_article(title, lang=lang, max_chars=max_chars)
