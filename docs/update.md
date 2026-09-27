# WebLens — Update Guide

## For Humans

Copy this to your AI Agent:

```
Update WebLens for me: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md
```

Or, more briefly:

```
Update WebLens: https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md
```

---

## For AI Agents

### ⚠️ Workspace Rules

**Never create files, clone repos, or run commands in the agent workspace.** Use `/tmp/` for temporary work and `~/.weblens/` for persistent data.

### Goal

Update WebLens to the latest version, refresh upstream tools, migrate from retired backends, and verify everything works. The user should not need to do anything manually (except things only a human can do, like clicking a browser-extension install button).

### Step 1: Check current version

```bash
weblens check-update
```

If it says "Already up to date", skip to Step 5 (verify). Otherwise continue.

### Step 2: Update WebLens package

Use the same method the user originally installed with:

```bash
pipx upgrade weblens                      # installed with pipx from PyPI
pip install --upgrade weblens             # installed with pip / inside ~/.weblens-venv

# Installed from GitHub (or PyPI has no newer release yet):
pipx install --force https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip
pip install --upgrade https://github.com/YOUR_GITHUB_USER/weblens/archive/main.zip
```

> If pip complains about `externally-managed-environment` (PEP 668), the user
> originally installed via pipx or a venv — use the pipx command, or activate
> `~/.weblens-venv` first.

### Step 3: Refresh upstream tools

Run these to bring installed tools to the versions this WebLens release pins
(the same versions `weblens install --system` uses). **Only touch what is
already installed — do not install new tools the user never asked for** (the
one exception: OpenCLI on desktop, see below).

```bash
# Python-based CLIs the user already has — pinned versions
which twitter >/dev/null 2>&1 && { pipx install --force 'twitter-cli==0.8.5' 2>/dev/null || uv tool install --force 'twitter-cli==0.8.5' 2>/dev/null; }
which bili    >/dev/null 2>&1 && { pipx install --force 'bilibili-cli==0.6.2' 2>/dev/null || uv tool install --force 'bilibili-cli==0.6.2' 2>/dev/null; }
which rdt     >/dev/null 2>&1 && pipx install --force 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66' 2>/dev/null

# yt-dlp tracks YouTube changes closely; keep it current
which yt-dlp  >/dev/null 2>&1 && { pipx install --force 'yt-dlp[default]' 2>/dev/null || uv tool install --force 'yt-dlp[default]' 2>/dev/null || python -m pip install -U 'yt-dlp[default]' 2>/dev/null; }

# npm-based — pinned versions
which mcporter >/dev/null 2>&1 && npm install -g 'mcporter@0.14.1' 2>/dev/null
which opencli  >/dev/null 2>&1 && npm install -g '@jackwener/opencli@1.8.8' 2>/dev/null
```

> The pins live in `weblens/commands/install.py` (`_TWITTER_CLI_VERSION`,
> `_BILIBILI_CLI_VERSION`, `_RDT_GIT_SOURCE`, `_MCPORTER_VERSION`,
> `_OPENCLI_VERSION`). If a newer WebLens release changes them, this guide
> changes with it. xhs-cli is unmaintained upstream; leave an existing install
> as it is.

**Desktop users without OpenCLI**: OpenCLI is the preferred
backend for Xiaohongshu/Reddit (and adds Bilibili subtitles). Offer it once. For
Xiaohongshu, OpenCLI may use only an existing Chrome session explicitly controlled
by the user. The update must never log the user in or read browser cookies:

> "This update introduces the OpenCLI backend. Want to install it? Afterwards you
> only need to click 'Add extension' once in the Chrome Web Store. For Xiaohongshu,
> OpenCLI only uses your existing Chrome session; if there is no existing session,
> I won't log in automatically and will set up MCP / legacy tools with Cookie-Editor instead."

If yes: `weblens install --system --channels opencli` and guide them through the
extension click. If no, everything keeps working on existing backends.

### Step 4: Coexistence (DO NOT uninstall old tools)

**Never uninstall tools the user already has.** Retired backends (e.g. yt-dlp
no longer serves Bilibili; xhs-cli is no longer installed by default) keep
working as fallbacks where they still function. WebLens routes around
them automatically — removal is the user's call, not yours.

### Step 5: Verify

```bash
weblens version
weblens doctor
weblens read 'https://en.wikipedia.org/wiki/Web_browser' --max-chars 300
weblens search 'web browser' --source hackernews --limit 3
```

`weblens doctor` only reports status; it does not install or modify skill
files. Run `weblens skill --install` to refresh the bundled skill files.

Check the doctor output:

- Every channel shows ✅ / [!] with a clear message, and multi-backend
  channels (Xiaohongshu/Reddit/Bilibili/Twitter) report `active backend: …`
- If a previously-working channel now shows [X]/error, the message contains
  the exact fix (e.g. a venv-reinstall prescription) — run it, then re-check
- `--json` gives the same data machine-readably (`active_backend` per channel)

### Step 6: Report to user

Tell the user:

1. What version they're on now (`weblens version`)
2. How many channels are available, and which backend each multi-backend
   platform is using (from doctor)
3. Anything that needs their action (e.g. a Chrome extension click, or a
   manual Cookie-Editor export when XiaoHongShu uses MCP / a legacy tool)
4. What changed in this update (release notes shown by `check-update`), for
   example new `weblens read` / `weblens search` sources

Done.
