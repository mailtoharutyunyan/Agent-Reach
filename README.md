<h1 align="center">👁️ WebLens</h1>

<p align="center">
  <strong>Give your AI Agent internet access in one step</strong>
</p>

<p align="center">
  The most reliable access path available right now — chosen, installed, and health-checked for you. Access paths change over time; you don't have to worry about it.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="#supported-platforms">Platforms</a> · <a href="#design-philosophy">Philosophy</a>
</p>

---

## Why WebLens?

AI Agents can already write code, edit documents, and manage projects for you — but ask one to find something online and it's lost:

- 📺 "What does this YouTube tutorial cover?" → **Can't watch it**, no access to subtitles
- 🐦 "Search Twitter for what people think of this product" → **Can't search**, the Twitter API is paid
- 📖 "Check Reddit to see if anyone has hit the same bug" → **403 blocked**, server IP rejected
- 📕 "Check the reviews for this product on Xiaohongshu (RedNote)" → **Can't open it**, login required
- 📺 "There's a tech video on Bilibili, summarize it for me" → **Can't fetch it**, generic downloaders are fully blocked by Bilibili's anti-bot controls
- 🔍 "Search the web for the latest LLM framework comparisons" → **No good search**, either paid or low quality
- 🌐 "What does this web page say?" → **Returns a pile of HTML tags**, basically unreadable
- 📦 "What is this GitHub repo for? What's being said in the Issues?" → Works, but auth setup is a hassle
- 📡 "Subscribe to these RSS feeds and tell me when they update" → You have to install a library and write code yourself

**None of this is hard, but it all takes fiddly setup**

Every platform has its own barriers — paid APIs, blocks to get around, accounts to log into, data to clean. You'd have to hit every pitfall, install tools, and tweak configs one by one; just getting your Agent to read Twitter can take half a day.

**WebLens turns this into a single sentence:**

```
Install WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md
```

Copy that to your Agent, and a few minutes later it can read Twitter, search Reddit, watch YouTube, and browse Xiaohongshu.

**Already installed? Updating is one sentence too:**

```
Update WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md
```

> ⭐ **Star this project** — we keep tracking changes on every platform and adding new channels. You don't have to watch for it yourself: when a platform blocks us, we fix it; when there's a new channel, we add it.

### ✅ Before you start, you might want to know

| | |
|---|---|
| 💰 **Completely free** | All tools are open source and all APIs are free. The only possible cost is a server proxy ($1/month); local computers don't need one |
| 🔒 **Privacy safe** | Cookies stay on your machine only — never uploaded or shared. The code is fully open source and can be audited anytime |
| 🔄 **Continuously updated** | Every platform uses multi-backend "primary + fallback" routing. When one access path stops working, we switch to the next and you won't notice (June 2026 example: Bilibili's anti-bot controls blocked yt-dlp completely → switched to bili-cli, zero action required from users) |
| 🤖 **Works with any Agent** | Claude Code, OpenClaw, Cursor, Windsurf… any Agent that can run command-line tools |
| 🩺 **Built-in diagnostics** | `weblens doctor` tells you in one command what works, what doesn't, and how to fix it |

---

## Supported Platforms

