<h1 align="center">👁️ WebLens</h1>

<p align="center">
  <strong>One command to read and search the web — for you and your AI agent.</strong>
</p>

<p align="center">
  <code>weblens read &lt;url&gt;</code> turns any link into clean text. <code>weblens search &lt;query&gt;</code> searches the web, Hacker News, Wikipedia, arXiv, Stack Overflow, GitHub and more.<br>
  Behind both, WebLens picks, installs and health-checks the best free backend for each platform.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#supported-sources">Sources</a> ·
  <a href="#use-with-ai-agents">AI agents</a> ·
  <a href="#python-api">Python API</a> ·
  <a href="#security--privacy">Security</a>
</p>

---

## 30-second demo

```bash
pip install weblens
```

**Read any URL.** WebLens detects what the link is and uses the platform's own API when one exists:

```console
$ weblens read 'https://arxiv.org/abs/1706.03762' --max-chars 300
# Attention Is All You Need

- source: arxiv via arXiv API
- url: https://arxiv.org/abs/1706.03762v7
- id: 1706.03762v7
- authors: Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, ...
- published: 2017-06-12T17:57:34Z
- categories: cs.CL, cs.LG
- pdf: https://arxiv.org/pdf/1706.03762v7
- truncated: yes

## Abstract

The dominant sequence transduction models are based on complex recurrent or
convolutional neural networks in an encoder-decoder configuration. ...
```

```console
$ weblens read 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' --max-chars 200
# Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)

- source: youtube via yt-dlp
- channel: Rick Astley
- duration: 3:33
- views: 1,820,177,641
- subtitles: en (manual)
...
```

**Search one source, or several at once:**

```console
$ weblens search 'rust async runtime' --source all --limit 2
# Search: "rust async runtime" (source: all)

## web (2)
1. Tokio - An asynchronous Rust runtime
   https://tokio.rs/
   Tokio is an asynchronous runtime for the Rust programming language. ...

## hackernews (2)
1. The State of Async Rust: Runtimes
   https://corrode.dev/blog/async/
   points: 258 · comments: 198 · author: RebootStr · date: 2023-09-25

## wikipedia (2)
1. Tokio (software)
   https://en.wikipedia.org/wiki/Tokio_%28software%29
...
## stackoverflow (2)
...
## arxiv (2)
...
```

Add `--json` to either command for structured output that scripts and agents can parse.

---

## Why WebLens

Agents are good at reasoning, but bad at getting to the content:

- A YouTube link has no text to read unless something fetches the transcript.
- Raw HTML is noisy; most pages need a reader to become usable text.
- Reddit, X and other social sites block anonymous and server traffic.
- Every platform has its own CLI, API quirks, login model and rate limits, and they change often.

WebLens handles all of that in one place:

| | |
|---|---|
| 🎯 **One interface** | `read` and `search` work the same way on every source, as CLI, Python API or MCP tools. |
| 🆓 **Free by default** | Ten sources work with no account and no API key. Every backend is open source or a free public API. |
| 🔀 **Resilient routing** | Each platform has an ordered list of backends. When one breaks, WebLens moves to the next. `weblens doctor` shows which one is active. |
| 🩺 **Built-in diagnostics** | `weblens doctor` tells you what works, what doesn't, and the exact fix. |
| 🤖 **Agent-ready** | Ships a skill file for Claude Code, OpenClaw and OpenCode, plus an MCP server for Cursor and other MCP clients. |
| 🔒 **Local-first** | Credentials stay in `~/.weblens/` on your machine. Private and internal URLs are refused. |

---

## Quick start

### Install it yourself

```bash
pip install weblens          # the PyPI package is named `weblens`
# or, isolated:
pipx install weblens

weblens doctor               # what works right now
weblens read 'https://news.ycombinator.com/item?id=42231710'
weblens search 'vector databases' --source hackernews
```

Latest development version from GitHub:

```bash
pipx install https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip
```

### Or let your agent do it

Paste this into Claude Code, Cursor, OpenClaw or any agent that can run shell commands:

```
Install WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md
```

The agent installs the CLI, checks your environment, registers the skill file, and asks which optional platforms you want. Updating works the same way:

```
Update WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md
```

> 🛡️ **Safe by default.** `weblens install` only inspects the machine and lists what is missing. Nothing is installed and no config is written until you pass `--system`. Use `--dry-run` to preview.

> ⚠️ **OpenClaw users:** the agent must be allowed to run shell commands. Switch to the `coding` tool profile first (`openclaw config set tools.profile "coding"`), restart the gateway with `openclaw gateway restart`, and start a new conversation.

---

## Commands

