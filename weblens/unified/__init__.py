"""Unified ``read`` / ``search`` layer shared by the CLI and the MCP server.

- :func:`weblens.unified.read.read_url` routes a URL to the most specific
  channel adapter (generic Jina ``web`` last) and returns a :class:`ReadResult`.
- :func:`weblens.unified.search.search` runs one source (or ``all`` in
  parallel) and returns a :class:`SearchResponse` of uniform results.
"""

from .errors import UsageError, WebLensError
from .models import ReadResult, SearchResponse, SearchResult

__all__ = [
    "ReadResult",
    "SearchResponse",
    "SearchResult",
    "UsageError",
    "WebLensError",
]
