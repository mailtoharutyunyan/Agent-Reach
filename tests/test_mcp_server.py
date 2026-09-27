"""Security boundaries for the optional WebLens MCP server."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

import weblens.integrations.mcp_server as mcp_server


class _FakeServer:
    def __init__(self, name):
        self.name = name
        self.list_tools_handler = None
        self.call_tool_handler = None

    def list_tools(self):
        def register(handler):
            self.list_tools_handler = handler
            return handler

        return register

    def call_tool(self):
        def register(handler):
            self.call_tool_handler = handler
            return handler

        return register


def _install_fake_mcp(monkeypatch):
    monkeypatch.setattr(mcp_server, "HAS_MCP", True)
    monkeypatch.setattr(mcp_server, "Server", _FakeServer, raising=False)
    monkeypatch.setattr(
        mcp_server,
        "Tool",
        lambda **kwargs: SimpleNamespace(**kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        mcp_server,
        "TextContent",
        lambda **kwargs: SimpleNamespace(**kwargs),
        raising=False,
    )


def test_mcp_status_uses_read_only_config(monkeypatch):
    _install_fake_mcp(monkeypatch)
    created_configs = []

    class _RecordingConfig:
        def __init__(self, *, read_only=False):
            self.read_only = read_only
            created_configs.append(self)

    class _WebLens:
        def __init__(self, config):
            self.config = config

        def doctor_report(self):
            return "ok"

    monkeypatch.setattr(mcp_server, "Config", _RecordingConfig)
    monkeypatch.setattr(mcp_server, "WebLens", _WebLens)

    server = mcp_server.create_server()
    result = asyncio.run(server.call_tool_handler("get_status", {}))

    assert len(created_configs) == 1
    assert created_configs[0].read_only is True
    assert result[0].text == "ok"


def test_mcp_status_exception_credentials_are_scrubbed(monkeypatch):
    _install_fake_mcp(monkeypatch)

    class _Config:
        def __init__(self, *, read_only=False):
            self.read_only = read_only

    class _ExplodingWebLens:
        def __init__(self, config):
            self.config = config

        def doctor_report(self):
            raise RuntimeError(
                "request https://alice:password@example.test/data"
                "?token=top-secret failed"
            )

    monkeypatch.setattr(mcp_server, "Config", _Config)
    monkeypatch.setattr(mcp_server, "WebLens", _ExplodingWebLens)

    server = mcp_server.create_server()
    with pytest.raises(mcp_server.ToolError) as info:
        asyncio.run(server.call_tool_handler("get_status", {}))
    text = str(info.value)

    assert text.startswith("Error: ")
    assert "alice" not in text
    assert "password" not in text
    assert "top-secret" not in text
    assert "https://***@example.test/data?token=***" in text


# --- read / search tools --------------------------------------------------------


def _server_with_fakes(monkeypatch):
    _install_fake_mcp(monkeypatch)

    class _Config:
        def __init__(self, *, read_only=False):
            self.read_only = read_only

    monkeypatch.setattr(mcp_server, "Config", _Config)
    return mcp_server.create_server()


def test_mcp_lists_status_read_and_search_tools(monkeypatch):
    server = _server_with_fakes(monkeypatch)
    tools = asyncio.run(server.list_tools_handler())
    names = [t.name for t in tools]
    assert names == ["get_status", "read", "search"]
    search_schema = tools[2].inputSchema
    assert "all" in search_schema["properties"]["source"]["enum"]
    assert tools[1].inputSchema["required"] == ["url"]


def test_mcp_read_calls_shared_read_path(monkeypatch):
    from weblens.unified.models import ReadResult

    server = _server_with_fakes(monkeypatch)
    seen = {}

    def fake_read_url(url, *, max_chars=None, config=None):
        seen.update(url=url, max_chars=max_chars, read_only=config.read_only)
        return ReadResult(title="T", url=url, source="web", body="B")

    monkeypatch.setattr(mcp_server, "read_url", fake_read_url)
    result = asyncio.run(server.call_tool_handler("read", {"url": "https://example.com", "max_chars": 5}))
    assert seen == {"url": "https://example.com", "max_chars": 5, "read_only": True}
    assert result[0].text.startswith("# T")

    result = asyncio.run(server.call_tool_handler("read", {"url": "https://example.com", "format": "json"}))
    import json as _json

    assert _json.loads(result[0].text)["body"] == "B"


def test_mcp_search_calls_shared_search_path(monkeypatch):
    from weblens.unified.models import SearchResponse, SearchResult

    server = _server_with_fakes(monkeypatch)
    seen = {}

    def fake_search(query, *, source, limit, config=None):
        seen.update(query=query, source=source, limit=limit)
        return SearchResponse(query=query, source=source, sources=[source],
                              results=[SearchResult("A", "https://a", source)])

    monkeypatch.setattr(mcp_server, "run_search", fake_search)
    result = asyncio.run(server.call_tool_handler("search", {"query": "rust", "source": "hackernews", "limit": 3}))
    assert seen == {"query": "rust", "source": "hackernews", "limit": 3}
    assert "1. A" in result[0].text


def test_mcp_tool_errors_are_raised_as_one_line_tool_errors(monkeypatch):
    # Raising from call_tool is what makes the SDK set isError=True.
    server = _server_with_fakes(monkeypatch)
    cases = [
        ("read", {"url": "http://localhost/x"}, "Error: invalid URL"),
        ("search", {"query": "x", "source": "nope"}, "Error: unknown source"),
        ("nope", {}, "Error: unknown tool 'nope'"),
    ]
    for name, arguments, prefix in cases:
        with pytest.raises(mcp_server.ToolError) as info:
            asyncio.run(server.call_tool_handler(name, arguments))
        assert str(info.value).startswith(prefix)
        assert "\n" not in str(info.value)


def test_mcp_blocking_tools_run_off_the_event_loop_thread(monkeypatch):
    from weblens.unified.models import ReadResult, SearchResponse

    _install_fake_mcp(monkeypatch)
    loop_thread = threading.get_ident()
    threads: dict[str, int] = {}

    class _Config:
        def __init__(self, *, read_only=False):
            self.read_only = read_only

    class _WebLens:
        def __init__(self, config):
            pass

        def doctor_report(self):
            threads["get_status"] = threading.get_ident()
            return "ok"

    def fake_read_url(url, *, max_chars=None, config=None):
        threads["read"] = threading.get_ident()
        return ReadResult(title="T", url=url, source="web")

    def fake_search(query, *, source, limit, config=None):
        threads["search"] = threading.get_ident()
        return SearchResponse(query=query, source=source)

    monkeypatch.setattr(mcp_server, "Config", _Config)
    monkeypatch.setattr(mcp_server, "WebLens", _WebLens)
    monkeypatch.setattr(mcp_server, "read_url", fake_read_url)
    monkeypatch.setattr(mcp_server, "run_search", fake_search)
    server = mcp_server.create_server()

    async def call_all():
        assert threading.get_ident() == loop_thread
        await server.call_tool_handler("get_status", {})
        await server.call_tool_handler("read", {"url": "https://example.com"})
        await server.call_tool_handler("search", {"query": "q"})

    asyncio.run(call_all())
    assert set(threads) == {"get_status", "read", "search"}
    assert loop_thread not in threads.values()


def _real_sdk_call(server, name, arguments):
    from mcp import types

    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    return asyncio.run(handler(request)).root


def test_mcp_errors_have_is_error_with_the_real_sdk(monkeypatch):
    pytest.importorskip("mcp")
    if not mcp_server.HAS_MCP:
        pytest.skip("mcp SDK not importable")

    class _Config:
        def __init__(self, *, read_only=False):
            self.read_only = read_only

    class _ExplodingWebLens:
        def __init__(self, config):
            pass

        def doctor_report(self):
            raise RuntimeError("GET https://alice:pw@example.test/x?token=top-secret failed")

    monkeypatch.setattr(mcp_server, "Config", _Config)
    monkeypatch.setattr(mcp_server, "WebLens", _ExplodingWebLens)
    server = mcp_server.create_server()

    result = _real_sdk_call(server, "read", {"url": "http://localhost/x"})
    assert result.isError is True
    assert result.content[0].text.startswith("Error: invalid URL")

    result = _real_sdk_call(server, "get_status", {})
    assert result.isError is True
    assert "top-secret" not in result.content[0].text and "alice" not in result.content[0].text


def test_mcp_success_is_not_an_error_with_the_real_sdk(monkeypatch):
    pytest.importorskip("mcp")
    if not mcp_server.HAS_MCP:
        pytest.skip("mcp SDK not importable")
    from weblens.unified.models import ReadResult

    class _Config:
        def __init__(self, *, read_only=False):
            self.read_only = read_only

    monkeypatch.setattr(mcp_server, "Config", _Config)
    monkeypatch.setattr(mcp_server, "read_url",
                        lambda url, *, max_chars=None, config=None: ReadResult(title="T", url=url,
                                                                               source="web", body="B"))
    server = mcp_server.create_server()
    result = _real_sdk_call(server, "read", {"url": "https://example.com"})
    assert result.isError is False
    assert result.content[0].text.startswith("# T")
