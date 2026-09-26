# WebLens — Installation Guide

## For Humans

Copy this to your AI Agent:

```
Install WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md
```

> 🛡️ **Safe by default:** `weblens install` only checks the machine and lists missing dependencies:
> ```
> Safely check and install WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md
> ```
> Only use `--system` after the user explicitly approves system-level installs and configuration writes.

---

## For AI Agents

### Goal

Install WebLens and all upstream tools so your user's agent has full internet access. After installation, you'll use the upstream tools directly (OpenCLI, twitter-cli, bili-cli, rdt-cli, yt-dlp, mcporter, gh CLI, etc.) — WebLens is the selector, installer, health checker and router, never a wrapper.

### ⚠️ Boundaries

When fixing issues, stay within these limits:

- **DO NOT** run commands with `sudo` unless the user explicitly approved
- **DO NOT** modify system files outside `~/.weblens/`
- **DO NOT** install packages not listed in this guide
- **DO NOT** disable firewalls, security settings, or system protections
- **DO NOT** clone repos, create files, or run commands inside the agent workspace / working directory
- If something requires elevated permissions, **tell the user** what's needed and let them decide

### 📁 Directory Rules

All WebLens files go in dedicated directories — **never in the agent workspace**:

| Purpose | Directory | Example |
|---------|-----------|---------|
| Config & tokens | `~/.weblens/` | `~/.weblens/config.json` |
| Upstream tool repos | `~/.weblens/tools/` | `~/.weblens/tools/xiaoyuzhou/` |
| Temporary files | `/tmp/` | `/tmp/yt-dlp-output/` |
| Skills | `~/.openclaw/skills/weblens/` | SKILL.md |

**Why?** If you clone repos or create files in the workspace, it pollutes the user's project directory and can break their agent over time. Keep the workspace clean.

### Step 1: Install the basics

```bash
# Recommended: pipx (least hassle)
pipx install https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip
weblens install --env=auto               # Read-only check (default)
# After the user explicitly approves system changes:
weblens install --env=auto --system

# If your Python comes from Homebrew / you hit PEP 668 (externally-managed-environment),
# install in a virtual environment:
python3 -m venv ~/.weblens-venv
source ~/.weblens-venv/bin/activate
pip install https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip
weblens install --env=auto               # Read-only check (default)
# After the user explicitly approves system changes:
weblens install --env=auto --system
```

> 💡 **Windows / Microsoft Store Python alias?**
> If `python3 --version` opens the Microsoft Store, or `where python3` points to
> `...\AppData\Local\Microsoft\WindowsApps\python3.exe`, then `python3` is the Windows
> Store alias, not a usable Python installation. Use the Python Launcher `py -3` instead, or the `python.exe` in the actual install directory.
>
> PowerShell example:
> ```powershell
> py -3 -m venv $env:USERPROFILE\.weblens-venv
> $env:USERPROFILE\.weblens-venv\Scripts\Activate.ps1
> python -m pip install https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip
> weblens install --env=auto
> ```

The default command checks core infrastructure (gh CLI, Node.js, mcporter, Exa search, yt-dlp config) without changing the host. With explicit `--system` approval it installs/configures the missing pieces and activates these zero-config channels:

- Web (Jina Reader), YouTube, GitHub, RSS, Exa Search, V2EX, Bilibili (basic)

> 💡 **macOS / Homebrew Python says `externally-managed-environment`?**
> This is PEP 668 protection, not a problem with WebLens itself. Prefer `pipx install ...`, or create a `venv` first and install into it.

**Install modes:**

```bash
weblens install --env=auto             # Check only; safe default
weblens install --env=auto --safe      # Same check-only behavior (compatibility)
weblens install --env=auto --system    # Explicitly allow external/system installs
weblens install --env=auto --dry-run   # Preview what --system would do
```

### Step 2: Ask the user which optional channels they want

After installing the basics, **ask the user** which additional channels they need. Present this list:

