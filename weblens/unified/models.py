"""Uniform result shapes for ``read`` and ``search``."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ReadResult:
    """One read page/item, rendered as Markdown-ish text or JSON."""

    title: str
    url: str
    source: str  # channel name, e.g. "hackernews", "web"
    body: str = ""
    backend: str = ""  # what actually served it, e.g. "yt-dlp", "Jina Reader"
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    truncated: bool = False

    def truncate(self, max_chars: int | None) -> ReadResult:
        if max_chars is not None and max_chars > 0 and len(self.body) > max_chars:
            self.body = self.body[:max_chars].rstrip() + "\n…"
            self.truncated = True
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    title: str
    url: str
    source: str
    snippet: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # score/date/author/...

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResponse:
    query: str
    source: str  # requested source ("all" for fan-out)
    results: list[SearchResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # source -> one-line error
    sources: list[str] = field(default_factory=list)  # sources actually queried

    def grouped(self) -> dict[str, list[SearchResult]]:
        groups: dict[str, list[SearchResult]] = {name: [] for name in self.sources}
        for result in self.results:
            groups.setdefault(result.source, []).append(result)
        return groups

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "query": self.query,
            "source": self.source,
            "results": [r.to_dict() for r in self.results],
            "notes": list(self.notes),
            "errors": dict(self.errors),
        }
        if self.source == "all":
            data["groups"] = {
                name: [r.to_dict() for r in items] for name, items in self.grouped().items()
            }
        return data