| Command | What it does |
|---|---|
| `weblens read <url> [--json] [--max-chars N]` | Read any public URL as clean text, routed to the best backend |
| `weblens search <query> [-s SOURCE] [-n N] [--json]` | Search `web` (default), `hackernews`, `wikipedia`, `arxiv`, `stackoverflow`, `youtube`, `github`, `v2ex`, `reddit`, `twitter`, or `all` |
| `weblens doctor [--json]` | Show every channel's status and active backend |
| `weblens install [--env local\|server\|auto] [--system] [--dry-run] [--channels LIST]` | Check dependencies; with `--system`, install and configure them |
| `weblens configure <key>` / `--from-browser BROWSER --platform P` | Save a proxy, token or cookies (hidden prompt or `--stdin`) |
| `weblens setup` | Interactive configuration wizard |
| `weblens skill --install` / `--uninstall` | Register or remove the agent skill file |
| `weblens transcribe <url-or-file> [-o FILE]` | Speech to text via Whisper (Groq or OpenAI key) |
| `weblens watch` | Quick health and update check, for scheduled tasks |
| `weblens check-update` | Check for a newer WebLens release |
| `weblens uninstall [--dry-run] [--keep-config]` | Remove config, tokens and skill files |
| `weblens version` | Print the version |

Global flags: `-v/--verbose` shows debug logs; `--debug` also prints full tracebacks. Exit codes: `0` success, `1` failure, `2` bad usage (invalid URL, unknown source, bad flag).

`search --source all` queries web, Hacker News, Wikipedia, Stack Overflow and arXiv in parallel and groups the results by source. `--limit` is per source (default 10, max 50). If web search (Exa) is not configured, `search` falls back to Hacker News + Wikipedia and says so.

---

## Supported sources

### Global

