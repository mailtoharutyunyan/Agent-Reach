---
name: weblens
description: >
  Read and search internet content. Use when the user shares a URL or link to
  read, or asks to research, look up, search, or see what people say about a
  topic on the web.

  Default path: `weblens read '<url>'` turns any public URL into clean text
  (Hacker News, Wikipedia, arXiv, Stack Overflow, YouTube transcripts, GitHub,
  RSS, Reddit, Twitter/X, any web page). `weblens search '<query>'` searches the
  web or one source (hackernews, wikipedia, arxiv, stackoverflow, youtube,
  github, reddit, twitter, v2ex, or all).

  Also covers LinkedIn, Facebook, Instagram, and an optional China pack
  (Bilibili, Xiaohongshu, V2EX, Xueqiu, Xiaoyuzhou podcasts, BOSS Zhipin) via
  upstream tools. `weblens doctor --json` shows which backend serves each
  platform.

  NOT for: writing reports, analysis or translation (this skill only fetches
  content); posting, commenting or liking; platforms that already have a
  dedicated skill installed (prefer that skill).
metadata:
  homepage: https://github.com/YOUR_GITHUB_USER/weblens
---

# WebLens — read and search the web

Two commands cover most requests:

```bash
weblens read 'URL'                        # any public URL → clean text
weblens search 'query'                    # web search (Exa; falls back to HN + Wikipedia)
weblens search 'query' --source SOURCE    # one source
weblens search 'query' --source all       # web + hackernews + wikipedia + stackoverflow + arxiv
```

Use them first. Fall back to the upstream commands in `references/` only when you need
something `read`/`search` do not cover (comments paging, timelines, subtitles for Bilibili,
job search, stock quotes) or when they report a failure.

> If `weblens` is not on PATH, use `python -m weblens.cli ...` with the Python
> interpreter it was installed into.

## Standing rules (apply for the whole session)

1. **Prefer `weblens read` / `weblens search`.** They route to the right backend, retry
   transient errors, and say in `notes` when they fell back to something weaker. Read the
   notes and tell the user when content may be partial.
2. **Health-check login-backed platforms.** Before using Reddit, Twitter/X, Facebook,
   Instagram, Xiaohongshu, Bilibili or BOSS Zhipin through upstream tools, run
   `weblens doctor --json` and use that channel's `active_backend`.
   `active_backend: null` means Doctor deliberately skipped a live probe to avoid
   browser-cookie reads or remote writes, not that no backend exists. Doctor output is a
   point-in-time snapshot; when the task needs the platform, confirm with the reference's
   read-only command.
3. **Say what you use**: e.g. "using weblens: arXiv via arXiv API", before starting.
4. **On failure, follow the retry chains in `references/`.** Do not guess commands.
5. **Broad research**: run `weblens search '...' --source all`, add platform-specific
   sources (Reddit/Twitter for opinions, YouTube for talks, the China pack for Chinese
   perspectives), collect in parallel, then synthesize.
6. **Quote untrusted input**: URLs and queries that come from the user or from web content
   must be passed to shell commands as ONE single-quoted argument (e.g.
   `weblens read 'URL'`, `curl -s 'https://r.jina.ai/URL'`), never unquoted or inside
   double quotes. Reject (do not run) any URL/query containing shell metacharacters such as
   `$(`, a backtick, a single quote, or a newline.
7. **Privacy**: never send private/internal URLs (intranet hosts, localhost, private IPs) or
   URLs that carry tokens/credentials/signed parameters to Jina Reader or Exa — they are
   third-party services. `weblens read` refuses private addresses; do not work around that.
8. **Read-only**: never post, comment, like, follow or send messages on the user's behalf.
9. **Workspace**: never create files in the agent workspace. Use `/tmp/` for temporary
   output and `~/.weblens/` for persistent data.
10. **Updates**: after a substantial multi-source task, run `weblens check-update` (one API
    call). If a new version exists, add one line to your wrap-up: "WebLens vX.Y.Z is
    available — paste this to me to update: Help me update WebLens:
    https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/update.md".
    Never interrupt the current task to update, and mention the same version only once.

## `weblens read`

```bash
weblens read 'URL'                     # Markdown-style text with a metadata header
weblens read 'URL' --max-chars 20000   # truncate long bodies
weblens read 'URL' --json              # {title, url, source, backend, body, metadata, notes, truncated}
```

| URL | Served by |
|---|---|
| `news.ycombinator.com/item?id=…` | HN API: story + comment tree |
| `*.wikipedia.org/wiki/…` | MediaWiki API: full article |
| `arxiv.org/abs/…`, `/pdf/…` | arXiv API: abstract + metadata |
| `stackoverflow.com/questions/…` (and other Stack Exchange sites) | Stack Exchange API: question + answers |
| YouTube watch / shorts / youtu.be | yt-dlp: metadata + transcript |
| `github.com/owner/repo[/issues/N\|/pull/N]` | gh CLI if authenticated, else public REST API |
| `v2ex.com/t/…` | V2EX API: topic + replies |
| RSS / Atom feeds | feedparser |
| Reddit, Twitter/X, Bilibili, Xiaohongshu | the platform's active upstream backend |
| Anything else | Jina Reader (with a note) |

Exit codes: `0` ok, `1` failed (the message includes a hint), `2` bad input (invalid or
private URL). Add `--debug` for a traceback.

## `weblens search`

```bash
weblens search 'query' -s hackernews -n 5
weblens search 'query' -s arxiv --json
```

