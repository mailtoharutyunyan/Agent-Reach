# Search Tools

Exa AI search engine.

## Exa AI Search

High-quality AI search engine, well suited for finding technical documentation, official examples, and related web pages.

```bash
mcporter call exa.web_search_exa query="query" numResults=5
mcporter call exa.web_search_exa query="library API code example" numResults=5
```

### Use cases

| Scenario | Parameters |
|-----|------|
| Web search | `web_search_exa(query: "...", numResults: 5)` |
| Technical/code resources | `web_search_exa(query: "framework name API example", numResults: 5)` |

> Exa MCP's `get_code_context_exa` is deprecated and not registered by default. Use
> `web_search_exa` for code questions too; when you need to search repository contents precisely, use the GitHub search in `dev.md` instead.

### Highlights

- Strong on English content and technical documentation
- Can pinpoint official docs and code examples through the query
- High-quality results

## Comparison with other search tools

| Tool | Source | Best for |
|-----|------|---------|
| Exa | weblens | English/technical/code search |
| Zhipu Search | my-mcp-tools | Chinese-language search |
| GitHub search | weblens (dev.md) | Repository/code search |
