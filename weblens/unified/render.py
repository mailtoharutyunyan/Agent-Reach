"""Plain Markdown-ish rendering for humans and agents."""

from __future__ import annotations

from typing import Any

from .models import ReadResult, SearchResponse, SearchResult


def _fmt_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int) and abs(value) >= 10000:
        return f"{value:,}"
    return str(value)


def render_read(result: ReadResult) -> str:
    lines = [f"# {result.title or result.url}", ""]
    source = result.source + (f" via {result.backend}" if result.backend else "")
    lines.append(f"- source: {source}")
    lines.append(f"- url: {result.url}")
    for key, value in result.metadata.items():
        text = _fmt_value(value).replace("\n", " ")
        lines.append(f"- {key}: {text}")
    for note in result.notes:
        lines.append(f"- note: {note}")
    if result.truncated:
        lines.append("- truncated: yes")
    body = result.body.strip()
    if body:
        lines += ["", body]
    return "\n".join(lines) + "\n"


def _render_result(index: int, r: SearchResult) -> list[str]:
    lines = [f"{index}. {r.title or '(untitled)'}"]
    if r.url:
        lines.append(f"   {r.url}")
    if r.extra:
        lines.append("   " + " · ".join(f"{k}: {_fmt_value(v)}" for k, v in r.extra.items()
                                        if k not in ("hn_url", "pdf")))
    if r.snippet:
        lines.append(f"   {r.snippet}")
    return lines


def render_search(response: SearchResponse) -> str:
    lines = [f'# Search: "{response.query}" (source: {response.source})', ""]
    for note in response.notes:
        lines.append(f"- note: {note}")
    if response.notes:
        lines.append("")
    if response.source == "all":
        for name, items in response.grouped().items():
            lines.append(f"## {name} ({len(items)})")
            if name in response.errors:
                lines.append(f"   error: {response.errors[name]}")
            elif not items:
                lines.append("   no results")
            for i, r in enumerate(items, 1):
                lines += _render_result(i, r)
            lines.append("")
    else:
        if not response.results:
            lines.append("No results.")
        for i, r in enumerate(response.results, 1):
            lines += _render_result(i, r)
    return "\n".join(lines).rstrip() + "\n"