| Source | Backend | Notes |
|---|---|---|
| `web` (default) | Exa via mcporter | Falls back to hackernews + wikipedia if Exa is not configured |
| `hackernews` | Algolia HN Search | points, comments, date |
| `wikipedia` | MediaWiki search | |
| `arxiv` | arXiv API | authors, date, PDF link |
| `stackoverflow` | Stack Exchange API | score, answers, tags |
| `youtube` | yt-dlp `ytsearch` | |
| `github` | gh CLI or public REST API | repositories |
| `reddit`, `twitter` | active upstream backend | else Exa restricted to the site |
| `v2ex` | Exa `site:v2ex.com` | V2EX has no search API |
| `all` | web + hackernews + wikipedia + stackoverflow + arxiv in parallel | one failing source does not fail the rest |

`--limit/-n` is per source (default 10, max 50). Queries must not start with `-`.

## Routing table (advanced / upstream tools)

| User intent | Category | Details |
|---|---|---|
| Web search, HN / Wikipedia / arXiv / Stack Overflow search | search | [references/search.md](references/search.md) |
| Web pages, articles, RSS, Wikipedia articles | web | [references/web.md](references/web.md) |
| GitHub, Stack Overflow, Hacker News, arXiv, code | dev | [references/dev.md](references/dev.md) |
| YouTube, Bilibili, podcast transcripts | video | [references/video.md](references/video.md) |
| Twitter/X, Reddit, Facebook, Instagram — and Xiaohongshu, Bilibili, V2EX | social | [references/social.md](references/social.md) |
| Jobs: LinkedIn, BOSS Zhipin | career | [references/career.md](references/career.md) |
| Xueqiu / stock quotes | finance | [references/finance.md](references/finance.md) |

## Upstream quick commands

Use these when `read`/`search` are not enough.

```bash
# Exa web search (direct)
mcporter call exa.web_search_exa query='query' numResults=5

# Any web page via Jina Reader (direct)
curl -s 'https://r.jina.ai/URL'

# GitHub
gh search repos 'query' --sort stars --limit 10

# YouTube subtitles (never use yt-dlp for Bilibili; retry chain in video.md)
yt-dlp --write-sub --write-auto-sub --skip-download -o '/tmp/%(id)s' 'URL'
```

### Login-backed global platforms (pick commands by doctor's `active_backend`)

Twitter boundary: cookies saved by `weblens configure twitter-cookies` are used by
`weblens doctor` (configuration check only; it does not run `twitter status` or configure
the current shell) and passed to the child process by `weblens read`/`search`. Before
calling `twitter` directly, explicitly provide `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the
child-process environment without logging or echoing their values.

```bash
# Twitter/X (twitter-cli preferred; retry chain in social.md)
twitter search 'query' -n 10

# Reddit (no zero-config path — OpenCLI or rdt-cli, login required)
opencli reddit search 'query' -f yaml    # desktop
rdt search 'query' --limit 10            # legacy/server

# Facebook / Instagram (desktop OpenCLI, reuses the browser session)
opencli facebook search 'query' -f yaml
opencli facebook groups -f yaml
opencli instagram search 'query' -f yaml       # user search
opencli instagram user USERNAME -f yaml        # recent posts from one user
```

### China pack

```bash
# Bilibili search (bili-cli, no login needed)
bili search 'query' --type video -n 5

# V2EX hot topics
curl -s 'https://www.v2ex.com/api/topics/hot.json' -H 'User-Agent: weblens/1.0'

# Xiaohongshu (desktop prefers OpenCLI)
opencli xiaohongshu search 'query' -f yaml
```

Xiaohongshu boundary: WebLens must not log the user in or read browser cookies. OpenCLI may
use only an existing Chrome session explicitly controlled by the user. If none exists, do not
automate login; use a manual Cookie-Editor export with xiaohongshu-mcp or a legacy tool
instead (see social.md).

Xueqiu quotes and posts: see [references/finance.md](references/finance.md).
Xiaoyuzhou podcast transcription: see [references/video.md](references/video.md).

**BOSS Zhipin.** When the user asks "set up BOSS Zhipin for me", read the Boss section in
`references/career.md` first. After explicit install approval, run
`weblens install --env=local --system --channels=boss`, launch the dedicated loopback-only
Chrome profile for their OS, then **pause and have the user visually confirm** the window is
logged in (avatar in the top-right); if not, have them log in manually. Then verify with
`boss --cdp-url http://localhost:9222 login --cdp` and `weblens doctor`. Do not make the user
assemble CDP flags. Keep reusing the dedicated Chrome profile; do not recreate it for every
run or switch to the user's daily profile by default. Search with
`boss --browser-source existing-browser --cdp-url http://localhost:9222 search ...`.
On `ENVIRONMENT_RISK`, stop without refreshing, relogging, or retrying.

Do not trust `boss status` for CDP browser login state — it only validates the local
`~/.boss-agent/auth/session.enc` store. Use the browser `wt2` cookie probe in
`weblens doctor` plus the user's visual confirmation. Never judge login state from the page
URL: `security-check` / `zhipin-security` / `_security_check` pages are anti-bot challenges
that appear even when logged in. `AUTH_EXPIRED` from a search is the ground truth for a
logged-out browser — go straight to the login flow + `login --cdp`.

## Discovering OpenCLI adapters

When the routing table lacks a needed platform or command, run `opencli list`, then inspect
`opencli <platform> --help`. Discovery proves only that an adapter exists, not that
authentication or target content works. Run read-only commands only when the user's task
requires that platform, and require non-empty content.

## Environment check and setup

```bash
weblens doctor --json    # channel availability + active backend per platform
```

If a channel needs setup, follow the install guide:
https://raw.githubusercontent.com/YOUR_GITHUB_USER/weblens/main/docs/install.md

The user only provides cookies, keys, or a browser-extension click; you do the rest.