| Platform | Works out of the box | Unlocked after setup | How to set up |
|------|---------|-----------|-------|
| 🌐 **Web** | Read any web page | — | No setup needed |
| 📺 **YouTube** | Subtitle extraction + video search | — | No setup needed |
| 📡 **RSS** | Read any RSS/Atom feed | — | No setup needed |
| 🔍 **Web search** | — | Semantic search across the web | Auto-configured (via MCP, free, no key needed) |
| 📦 **GitHub** | Read public repos + search | Private repos, open Issues/PRs, Fork | Tell your Agent "help me log in to GitHub" |
| 🐦 **Twitter/X** | Read single tweets | Search tweets, browse timelines, read long-form articles | Tell your Agent "help me set up Twitter" |
| 📺 **Bilibili** | Search + video details (bili-cli, no login needed) | Subtitles (OpenCLI) | Tell your Agent "help me set up Bilibili" |
| 📖 **Reddit** | — (no zero-config path: anonymous endpoints are blocked) | Search + read posts and comments | Install OpenCLI on desktop to use your browser login session; or rdt-cli + Cookie |
| 📘 **Facebook** | — | Search, profiles, Feed, groups list | Install OpenCLI on desktop (reuses your Chrome login session) |
| 📷 **Instagram** | — | User search, Profile, a user's recent posts, Explore | Install OpenCLI on desktop (reuses your Chrome login session) |
| 📕 **Xiaohongshu (RedNote)** | — | Search, read, comments | OpenCLI only uses the user's existing Chrome session; MCP/legacy tools use Cookie-Editor |
| 💼 **LinkedIn** | Read public pages via Jina Reader | Profile details, company pages, job search | Tell your Agent "help me set up LinkedIn" |
| 🎯 **BOSS Zhipin** | CDP pipeline health check | Job search + full JD text (dedicated real Chrome) | Tell your Agent "set up BOSS Zhipin for me"; the Agent opens a dedicated Chrome and you log in manually |
| 💻 **V2EX** | Hot topics, node topics, topic details + replies, user info | — | No setup needed |
| 📈 **Xueqiu (Snowball)** | Stock quotes, stock search, hot posts, hot stock rankings | — | Tell your Agent "help me set up Xueqiu" |
| 🎙️ **Xiaoyuzhou Podcast** | — | Podcast audio to text (Whisper transcription, free key) | Tell your Agent "help me set up Xiaoyuzhou Podcast" |

> **Not sure how to set it up? No need to read the docs.** Just tell your Agent "help me set up XXX" — it knows what's needed and will guide you step by step.
>
> 🍪 Twitter only accepts content the user exports manually via Cookie-Editor. WebLens does not log in to Xiaohongshu on the user's behalf and does not read Xiaohongshu browser cookies; OpenCLI only uses a Chrome session that already exists and is explicitly controlled by the user. `weblens configure xhs-cookies` does not inject cookies into OpenCLI / Chrome; if there is no existing session, export with Cookie-Editor instead and configure xiaohongshu-mcp / legacy tools.
>
> Saved Twitter cookies are only used by `weblens doctor` to check whether the configuration is complete; before running the upstream `twitter` command directly, you still need to explicitly set `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the current process environment.
>
> 🔒 Cookies stay on your machine only — never uploaded or shared. The code is fully open source and can be audited anytime.
> 💻 Local computers don't need a proxy. A proxy is only needed when deploying on a server (~$1/month).

---

## Quick Start

> ⚠️ **OpenClaw users: first make sure exec permission is enabled**
>
> WebLens relies on the Agent running shell commands (`pip install`, `mcporter`, `twitter`, etc.). If your OpenClaw uses the default `messaging` tool profile, the Agent will not be able to run commands. **Enable exec permission before installing**:
>
> ```bash
> openclaw config set tools.profile "coding"
> ```
> Or set `"tools": { "profile": "coding" }` in `~/.openclaw/openclaw.json`.
> After that, restart the Gateway (`openclaw gateway restart`) and start a new conversation. Other platforms (Claude Code, Cursor, Windsurf, etc.) are not affected by this restriction.

Copy this sentence to your AI Agent (Claude Code, OpenClaw, Cursor, etc.):

```
Install WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md
```

That's the only step. The Agent takes care of everything else.

> 🔄 **Already installed?** Updating is one sentence too:
> ```
> Update WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md
> ```

> 🛡️ **Safe by default:** by default `weblens install` only checks the environment; it does not automatically install system packages or write configuration:
> ```
> Safely check and install WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md
> ```
> Only use `weblens install --system` after you have explicitly allowed changes to your system.

<details>
<summary>What does it do? (click to expand)</summary>

1. **Install the CLI tool** — installs the `weblens` command line from this repository (bundles yt-dlp and feedparser; do not install the package of the same name from PyPI — it is not this project)
2. **Check system infrastructure** — checks Node.js, gh CLI, and mcporter, and shows how to install anything missing
3. **Install and configure as authorized** — only installs dependencies and connects Exa via MCP when `--system` is passed explicitly
4. **Detect the environment** — determines whether it's running on a local computer or a server and gives matching setup recommendations
5. **Register SKILL.md as authorized** — only writes to the Agent's skills directory with an explicit `--system`; the default check does not change any files
6. **Ask whether you want more** — only the 6 zero-config channels are activated by default; for channels that need a login session (Xiaohongshu, Twitter, Reddit, Facebook, Instagram), the Agent shows you a menu and asks which ones you want, and only installs the ones you name

After installation, `weblens doctor` tells you in one command the status of each channel and which path it is currently using.
</details>

---

## Works Out of the Box

No configuration needed — just tell your Agent:

- "Take a look at this link" → `curl https://r.jina.ai/URL` reads any web page
- "What does this GitHub repo do?" → `gh repo view owner/repo`
- "What does this YouTube video cover?" → `yt-dlp` extracts subtitles
- "Search Bilibili for AI tutorials" → `bili search` (no login needed)
- "Search the web for LLM framework comparisons" → Exa semantic search
- "Subscribe to this RSS feed" → `feedparser` parses it

