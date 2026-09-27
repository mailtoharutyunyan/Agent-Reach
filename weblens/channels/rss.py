"""RSS — check if feedparser is available; recognize feed-shaped URLs."""

from urllib.parse import parse_qsl, urlsplit

from .base import Channel

#: Last path segment endings that name a feed file.
_FEED_SUFFIXES = (".rss", ".xml", ".atom", ".rdf")
#: Whole last path segments that name a feed endpoint (``/feed``, ``/rss/``).
_FEED_LAST_SEGMENTS = frozenset({"feed", "rss", "atom"})
#: First path segments under which everything is a feed (``/feeds/posts/default``,
#: ``export.arxiv.org/rss/cs.AI``). ``/feed/...`` is deliberately absent: it is
#: an HTML page on many sites (e.g. LinkedIn posts under ``/feed/update/``).
_FEED_DIR_SEGMENTS = frozenset({"feeds", "rss"})
#: Leftmost host labels of dedicated feed hosts (``rss.arxiv.org``, ``feeds.feedburner.com``).
_FEED_HOST_LABELS = frozenset({"rss", "feeds"})
#: Query parameters that select a feed rendering (``?format=rss``, WordPress ``?feed=rss2``).
_FEED_QUERY = {
    "format": frozenset({"rss", "atom", "rss2"}),
    "feed": frozenset({"rss", "rss2", "atom", "rdf"}),
}


def is_feed_url(url: str) -> bool:
    """Whether *url* is shaped like an RSS/Atom feed (strict; no substring matching).

    Content sniffing (``weblens.unified.read.looks_like_feed``) covers feeds
    whose URLs do not look like feeds, so this errs on the side of False.
    """
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except (TypeError, ValueError):
        return False
    if parts.scheme.lower() not in {"http", "https"} or not host:
        return False
    if host.count(".") >= 2 and host.split(".", 1)[0] in _FEED_HOST_LABELS:
        return True
    segments = [s for s in parts.path.lower().split("/") if s]
    if segments:
        last = segments[-1]
        if last in _FEED_LAST_SEGMENTS or last.endswith(_FEED_SUFFIXES):
            return True
        if len(segments) > 1 and segments[0] in _FEED_DIR_SEGMENTS:
            return True
    return any(
        value.strip().lower() in _FEED_QUERY.get(key.lower(), ())
        for key, value in parse_qsl(parts.query)
    )


class RSSChannel(Channel):
    name = "rss"
    description = "RSS/Atom feeds"
    backends = ["feedparser"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return is_feed_url(url)

    def check(self, config=None):
        try:
            import feedparser  # noqa: F401
        except ImportError:
            self.active_backend = None
            return "off", "feedparser is not installed. Install: pip install feedparser"
        except Exception as e:
            # Installed but crashes on import (partial install/version conflict) -> suggest reinstall
            self.active_backend = None
            return "error", f"feedparser import failed: {e}\nFix: pip install --force-reinstall feedparser"
        self.active_backend = self.backends[0]
        return "ok", "Can read RSS/Atom feeds"
