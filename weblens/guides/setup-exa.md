# Exa Search Setup Guide

## What It Does
Exa is an AI semantic search engine. It is connected via MCP and is **free, with no API key required**. Once configured, it unlocks:
- Semantic web-wide search
- Reddit search (via site:reddit.com)
- Twitter search (via site:x.com)

## Steps the Agent Can Complete Automatically

With the user's explicit authorization, `weblens install --env=auto --system` completes the following steps.
The default command without `--system` only runs read-only checks.

### 1. Install mcporter
```bash
npm install -g mcporter
```

### 2. Register the Exa MCP
```bash
mcporter config add exa https://mcp.exa.ai/mcp --scope home
```

### 3. Verify
```bash
weblens doctor | grep "Search"
mcporter call exa.web_search_exa query="test" numResults=1
```

## Steps the User Must Do Manually

**None.** Exa is connected via MCP: free, no sign-up, no API key.

If `weblens install --system` did not configure Exa because of network issues, just run the two commands above manually.

## FAQ

**Q: Is there a search limit?**
A: The MCP endpoint is provided officially by Exa (mcp.exa.ai) and is currently free and unlimited. If that changes in the future, weblens will adapt in an update.

**Q: What is mcporter?**
A: A command-line bridge for the MCP protocol, used to call MCP servers. WebLens uses it to connect to Exa and Xiaohongshu (RedNote).