**No commands to remember.** After reading SKILL.md, the Agent knows what to call on its own. For platforms that require login (Xiaohongshu, Twitter, Reddit, Facebook, Instagram), just tell your Agent "help me set up XXX" to unlock them.

---

## Design Philosophy

**WebLens is a capability layer, not yet another tool.**

It sits one level above any specific implementation — it handles **selection, installation, health checks, and routing**, not the reading itself. Reading is done by the Agent calling upstream tools directly, with no wrapper layer.

Whenever you set up the environment for a new Agent, you always spend time finding tools, installing dependencies, and tweaking configs — what do you use to read Twitter? How do you log in to Reddit? The Xiaohongshu CLI stopped being maintained, so what replaces it? You have to hit the same pitfalls all over again every time. What WebLens does is simple: **we choose, install, and health-check the most reliable access path available right now for you. Access paths change over time (in March 2026 a batch of single-platform CLIs all stopped being maintained, and we changed the routing), so you don't have to worry about it.**

### 🔌 Every platform = an ordered list of backends (primary + fallbacks)

Switching access paths = reordering the list, not rewriting code. `weblens doctor` tells you **which backend each platform is currently using**.

```
channels/
├── web.py          → Jina Reader
├── twitter.py      → twitter-cli ▸ OpenCLI ▸ bird
├── youtube.py      → yt-dlp
├── github.py       → gh CLI
├── bilibili.py     → bili-cli ▸ OpenCLI ▸ search API (yt-dlp blocked by Bilibili's anti-bot controls, retired)
├── reddit.py       → OpenCLI ▸ rdt-cli (no zero-config path, login session required)
├── facebook.py     → OpenCLI (desktop browser login session)
├── instagram.py    → OpenCLI (desktop browser login session)
├── xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli
├── linkedin.py     → mcp-server-linkedin ▸ Jina Reader
├── rss.py          → feedparser
├── exa_search.py   → Exa via mcporter
└── __init__.py     → Channel registry (used by doctor checks)
```

Each channel file **actually probes** its candidate backends in order (not just checking whether a command exists); the first one that fully works is selected, and broken ones come with a fix prescription. The actual reading and searching is done by the Agent calling upstream tools directly.

### Current Tool Choices