> The basic channels are installed! You can now ask me to search the web, watch YouTube, read GitHub, and more.
>
> These optional channels are also available. Which ones do you need?
>
> - 🌟 **OpenCLI** (recommended for desktop) — one install provides Reddit/Facebook/Instagram/Bilibili subtitles/Twitter fallback, and serves as the Xiaohongshu (RedNote) desktop backend; for Xiaohongshu it only uses a Chrome session the user already has and explicitly controls
> - 🐦 **Twitter/X** — search tweets, view timelines (requires login cookies)
> - 📈 **Xueqiu (Snowball)** — stock quotes, trending posts (requires login cookies)
> - 🎙️ **Xiaoyuzhou podcasts** — audio-to-text (requires a free Groq key)
> - 📕 **Xiaohongshu (RedNote)** — search, read, comments (OpenCLI uses an existing session; MCP/legacy tools use Cookie-Editor)
> - 📖 **Reddit** — search and read posts (login required: desktop OpenCLI or rdt-cli + cookies)
> - 📘 **Facebook** — search, profiles, feed, group list (desktop via OpenCLI, reusing the Chrome login)
> - 📷 **Instagram** — user search, profiles, a user's recent posts, Explore (desktop via OpenCLI, reusing the Chrome login)
> - 📺 **Bilibili full version** — trending, rankings, search, video details (bili-cli, no login needed)
> - 💼 **LinkedIn** — profiles, job search
> - 🎯 **BOSS Zhipin** — job search + full JD text (local dedicated Chrome; the user logs in manually)
>
> Tell me which ones you want, e.g. "Install Xiaohongshu and Twitter for me" or "Install Facebook and Instagram for me". Or say "install everything".

Based on the user's choice, run:

```bash
weblens install --env=auto --system --channels=opencli,xiaohongshu   # Desktop user chose XHS
weblens install --env=auto --system --channels=facebook,instagram    # Desktop Meta channels
weblens install --env=local --system --channels=boss                # Desktop BOSS Zhipin
weblens install --env=auto --system --channels=all                   # User approved everything
```

Supported channel names: `opencli`, `twitter`, `xiaoyuzhou`, `xueqiu`, `xiaohongshu`, `reddit`, `facebook`, `instagram`, `bilibili`, `linkedin`, `boss`, `all`

### Step 3: Fix what's broken

Run `weblens doctor` and check the output.

Try to get as many channels to ✅ as possible. If something failed during install or shows as ❌/⚠️ in doctor, diagnose the problem and try to fix it — but stay within the boundaries above. If a fix requires elevated permissions or system changes, ask the user first.

Only ask the user when you genuinely need their input (credentials, permissions, etc.).

### Step 3: Configure things that need user input

Some channels need credentials only the user can provide. Based on the doctor output, ask for what's missing:

> 🔒 **Security tip:** For platforms that need cookies or browser sessions (Twitter, Xiaohongshu (RedNote), Reddit, Facebook, Instagram, BOSS Zhipin), we recommend using a **dedicated/secondary account** rather than your main account. Cookie/browser-session auth carries two risks:
> 1. **Account ban** — platforms may detect non-browser API calls and restrict or ban the account
> 2. **Credential exposure** — cookies grant full account access; using a secondary account limits the blast radius if credentials are ever compromised