| Source | `read` | `search` | Backend | Setup |
|---|---|---|---|---|
| 🌐 **Any web page** | ✅ | — | [Jina Reader](https://github.com/jina-ai/reader) | None |
| 🔍 **Web search** | — | ✅ `web` | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | None (free MCP endpoint, added by `install --system`) |
| 📺 **YouTube** | ✅ metadata + transcript | ✅ `youtube` | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | None |
| 📦 **GitHub** | ✅ repo README, issue, PR | ✅ `github` | [gh CLI](https://cli.github.com) or public REST API | None; `gh auth login` lifts the 60 req/h limit |
| 🟧 **Hacker News** | ✅ story + comment tree | ✅ `hackernews` | HN Firebase API + Algolia | None |
| 📚 **Wikipedia** | ✅ full article | ✅ `wikipedia` | Wikipedia REST + MediaWiki API | None |
| 📄 **arXiv** | ✅ abstract + metadata | ✅ `arxiv` | arXiv API | None |
| 💬 **Stack Overflow** | ✅ question + answers | ✅ `stackoverflow` | Stack Exchange API | None |
| 📡 **RSS / Atom** | ✅ | — | [feedparser](https://github.com/kurtmckee/feedparser) | None |
| 📖 **Reddit** | ✅ via backend | ✅ `reddit` | [OpenCLI](https://github.com/jackwener/opencli) ▸ [rdt-cli](https://github.com/public-clis/rdt-cli) | Login session required |
| 🐦 **Twitter / X** | ✅ via backend | ✅ `twitter` | [twitter-cli](https://github.com/public-clis/twitter-cli) ▸ OpenCLI | Cookies (Cookie-Editor export) |
| 💼 **LinkedIn** | Public pages via Jina | Upstream tool | [mcp-server-linkedin](https://github.com/stickerdaniel/linkedin-mcp-server) ▸ Jina | Optional MCP server + login |
| 📘 **Facebook** | Upstream tool | Upstream tool | OpenCLI | Desktop Chrome login |
| 📷 **Instagram** | Upstream tool | Upstream tool | OpenCLI | Desktop Chrome login |

"Via backend" means `weblens read`/`search` call the platform's active upstream tool for you. When no backend is working, `read` falls back to Jina Reader and `search` falls back to Exa restricted to that site, and the output includes a note saying so. "Upstream tool" means the agent calls the tool directly; the skill file has the commands.

Not sure how to set up a platform? Tell your agent "help me set up Reddit" (or any other platform). The install guide walks it through the steps.

<details>
<summary><strong>🇨🇳 China pack (optional)</strong></summary>

<br>

| Source | What you get | Backend | Setup |
|---|---|---|---|
| 📺 **Bilibili** | Search, video details, trending (`weblens read` on a video URL); subtitles via OpenCLI | [bili-cli](https://github.com/public-clis/bilibili-cli) ▸ OpenCLI ▸ search API | None for basics |
| 📕 **Xiaohongshu (RedNote)** | Search, notes, comments | OpenCLI ▸ [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) ▸ [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) | Existing Chrome session, or Cookie-Editor export |
| 💻 **V2EX** | Topics + replies (`weblens read`), hot topics, nodes; `search -s v2ex` uses Exa (`site:v2ex.com`) | V2EX public API | None |
| 📈 **Xueqiu (Snowball)** | Stock quotes, search, hot posts | Xueqiu API | Browser cookie import |
| 🎙️ **Xiaoyuzhou Podcast** | Episode audio to text | Groq Whisper + ffmpeg | Free Groq key |
| 🎯 **BOSS Zhipin** | Job search + full JD text | boss-agent-cli over CDP | Dedicated local Chrome; tell your agent "set up BOSS Zhipin for me" |

Xiaohongshu: WebLens never logs in for you and never reads Xiaohongshu browser cookies. OpenCLI only uses a Chrome session that you already have and control. `weblens configure xhs-cookies` does not inject cookies into OpenCLI or Chrome; it is for xiaohongshu-mcp and legacy tools.

</details>

### Credentials boundaries

- **Twitter/X** only accepts cookies you export yourself with Cookie-Editor (`weblens configure twitter-cookies`, hidden prompt). The saved values are used by `weblens doctor` and by `weblens read`/`search`. To run the upstream `twitter` CLI directly, set `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in that process's environment.
- **Secrets never go on the command line.** `weblens configure` reads keys, tokens and cookies from a hidden prompt or `--stdin`.
- **Local machines need no proxy.** Servers may need one for Reddit and X (`weblens configure proxy`).

---

## How it works

Each platform is one file in `weblens/channels/` with an ordered list of backends. `weblens doctor` probes them in order (it actually runs the tool rather than just checking that it exists) and reports the first one that works. `weblens read` and `weblens search` use the same routing.

```
channels/
├── web.py            → Jina Reader
├── exa_search.py     → Exa via mcporter
├── youtube.py        → yt-dlp
├── github.py         → gh CLI ▸ public REST API
├── hackernews.py     → HN Firebase API + Algolia
├── wikipedia.py      → Wikipedia REST + MediaWiki API
├── arxiv.py          → arXiv API
├── stackoverflow.py  → Stack Exchange API
├── rss.py            → feedparser
├── reddit.py         → OpenCLI ▸ rdt-cli
├── twitter.py        → twitter-cli ▸ OpenCLI ▸ bird
├── linkedin.py       → mcp-server-linkedin ▸ Jina Reader
├── facebook.py       → OpenCLI
├── instagram.py      → OpenCLI
├── bilibili.py       → bili-cli ▸ OpenCLI ▸ search API
├── xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli
├── v2ex.py           → V2EX API
├── xueqiu.py         → Xueqiu API
├── xiaoyuzhou.py     → Groq Whisper + ffmpeg
└── boss.py           → boss-agent-cli (CDP)
```

Switching a platform to a different backend means reordering its list, not rewriting callers. You can force one with the config key `<channel>_backend` or the environment variable `<CHANNEL>_BACKEND`.

---

## Use with AI agents

### Skill file (Claude Code, OpenClaw, OpenCode)

```bash
weblens skill --install
```

This copies `SKILL.md` and its `references/` into every agent skill directory it finds: `~/.claude/skills/weblens`, `~/.openclaw/skills/weblens`, `~/.config/opencode/skills/weblens`, or `~/.agents/skills/weblens`. The skill tells the agent to use `weblens read` and `weblens search` first and lists upstream commands for advanced cases.

### MCP server (Cursor, Claude Desktop, any MCP client)

The MCP server needs the `mcp` extra:

```bash
pip install 'weblens[mcp]'
python -m weblens.integrations.mcp_server   # stdio server
```

Add it to your client config (for example `~/.cursor/mcp.json` or Claude Desktop's `claude_desktop_config.json`). Use the absolute path of the Python interpreter WebLens is installed into:

```json
{
  "mcpServers": {
    "weblens": {
      "command": "/path/to/python",
      "args": ["-m", "weblens.integrations.mcp_server"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add weblens -- /path/to/python -m weblens.integrations.mcp_server
```

| Tool | Arguments | Returns |
|---|---|---|
| `get_status` | — | The `weblens doctor` report |
| `read` | `url`, `max_chars?`, `format?` (`markdown` \| `json`) | Same output as `weblens read` |
| `search` | `query`, `source?`, `limit?` (1–50), `format?` | Same output as `weblens search` |

---

## Python API

```python
from weblens.core import WebLens

lens = WebLens()

page = lens.read("https://en.wikipedia.org/wiki/Model_Context_Protocol", max_chars=2000)
print(page.title, page.source, page.backend)
print(page.body)
print(page.notes)          # fallbacks and caveats, if any

hits = lens.search("retrieval augmented generation", source="arxiv", limit=5)
for r in hits.results:
    print(r.title, r.url, r.extra.get("date"))

print(lens.doctor_report())  # same text as `weblens doctor`
```

`read()` returns a `ReadResult` (`title`, `url`, `source`, `backend`, `body`, `metadata`, `notes`, `truncated`). `search()` returns a `SearchResponse` (`results`, `notes`, `errors`, `sources`). Both have `.to_dict()`. Failures raise `weblens.unified.errors.WebLensError`, which has a `.hint` with the suggested fix.

---

## Security & privacy

| | |
|---|---|
| 🌍 **Third-party services** | Generic pages are read through **Jina Reader** (`r.jina.ai`) and web search goes through **Exa**, so those services see the URLs and queries you send. Native sources (HN, Wikipedia, arXiv, Stack Exchange, GitHub, YouTube, V2EX) and RSS/Atom feeds are fetched directly. |
| 📡 **Direct feed check** | Before a URL that no native channel claims is sent to Jina, WebLens makes one small direct request to it from your machine (or your configured proxy; it reads at most the first 8 KB, with an 8-second limit) to see whether it is an RSS/Atom feed. Feed-shaped URLs such as `/feed`, `.rss` or `.atom` are downloaded directly in full. So the target site sees your IP (or your proxy's) and the `weblens/<version>` User-Agent, not only Jina. |
| 🚫 **Private targets refused** | `weblens read` refuses localhost, private and link-local IP literals, and internal hostnames (`.local`, `.internal`, cloud metadata). Direct feed fetches and the feed check also require the host, and every redirect hop, to resolve only to public addresses, and they connect to the address that was checked (no second DNS lookup, so DNS rebinding cannot swap in a private IP). Through a proxy (`HTTPS_PROXY` or `weblens configure proxy`), the proxy resolves the host and makes the final connection, so only the pre-check applies. Native channels only talk to their own API hosts over HTTPS. |
| 🔒 **Local credentials** | Cookies and tokens live only in `~/.weblens/config.yaml` (mode `600`). They are never uploaded. |
| 📌 **Pinned installs** | `weblens install --system` installs exact versions of mcporter, OpenCLI, twitter-cli and bilibili-cli, and fixed git commits for rdt-cli and boss-agent-cli, never a moving branch. |
| 🧾 **Shell safety for agents** | The skill file tells agents to pass every URL or query as one single-quoted argument and to refuse input that contains shell metacharacters. |
| 🛡️ **No surprise changes** | `install` is check-only unless you pass `--system`; `--dry-run` previews; `uninstall` removes everything. |

> ⚠️ **Account-ban risk.** Using cookies or browser sessions from scripts (X, Reddit, Xiaohongshu, Facebook, Instagram, BOSS Zhipin) can get an account flagged or banned. Use a dedicated secondary account, not your main one. A cookie is equivalent to a logged-in session, so a secondary account also limits the damage if it leaks.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

### Uninstall

```bash
weblens uninstall              # removes ~/.weblens/, skill files, and WebLens MCP entries in mcporter
weblens uninstall --dry-run    # preview
weblens uninstall --keep-config
pip uninstall weblens
```

---

## Troubleshooting

Start with `weblens doctor`; each problem comes with a fix. Common cases (YouTube 429, GitHub rate limit, Exa not configured, Stack Exchange quota, X/Twitter auth, BOSS Zhipin login) are covered in [docs/troubleshooting.md](docs/troubleshooting.md). Run any command with `--debug` for a full traceback.

## Contributing

Contributions are welcome, especially new channels and backend fixes. See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup, the channel contract and PR guidelines.

## License

[MIT](LICENSE)

## Credits

WebLens builds on these open-source projects and free services:

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [GitHub CLI](https://cli.github.com) · [feedparser](https://github.com/kurtmckee/feedparser) · [OpenCLI](https://github.com/jackwener/opencli) · [twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [mcp-server-linkedin](https://github.com/stickerdaniel/linkedin-mcp-server) · [boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) · [Groq](https://groq.com) · public APIs from [Hacker News](https://github.com/HackerNews/API), [Algolia HN Search](https://hn.algolia.com/api), [Wikipedia](https://www.mediawiki.org/wiki/API:Main_page), [arXiv](https://info.arxiv.org/help/api/) and [Stack Exchange](https://api.stackexchange.com)