| Scenario | Primary | Fallback | Why |
|------|------|------|-----------|
| Read web pages | [Jina Reader](https://github.com/jina-ai/reader) | — | Free, no API key needed |
| Read tweets | [twitter-cli](https://github.com/public-clis/twitter-cli) | [OpenCLI](https://github.com/jackwener/opencli) | Search is stable in real-world tests; OpenCLI falls back on your browser login session |
| Reddit | [OpenCLI](https://github.com/jackwener/opencli) (desktop) | [rdt-cli](https://github.com/public-clis/rdt-cli) | Anonymous endpoints are blocked and the official API requires approval — only the login-session route is left |
| Facebook | [OpenCLI](https://github.com/jackwener/opencli) (desktop) | — | Graph API/Groups API permissions have been tightened; a browser login session is currently the most practical route |
| Instagram | [OpenCLI](https://github.com/jackwener/opencli) (desktop) | Official Graph API (Business/Creator + review) | instaloader-style paths are unstable; OpenCLI reuses a real browser session |
| YouTube subtitles + search | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | — | 154K stars, still the best for YouTube (note: no longer used for Bilibili) |
| Bilibili | [bili-cli](https://github.com/public-clis/bilibili-cli) | OpenCLI ▸ search API | yt-dlp is blocked with 412 by Bilibili's anti-bot controls (verified June 2026); bili-cli can search and read without login |
| Search the web | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | — | AI semantic search, connected via MCP with no key needed |
| GitHub | [gh CLI](https://cli.github.com) | — | Official tool, full API capabilities after authentication |
| Read RSS | [feedparser](https://github.com/kurtmckee/feedparser) | — | The standard choice in the Python ecosystem |
| Xiaohongshu | [OpenCLI](https://github.com/jackwener/opencli) (desktop) | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) (server) ▸ xhs-cli | OpenCLI only uses the user's existing session; other backends use a manual Cookie-Editor export |
| LinkedIn | [mcp-server-linkedin](https://github.com/stickerdaniel/linkedin-mcp-server) | Jina Reader | MCP service, browser automation |

> 📌 These are all "current choices", re-verified regularly through real-machine testing. When a path stops working we switch to the next one — `weblens doctor` always tells you which path is in use right now.

---

## Security

WebLens is designed with security in mind:

| Measure | Details |
|------|------|
| 🔒 **Local credential storage** | Cookies and tokens are stored only on your machine in `~/.weblens/config.yaml`, with file permission 600 (owner read/write only), never uploaded or shared |
| 🛡️ **Safe by default** | `weblens install` does not modify the system by default; external tools are installed and configuration is written only with an explicit `--system` |
| 👀 **Fully open source** | Transparent code that can be audited anytime. All dependency tools are open-source projects too |
| 🔍 **Dry Run** | `weblens install --dry-run` previews all actions without making any changes |
| 🧩 **Pluggable architecture** | Don't trust a component? Just swap out the corresponding channel file — nothing else is affected |

### 🍪 Cookie Security Recommendations

> ⚠️ **Account ban risk:** On platforms that use cookie login (Twitter, Xiaohongshu, etc.), calls made via scripts/APIs **carry a risk of being detected by the platform and getting the account banned**. Always use a **dedicated secondary account**, not your main account.

For platforms that need cookies or a login session (Twitter, Xiaohongshu, Reddit, Facebook, Instagram, etc.), we recommend using a **dedicated secondary account** rather than your main account. There are two reasons:
1. **Ban risk** — the platform may detect API calls that don't look like normal browser behavior, leading to account restrictions or bans
2. **Security risk** — a cookie is equivalent to full login access; using a secondary account limits the impact if credentials leak

### 📦 Installation Options

| Option | Command | Best for |
|------|------|---------|
| Default safe check | `weblens install --env=auto` | All environments; read-only check that lists what's missing |
| Explicitly install system dependencies | `weblens install --env=auto --system` | When you explicitly allow changes to the current machine |
| Compatibility safe flag | `weblens install --env=auto --safe` | Same as the default behavior |
| Preview only | `weblens install --env=auto --dry-run` | See what it would do first |

### 🗑️ Uninstall

```bash
weblens uninstall
```

This removes: `~/.weblens/` (including all tokens/cookies), each Agent's skill files, and the MCP configuration in mcporter.

```bash
# Preview only, don't actually delete
weblens uninstall --dry-run

# Delete only the skill files, keep token configuration (for reinstalling)
weblens uninstall --keep-config
```

To uninstall the Python package itself: `pip uninstall weblens`

---

## Credits

[OpenCLI](https://github.com/jackwener/opencli) · [twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [mcp-server-linkedin](https://github.com/stickerdaniel/linkedin-mcp-server)

## License

[MIT](LICENSE)
