"""
WebLens MCP Server — expose status, read and search as MCP tools.

Run: python -m weblens.integrations.mcp_server

Tools:
  - get_status: doctor report
  - read(url, max_chars?, format?): same code path as `weblens read`
  - search(query, source?, limit?, format?): same code path as `weblens search`

All three do blocking network/subprocess work, so they run in a worker thread
(``asyncio.to_thread``) and never stall the server's event loop. Failures are
raised as :class:`ToolError`; every ``mcp`` SDK release (1.0 through current)
turns an exception raised by a ``call_tool`` handler into a ``CallToolResult``
with ``isError=True`` and the exception text as its content.
"""

import asyncio
import json
import sys

from weblens.config import Config
from weblens.core import WebLens
from weblens.unified.errors import describe_exception
from weblens.unified.read import read_url
from weblens.unified.render import render_read, render_search
from weblens.unified.search import MAX_LIMIT, SOURCES
from weblens.unified.search import search as run_search
from weblens.utils.text import scrub_url_credentials

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


class ToolError(Exception):
    """A tool failure with a one-line, credential-scrubbed ``Error: …`` message.

    Raised out of the ``call_tool`` handler so the MCP SDK reports it as an
    error result (``isError=True``) rather than as ordinary tool output.
    """


def _want_json(arguments: dict) -> bool:
    return str(arguments.get("format") or "markdown").lower() == "json"


def tool_read(arguments: dict, config=None) -> str | dict:
    """MCP `read` tool body (sync; runs in a worker thread). Raises :class:`ToolError`."""
    try:
        max_chars = arguments.get("max_chars")
        result = read_url(
            str(arguments.get("url") or ""),
            max_chars=int(max_chars) if max_chars is not None else None,
            config=config,
        )
    except Exception as exc:
        raise ToolError(f"Error: {describe_exception(exc, 'read').one_line()}") from exc
    return result.to_dict() if _want_json(arguments) else render_read(result)


def tool_search(arguments: dict, config=None) -> str | dict:
    """MCP `search` tool body (sync; runs in a worker thread). Raises :class:`ToolError`."""
    try:
        response = run_search(
            str(arguments.get("query") or ""),
            source=str(arguments.get("source") or "web"),
            limit=int(arguments.get("limit") or 10),
            config=config,
        )
    except Exception as exc:
        raise ToolError(f"Error: {describe_exception(exc, 'search').one_line()}") from exc
    return response.to_dict() if _want_json(arguments) else render_search(response)


def tool_status(eyes) -> str:
    """MCP `get_status` tool body (sync; runs in a worker thread). Raises :class:`ToolError`."""
    try:
        return eyes.doctor_report()
    except Exception as exc:
        raise ToolError(f"Error: {scrub_url_credentials(exc)}") from exc


def create_server():
    if not HAS_MCP:
        print(
            "MCP not installed. Install: python -m pip install "
            "'weblens[mcp] @ "
            "https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip'",
            file=sys.stderr,
        )
        sys.exit(1)

    server = Server("weblens")
    config = Config(read_only=True)
    eyes = WebLens(config)

    @server.list_tools()
    async def list_tools():
        return [
            Tool(name="get_status",
                 description="Get WebLens status: which channels are installed and active.",
                 inputSchema={"type": "object", "properties": {}}),
            Tool(name="read",
                 description=(
                     "Read any public URL as clean text. Auto-routes Hacker News, Wikipedia, "
                     "arXiv, Stack Overflow, YouTube (metadata + transcript), GitHub "
                     "(repo README / issue / PR), V2EX, RSS/Atom; anything else via Jina Reader."
                 ),
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "url": {"type": "string", "description": "http(s) URL"},
                         "max_chars": {"type": "integer", "minimum": 1,
                                       "description": "Truncate the body to N characters"},
                         "format": {"type": "string", "enum": ["markdown", "json"],
                                    "default": "markdown"},
                     },
                     "required": ["url"],
                 }),
            Tool(name="search",
                 description=(
                     "Search the web (Exa) or one source; source='all' fans out to web, "
                     "hackernews, wikipedia, stackoverflow and arxiv in parallel."
                 ),
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "query": {"type": "string"},
                         "source": {"type": "string", "enum": list(SOURCES), "default": "web"},
                         "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT,
                                   "default": 10},
                         "format": {"type": "string", "enum": ["markdown", "json"],
                                    "default": "markdown"},
                     },
                     "required": ["query"],
                 }),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        result: str | dict
        try:
            if name == "get_status":
                result = await asyncio.to_thread(tool_status, eyes)
            elif name == "read":
                result = await asyncio.to_thread(tool_read, arguments or {}, config)
            elif name == "search":
                result = await asyncio.to_thread(tool_search, arguments or {}, config)
            else:
                raise ToolError(f"Error: unknown tool {name!r}")
        except ToolError:
            raise  # the SDK returns it as CallToolResult(isError=True)
        except Exception as exc:
            raise ToolError(f"Error: {scrub_url_credentials(exc)}") from exc

        text = json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)
        return [TextContent(type="text", text=text)]

    return server


async def main():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