> 🍪 **Cookies / login state:**
>
> For platforms where traditional CLIs need cookies (Twitter, Xueqiu, etc.), **prefer importing with Cookie-Editor**; it is the simplest and most reliable method:
> 1. The user logs in to the platform in their own browser
> 2. Install the [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
> 3. Click the extension → Export → Header String
> 4. Send the exported string to the Agent
>
> Twitter only accepts content the user explicitly exports through Cookie-Editor. WebLens does not log in to Xiaohongshu on the user's behalf and does not read Xiaohongshu browser cookies; Xiaohongshu OpenCLI only uses a Chrome session the user already has and explicitly controls. When there is no existing session, export with Cookie-Editor instead and configure xiaohongshu-mcp / the legacy tools. Xueqiu and Bilibili can be imported explicitly per platform, e.g. `weblens configure --from-browser chrome --platform xueqiu`; the command does not scan or save other platforms.

**Twitter search & posting:**
> "To unlock Twitter search, I need your Twitter cookies. Install the Cookie-Editor Chrome extension, go to x.com/twitter.com, click the extension → Export → Header String, and paste it to me."

```bash
weblens configure twitter-cookies
```

This saves `twitter_auth_token` and `twitter_ct0` for WebLens's own
`doctor` configuration check. `doctor` does not run the upstream `twitter status` in real time and does not modify
the current shell. Before running `twitter search/read/...` directly, you must explicitly set these in that process's environment:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
twitter search "query" -n 10
```

> **Proxy notes (for networks that need to bypass the firewall, such as mainland China):**
>
> twitter-cli and rdt-cli use Python; on networks that require a proxy, you can configure one via environment variables.
>
> **What you (the Agent) need to do:**
> 1. Confirm the user has configured a proxy: `weblens configure proxy` (hidden input)
> 2. Set the environment variables: `export HTTP_PROXY="..." HTTPS_PROXY="..."`
> 3. WebLens handles the rest automatically; the user does not need to do anything else
>
> If the user reports "fetch failed", see [troubleshooting.md](troubleshooting.md)

**Reddit (login is mandatory — no zero-config path):**
> Reddit's anonymous endpoints are blocked, and the official API requires manual approval. Desktop users should prefer OpenCLI (works once you have logged in to reddit.com in the browser); server/legacy users use rdt-cli:

```bash
# PyPI lags behind, so install from GitHub (same pinned version as _RDT_GIT_SOURCE in the code)
pipx install 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66'
rdt login   # Extracts browser cookies automatically; on a server without a browser, write cookies manually as doctor instructs
```

> Accessing Reddit from mainland China requires a proxy; if your server IP gets flagged by risk controls, you can configure a residential proxy (e.g. https://webshare.io, about $1/month):
> ```bash
> weblens configure proxy
> ```

**Xiaohongshu (RedNote) (multiple backends, chosen by environment):**

> **Authentication boundaries:** WebLens does not log in to Xiaohongshu on the user's behalf and does not read browser
> cookies. OpenCLI only uses a Chrome session that already exists and is explicitly controlled by the user;
> `weblens configure xhs-cookies` never injects cookies into OpenCLI or Chrome.
> If there is no existing session, do not log in automatically; instead, export manually with Cookie-Editor and configure
> xiaohongshu-mcp or the legacy tools:
>
> ```bash
> weblens configure xhs-cookies
> ```
>
> This explicit command saves/imports the user-supplied same-domain xiaohongshu.com cookie set; confirm the
> cookie names and scope first. Cookies from domains other than xiaohongshu.com are ignored.
>
> **Desktop computers (OpenCLI recommended):**

```bash
weblens install --system --channels opencli
```

> After installing, guide the user through the one manual step (a Chrome security restriction; it cannot be done on their behalf):
> 1. Open https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
> 2. Click "Add to Chrome"
> 3. Run `opencli doctor` to verify (it succeeded if it shows Extension: connected)
>
> On AUTH_REQUIRED when the user has no existing session, do not log in automatically on the user's behalf; switch to the
> xiaohongshu-mcp / legacy-tool Cookie-Editor route below.
>
> **Servers / headless environments (xiaohongshu-mcp):**
> 1. Download the binary for your platform from https://github.com/xpzouying/xiaohongshu-mcp/releases to `~/.weblens/tools/`
> 2. Start the service (the first run automatically downloads a ~150MB headless browser; wait patiently for it to finish)
> 3. Import cookies manually using the Cookie-Editor flow above
> 4. Connect: `mcporter config add xiaohongshu http://localhost:18060/mcp --scope home`
> 5. Always pass `--timeout 120000` when calling it
>
> **Legacy users (xhs-cli):** an already-installed xhs-cli keeps working as a fallback backend
> (upstream stopped updates in 2026-03; new installs are not recommended); authentication still uses the manual Cookie-Editor
> export flow above.

**Facebook / Instagram (desktop OpenCLI):**
> These two platforms go through OpenCLI: it reuses the user's own Chrome login, does not store account passwords, and does not go through the Meta Graph API approval process. Server/headless environments are not recommended.

```bash
weblens install --system --channels facebook,instagram
```

> After installing:
> 1. Confirm the OpenCLI extension is installed in Chrome and `opencli doctor` passes
> 2. Log in to facebook.com / instagram.com in Chrome
> 3. The Agent calls it directly:
>    ```bash
>    opencli facebook search "query" -f yaml
>    opencli facebook profile zuck -f yaml
>    opencli facebook groups -f yaml
>    opencli instagram search "query" -f yaml     # user search
>    opencli instagram profile nasa -f yaml
>    opencli instagram user nasa -f yaml          # a specific user's recent posts
>    ```
>
> Facebook Groups currently only promises to read the group list/recent activity visible to the logged-in user; it does not promise an API for arbitrary group posts and comments. Instagram's search is a user search, not a site-wide post keyword search; if you get a 429/login error, first have the user log in again in Chrome and reduce the request rate.

**Xueqiu (Snowball) (stock quotes + trending posts):**
> "Xueqiu needs logged-in cookies. Please log in to xueqiu.com in Chrome first, then run:"

```bash
weblens configure --from-browser chrome --platform xueqiu
```

> It only reads and saves the minimal cookies Xueqiu needs; it does not read other platforms along the way.

**Xiaoyuzhou Podcast (Groq Whisper):**
> "Xiaoyuzhou podcast transcription is installed by default; it only needs a free Groq API key."

The script is installed automatically with WebLens; the user only needs to provide the key:

```bash
weblens configure groq-key
```

> **Get a Groq API key (free, no credit card, done in 30 seconds):**
> 1. Open https://console.groq.com
> 2. Log in with a Google/GitHub account (or sign up)
> 3. Left menu → API Keys → Create API Key
> 4. Copy the key (it starts with `gsk_`) and send it to the Agent
>
> **How to use:**
> The user sends a Xiaoyuzhou link to the Agent, and the Agent automatically calls:
> ```bash
> bash ~/.weblens/tools/xiaoyuzhou/transcribe.sh https://www.xiaoyuzhoufm.com/episode/xxxxx
> ```
>
> Automatically downloads the audio → transcodes and splits it → transcribes with Groq Whisper → outputs a full Chinese transcript.
>
> **Free tier and limits:**
> - About 2 hours of audio (7200 seconds) per hour; once exceeded, it recovers automatically after 15 minutes
> - More than enough for listening to a few podcast episodes a day
> - High transcription quality (Whisper large-v3), but no speaker diarization
> - For podcasts longer than 2 hours, processing in batches is recommended

**LinkedIn (optional — mcp-server-linkedin):**
> "Basic LinkedIn content can be read through Jina Reader. Full features (profile details, people and job search) require mcp-server-linkedin."

> **Configuration (stdio recommended):**
> First install `uv` following the official instructions (it also provides `uvx`):
> https://docs.astral.sh/uv/getting-started/installation/
>
> ```bash
> mcporter config add linkedin --command uvx --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home
> ```
>
> `uvx` fetches and starts the latest version of the server on demand; no separate Python package or long-running HTTP service is needed.
>
> **First login (requires a browser UI):**
> ```bash
> uvx mcp-server-linkedin@latest --login
> ```
> When the browser pops up, log in to LinkedIn manually; the login state is saved to `~/.linkedin-mcp/profile/`. On a server without a desktop, run the same login command in a visible desktop such as VNC.
>
> For details, see https://github.com/stickerdaniel/linkedin-mcp-server

**BOSS Zhipin (desktop only — boss-agent-cli + CDP):**

When the user says "Set up BOSS Zhipin for me", the Agent completes the parts that can be automated and leaves only the website login to the user:

1. First explain that it will install an upstream CLI and launch a separate Chrome profile directory, and ask for authorization for system installs.
2. After the user agrees, run:
   ```bash
   weblens install --env=local --system --channels=boss
   ```
3. Launch the dedicated Chrome bound only to the local loopback address, according to your OS:
   ```bash
   # macOS
   open -na "Google Chrome" --args --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"

   # Linux
   google-chrome --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```
   Windows PowerShell:
   ```powershell
   Start-Process chrome.exe -ArgumentList '--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222',"--user-data-dir=$env:USERPROFILE\.boss-chrome-profile",'https://www.zhipin.com/web/geek/job'
   ```
4. Pause and have the **user visually confirm** the login state in the window (an avatar in the top-right corner); if not logged in, have the **user log in
   manually**, scan the code, or solve the slider. The Agent does not ask for account passwords, does not log in on the user's behalf, and must not use `boss status`
   in place of this step — it only validates the local `session.enc` and does not mean this Chrome is logged in.
5. After the user confirms login is complete, run:
   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   weblens doctor    # check the browser wt2 cookie probe result in the boss row message
   ```

> Security boundary: any local process that can reach debugging port 9222 can fully control this Chrome.
> You must use `--remote-debugging-address=127.0.0.1` and must not expose it to the LAN or the public internet; use a
> separate profile and reuse it long-term, do not delete or recreate it each time, and do not switch to the everyday main Chrome by default;
> close the dedicated Chrome when not in use. Boss does not support server/headless environments. Search commands must include
> `--browser-source existing-browser --cdp-url http://localhost:9222`.
>
> Dependency: the boss-agent-cli follow-up split PRs #403–#407 have been merged into upstream master, and the installer pins the upstream
> fixed commit
> `4c991b77086a203173bf08a4cb64a23af6514fe6` rather than following a moving branch. That commit includes
> `browser_source="existing-browser"` (strict CDP), `JobItem.lid`, and `job_card_browser()`. Once upstream publishes a stable release,
> WebLens should switch to a version constraint.

### Step 4: Final check

Run `weblens doctor` one final time and report the results to your user.

### Step 5: Set up daily monitoring (OpenClaw only)

If you are running inside **OpenClaw**, ask your user:

> "WebLens is installed. Would you like me to set up a daily automatic check? It will keep an eye on whether these channels are working and whether there's a new version. It only notifies you when there's a problem and stays quiet otherwise."

If the user agrees, create a **cron job** (daily, `sessionTarget: "isolated"`, `delivery: "announce"`) with this task:

```
Run the weblens watch command.
If the output contains "all good", there is no need to notify the user; finish silently.
If the output contains problems (❌ ⚠️) or a new version (🆕), send the full report to the user and suggest fixes.
If a new version is available, ask the user whether to upgrade (sending this sentence to the user's Agent performs a full update: Update WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md).
```

If the user wants a different agent to handle it, let them choose.

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `weblens install --env=auto` | Read-only dependency and channel check (default) |
| `weblens install --env=auto --system` | Explicitly install/configure core external tools |
| `weblens install --env=auto --system --channels=twitter,xiaohongshu` | Install approved optional channels |
| `weblens install --env=local --system --channels=boss` | Install the desktop BOSS Zhipin strict-CDP backend |
| `weblens install --env=auto --system --channels=all` | Install everything after explicit approval |
| `weblens install --env=auto --safe` | Compatibility alias for the safe default |
| `weblens install --env=auto --dry-run` | Preview what would be done |
| `weblens doctor` | Show channel status |
| `weblens watch` | Quick health + update check (for scheduled tasks) |
| `weblens check-update` | Check for new versions |
| `weblens configure twitter-cookies` | Saves Twitter cookies via hidden input; direct calls still need explicit environment variables |
| `weblens configure proxy` | Saves the proxy address via hidden input; not an automatic unlock switch |
| `weblens configure groq-key` | Configures the Xiaoyuzhou transcription key via hidden input |

After installation, use upstream tools directly. See SKILL.md for the full command reference:

| Platform | Upstream Tool | Example |
|----------|--------------|---------|
| Twitter/X | `twitter` (fallback `opencli`) | After setting `TWITTER_AUTH_TOKEN` / `TWITTER_CT0`, run `twitter search "query" -n 10` |
| YouTube | `yt-dlp` | `yt-dlp --dump-json URL` |
| Bilibili | `bili` (subtitles via `opencli`) | `bili search "query" --type video` / `opencli bilibili subtitle BVxxx` |
| Reddit | `opencli` (fallback `rdt`) | `opencli reddit search "query" -f yaml` / `rdt read POST_ID` |
| Facebook | `opencli` | `opencli facebook search "query" -f yaml` |
| Instagram | `opencli` | `opencli instagram user nasa -f yaml` |
| GitHub | `gh` | `gh search repos "query"` |
| Web | `curl` + Jina | `curl -s "https://r.jina.ai/URL"` |
| Exa Search | `mcporter` | `mcporter call exa.web_search_exa query="..." numResults=5` |
| Xiaohongshu (RedNote) | `opencli` (servers: `mcporter`) | `opencli xiaohongshu search "query" -f yaml` |
| Xiaoyuzhou podcasts | `transcribe.sh` | `bash ~/.weblens/tools/xiaoyuzhou/transcribe.sh <URL>` |
| LinkedIn | `mcporter` | `mcporter call linkedin.get_person_profile linkedin_username="..."` |
| BOSS Zhipin | `boss` / Python public API | `weblens doctor` (browser wt2 probe; `boss status` only reflects the local session.enc); for search and JDs see `references/career.md` |
| RSS | `feedparser` | `python3 -c "import feedparser; ..."` |

> For multi-backend platforms, `active_backend` in `weblens doctor --json` is authoritative.
