# Xiaohongshu (RedNote) Setup Guide

## What It Does
Reads and searches Xiaohongshu (RedNote) notes. Desktops prefer OpenCLI; servers use
[xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp);
xhs-cli is kept only as a legacy fallback for users who already have it installed.

## Prerequisites
- OpenCLI: a Chrome Xiaohongshu session that already exists and is explicitly controlled by the user
- xiaohongshu-mcp / legacy tools: the Cookie-Editor browser extension

## Authentication Boundaries

WebLens does not log in to Xiaohongshu on the user's behalf, and it does not read browser cookies.

OpenCLI only uses a Chrome session that already exists and is explicitly controlled by the user.
`weblens configure xhs-cookies` never injects cookies into OpenCLI or Chrome.
If there is no existing session, do not log in automatically; instead, export manually with Cookie-Editor and configure
xiaohongshu-mcp or the legacy tools:

1. Install the [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) extension in Chrome
2. The user prepares the session to export on xiaohongshu.com themselves
3. Click the Cookie-Editor icon → Export → Header String
4. Send the exported string to the Agent and run:

```bash
weblens configure xhs-cookies
weblens doctor
```

This explicit command saves/imports the user-supplied same-domain xiaohongshu.com cookie set; before running it,
confirm the cookie names and scope. Cookies from domains other than xiaohongshu.com are ignored.

If the xiaohongshu-mcp container is running, the configure command imports the cookies into the container; otherwise it writes
them to an owner-only local file and prints the path for a follow-up manual import.

## Usage Examples

First pick commands based on `active_backend` in `weblens doctor --json`. Legacy xhs-cli examples:

Search notes:
```bash
xhs search "keyword"
```

Read note details:
```bash
xhs read NOTE_ID
```

View comments:
```bash
xhs comments NOTE_ID
```

## FAQ

**Q: My cookies expired?**
A: Export again manually with Cookie-Editor, then run
`weblens configure xhs-cookies` and paste into the hidden input prompt.

**Q: Xiaohongshu warns about an IP risk?**
A: A residential proxy is recommended: `export HTTP_PROXY="http://user:pass@ip:port"`.

**Q: xhs-cli doesn't support my system?**
A: Make sure Python 3.10+ and pipx are installed. Then just run `pipx install xiaohongshu-cli`.

## Server Option: Docker MCP

If you are already using the [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker setup, it works fine too:

```bash
docker run -d \
  --name xiaohongshu-mcp \
  -p 18060:18060 \
  xpzouying/xiaohongshu-mcp

mcporter config add xiaohongshu http://localhost:18060/mcp --scope home
```

This server backend uses the manual Cookie-Editor export flow described above.
