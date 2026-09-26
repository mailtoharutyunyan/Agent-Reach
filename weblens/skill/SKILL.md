---
name: weblens
description: >
  MUST USE when user wants to research/search/look up/find anything online
  — e.g. research X across the web / look up X / search X / what do people
  think of X / discussion of X / research this topic.

  Also MUST USE when user mentions any platform or shares any URL/link:
  Xiaohongshu/xhs, Twitter/X, Bilibili, Reddit, Facebook, Instagram, V2EX,
  LinkedIn/BOSS Zhipin/jobs, YouTube, GitHub code search, Xiaoyuzhou podcasts,
  Xueqiu/stock quotes, RSS feeds, or any web URL.

  16 platforms, multi-backend routing (OpenCLI / per-platform CLIs / APIs).
  Zero config for 6 channels. Run `weblens doctor --json` to see which
  backend serves each platform right now.

  NOT for: reports/analysis/translation (this skill only fetches content);
  posting/commenting/liking; platforms with a dedicated skill (use that first).

  [Routing] SKILL.md has the routing table + common commands; complex cases: read references/*.md.
  Categories: search / social / career / dev / web / video / finance.
metadata:
  homepage: https://github.com/YOUR_GITHUB_USER/weblens
---

# WebLens — Internet Capability Router

16 platforms, multiple backends. **When this skill exists, you must use it to access these platforms — do not invent your own approach.**

## Standing rules (apply throughout)

1. **Health-check before acting**: for multi-backend/login-backed platforms (Xiaohongshu/Reddit/Bilibili/Twitter/Facebook/Instagram/BOSS Zhipin), first run
   `weblens doctor --json`. When `active_backend` has a value, pick the command group accordingly; `active_backend: null`
   means Doctor skipped live verification to avoid triggering browser cookie reads or remote writes, not that the backend does not exist.
   Doctor results are a "point-in-time snapshot"; channels/login state may have changed. If you suspect something has gone stale before running a read-only command,
   re-confirm using the "Health check and recovery" runbook in the matching reference (e.g. the BOSS Zhipin CDP troubleshooting in career.md).
2. **Announce what you are using**: before starting work, say "using weblens platform X / backend Y".
3. **Handle failures with the retry chains in references**; do not guess commands.
4. **Web-wide research tasks**: combine multiple platforms (Exa search + Twitter/Reddit for discussions + Xiaohongshu/Bilibili for Chinese perspectives), collect in parallel, then synthesize.
5. **Watch versions for the user**: after finishing a substantial research/multi-platform task, also run
   `weblens check-update` (fast, one API call). If there is a new version, add one line to your wrap-up:
   "WebLens vX.Y.Z is available — copy this sentence to me to update: Help me update WebLens:
   https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md".
   Do not interrupt the current task to update, and do not remind about the same version more than once.

## Routing table

| User intent | Category | Details |
|---------|------|---------|
| Web search / code search | search | [references/search.md](references/search.md) |
| Xiaohongshu/Twitter/Bilibili/V2EX/Reddit/Facebook/Instagram | social | [references/social.md](references/social.md) |
| Recruiting/jobs/LinkedIn/BOSS Zhipin | career | [references/career.md](references/career.md) |
| GitHub/code | dev | [references/dev.md](references/dev.md) |
| Web pages/articles/RSS | web | [references/web.md](references/web.md) |
| YouTube/Bilibili/podcast transcripts | video | [references/video.md](references/video.md) |
| Xueqiu/stock quotes | finance | [references/finance.md](references/finance.md) |

## Zero-config quick commands

```bash
# Exa web search
mcporter call exa.web_search_exa query="query" numResults=5

# General web page reading
curl -s "https://r.jina.ai/URL"

# GitHub search
gh search repos "query" --sort stars --limit 10

# YouTube subtitles (note: do not use yt-dlp for Bilibili; see video.md for the retry chain)
yt-dlp --write-sub --write-auto-sub --skip-download -o "/tmp/%(id)s" "URL"

# V2EX hot topics
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: weblens/1.0"

# Bilibili search (bili-cli, no login needed)
bili search "query" --type video -n 5
```

## Login-backed platforms (pick commands by doctor's active_backend)

Twitter note: cookies saved by `weblens configure twitter-cookies` are only for
`doctor` to check whether configuration is complete; `doctor` does not run `twitter status`, and does not configure the current
shell. Before running `twitter` directly, you must explicitly provide
`TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the subprocess environment, and must not expose their values in logs or command echo.

Xiaohongshu note: WebLens does not log in on the user's behalf and does not read browser cookies. OpenCLI only uses
a Chrome session the user already has and explicitly controls; if there is no existing session, do not log in automatically — instead
export manually with Cookie-Editor and configure xiaohongshu-mcp / legacy tools.

BOSS Zhipin setup trigger: when the user says "set up BOSS Zhipin for me", first read the Boss section of `references/career.md`,
then, after getting installation approval, run
`weblens install --env=local --system --channels=boss`. The agent is responsible for launching, per OS, a dedicated Chrome
bound only to `127.0.0.1:9222`; **the first step after launching is to pause and have the user visually confirm**
that the window is in a logged-in state (avatar in the top-right corner). If not logged in, have the user log in / scan the code; after the user confirms, run
`boss --cdp-url http://localhost:9222 login --cdp` and `weblens doctor` to verify.
Do not make the user figure out port parameters themselves.
The dedicated Chrome profile must be reused long-term; do not create a new one each time, and do not switch to the user's everyday main Chrome by default.

To judge the CDP browser's login state, **do not trust `boss status`** (it only checks the local session.enc, and it and the
browser login state do not represent each other). Rely on `weblens doctor`'s browser cookie probe (wt2),
combined with the user's visual confirmation. Never judge login state from the current page URL:
the `security-check` / `zhipin-security` / `_security_check` security verification pages are Boss anti-scraping challenges
and have nothing to do with login — they appear even when logged in (almost always with a Chrome that has a CDP debugging port). When you see one, do not
treat it as "not logged in"; first run `weblens doctor` to check the browser cookie, then decide whether the user needs to log in.
A search reporting `AUTH_EXPIRED` is the ground truth that the browser is not logged in: go straight to the login flow + `login --cdp`,
and do not interpret it as a security-verification issue.

When running searches you must use
`boss --browser-source existing-browser --cdp-url http://localhost:9222 search ...`;
on `ENVIRONMENT_RISK`, stop immediately — do not refresh, do not log in again, do not retry automatically.

```bash
# Twitter search (twitter-cli preferred; see social.md for the retry chain)
twitter search "query" -n 10

# Reddit (no zero-config path: OpenCLI or rdt-cli, login session required)
opencli reddit search "query" -f yaml   # desktop
rdt search "query" --limit 10            # legacy/server

# Xiaohongshu (OpenCLI preferred on desktop)
opencli xiaohongshu search "query" -f yaml

# Facebook / Instagram (desktop OpenCLI, reuses browser login session)
opencli facebook search "query" -f yaml
opencli facebook groups -f yaml
opencli instagram search "query" -f yaml       # search users
opencli instagram user USERNAME -f yaml        # read a given user's recent posts
```

## Environment check

> The local Python environment defaults to conda `dl`; if `weblens` is not on PATH, use the
> `conda run -n dl weblens ...` prefix.

```bash
# Check available channels and the currently active backend for each platform
conda run -n dl weblens doctor --json
```

## OpenCLI adapter discovery

When the routing table does not cover the platform or command the user needs, first use `opencli list` to find existing adapters, then use
`opencli <platform> --help` to view the public commands. Discovering an adapter only proves the command exists, not that the login state or
target content is available; only run read-only commands when the user's task clearly requires that platform, and verify by actual non-empty content.

## Workspace rules

**Do not create files in the agent workspace.** Use `/tmp/` for temporary output and `~/.weblens/` for persistent data.

## Detailed docs

Based on the user's needs, read the matching detailed doc:

- [Search tools](references/search.md) — Exa AI search
- [Social media](references/social.md) — Xiaohongshu, Twitter, Bilibili, V2EX, Reddit, Facebook, Instagram (multi-backend/login-backed command groups)
- [Careers & recruiting](references/career.md) — LinkedIn, BOSS Zhipin
- [Developer tools](references/dev.md) — GitHub CLI
- [Web reading](references/web.md) — Jina Reader, RSS
- [Video & podcasts](references/video.md) — YouTube, Bilibili, Xiaoyuzhou
- [Finance & market data](references/finance.md) — Xueqiu stock quotes, search, trending content

## Configuring channels

If a channel needs configuration, get the installation guide:
https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md

The user only needs to provide cookies; the agent handles all other configuration.
