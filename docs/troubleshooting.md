# Troubleshooting

Start with `weblens doctor` (or `weblens doctor --json`). Every channel that is not ✅
comes with a message and, where possible, the exact fix.

## General: reading errors

- **Exit codes:** `0` success, `1` the command failed (the message ends with a hint), `2`
  bad usage — an invalid URL, an unknown `--source`, a bad flag, a `--limit` outside 1–50,
  or a query that starts with `-`.
- **Full traceback:** add `--debug` (for example `weblens --debug read 'URL'`). `-v` shows
  debug logs without the traceback.
- **`error: invalid URL ...: pass a public http(s) URL`:** `weblens read` refuses
  localhost, private and link-local IPs, and internal hostnames (`.local`, `.internal`,
  `.lan`, cloud metadata). This is intentional: those URLs would otherwise be sent to a
  third-party reader. Fetch internal pages with your own tools.
- **A note says "read via Jina Reader instead — content may be partial":** the URL
  belongs to a platform whose backend is not working (or has no reader for that page
  type), so WebLens fell back to the generic reader. Run `weblens doctor` to see which
  backend is missing, then set it up (see [install.md](install.md)).

---

## YouTube: HTTP 429 / "subtitles skipped"

**Symptom:** `weblens read` on a YouTube URL returns metadata but the notes say
`subtitles skipped: YouTube rate limited subtitle downloads (HTTP 429)`, or yt-dlp fails
with `HTTP Error 429: Too Many Requests`.

**Cause:** YouTube rate-limits subtitle and video requests per IP. Data-center and VPN IPs
hit it quickly. WebLens already retries the subtitle download once, more slowly.

**Solutions:**

1. Wait a few minutes and retry. Avoid reading many videos in a burst.
2. Update yt-dlp; YouTube changes often:
   ```bash
   python -m pip install -U 'yt-dlp[default]'
   ```
3. If YouTube asks you to sign in or confirm you are not a bot, log in to YouTube in a
   browser and tell WebLens to use its cookies. `weblens read` / `weblens search -s youtube`
   then pass `--cookies-from-browser <browser>` to yt-dlp (supported: brave, chrome,
   chromium, edge, firefox, opera, safari, vivaldi, whale):
   ```bash
   weblens configure youtube-cookies chrome
   ```
   Calling yt-dlp directly works too:
   ```bash
   yt-dlp --cookies-from-browser chrome --write-sub --write-auto-sub --skip-download -o '/tmp/%(id)s' 'URL'
   ```
4. Use the fallbacks in the skill's `references/video.md`: `opencli youtube transcript 'URL' -f yaml`
   on desktop, or `weblens transcribe 'URL'` to transcribe the audio.

---

## GitHub: "GitHub API rate limit exceeded"

**Symptom:** `weblens read 'https://github.com/...'` or `weblens search '...' -s github`
fails with `GitHub API rate limit exceeded`.

**Cause:** without credentials WebLens uses the public GitHub REST API, which allows
**60 requests per hour** per IP. Reading one issue with comments can take several requests.

**Solution:** authenticate the GitHub CLI once. WebLens uses `gh` automatically when it is
logged in (or when `GH_TOKEN` / `GITHUB_TOKEN` is set), which raises the limit to 5,000
requests per hour. Without `gh`, a token from `GH_TOKEN` / `GITHUB_TOKEN` or saved with
`weblens configure github-token` is sent to the REST API instead (env vars win):

```bash
brew install gh        # or see https://cli.github.com for other platforms
gh auth login
gh auth status
```

The first line of the output shows which backend served the request
(`github via gh CLI`, `github via GitHub REST API (token)` or
`github via GitHub REST API (public)`).

---

## Web search: "web search unavailable" / Exa not configured

**Symptom:** `weblens search 'query'` prints a note like
`web search unavailable (...); fell back to hackernews + wikipedia`, or
`--source v2ex` / `reddit` / `twitter` fails with a hint to configure Exa.

**Cause:** web search uses Exa's free MCP endpoint through mcporter. Either mcporter is not
installed or the `exa` server is not registered.

**Solution:**

```bash
npm install -g 'mcporter@0.14.1'           # skip if `mcporter --version` works
mcporter config add exa https://mcp.exa.ai/mcp --scope home
mcporter list exa                          # should list web_search_exa
weblens search 'test query' --limit 3
```

`weblens install --env=auto --system` does both steps for you. No API key is needed.

---

## Stack Overflow: quota exhausted / throttled

**Symptom:** `weblens search '...' -s stackoverflow`, or reading a Stack Exchange URL, fails
with `Stack Exchange API error 502 (throttle_violation)` or another quota message; with `-v`
you may see `Stack Exchange keyless quota low: N of 300 requests left today`. Requests may
also pause for a few seconds before returning.

**Cause:** keyless Stack Exchange API access allows about **300 requests per day per IP**.
The API can also tell clients to back off for some seconds; WebLens waits automatically
when it does.

**Solution:** wait for the daily quota to reset, or run from a different network. In the
meantime, find questions with web search and read them through Jina Reader:

```bash
weblens search 'site:stackoverflow.com your error message'
curl -s 'https://r.jina.ai/https://stackoverflow.com/questions/ID'
```

---

## Twitter/X: twitter-cli connection fails

**Symptom:** `twitter search` or other commands return an error

**Cause:** twitter-cli needs the `TWITTER_AUTH_TOKEN` and `TWITTER_CT0`
environment variables to access the Twitter API. The values saved by `weblens configure twitter-cookies`
are only used by doctor to check whether the configuration is complete; doctor does not perform upstream authentication and does not set the current
shell. If your network requires a proxy to reach x.com, you also need to configure a proxy.

**Solutions:**

### Option 1: Set proxy environment variables

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search 'test' -n 1
```

### Option 2: Use a global proxy tool

Let a proxy tool take over all network traffic so twitter-cli's requests also go through the proxy:

```bash
# macOS — enable "Enhanced Mode" in ClashX / Surge
# Linux — proxychains or tun2socks
proxychains twitter search 'test' -n 1
```

### Option 3: Skip twitter-cli and use Exa search instead

When twitter-cli is unavailable, you can search Twitter content with Exa:

```bash
mcporter call exa.web_search_exa query='site:x.com search terms' numResults=5
# or, via WebLens (uses the active backend, else Exa site:x.com):
weblens search 'search terms' --source twitter
```

### Option 4: Check authentication

```bash
twitter check
```

> If it returns "Missing credentials", you need to set
> `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the environment of the process running that command.
>
> **Fallback:** If you have already installed bird CLI (`npm install -g @steipete/bird`), it works fine too. WebLens automatically detects installed tools.

---

# China pack

## Xueqiu (Snowball): API returns 400

**Symptom:** `weblens doctor` shows Xueqiu as ⚠️ and reports `HTTP Error 400`

**Cause:** The Xueqiu API requires a logged-in cookie; it cannot be accessed anonymously.

**Solution:** Log in to xueqiu.com in Chrome, then run:

```bash
weblens configure --from-browser chrome --platform xueqiu
```

Run `weblens doctor` again to confirm it is back to ✅. When the cookie expires, just run it again.

---

## BOSS Zhipin: `boss status` says logged in, but search reports `AUTH_EXPIRED`

**Symptom:** `boss status` / `status --live` returns `logged_in: true` (sometimes even with a username),
but `boss ... search` immediately reports `{"code": "AUTH_EXPIRED", ...}` with a "user not logged in" message.
The dedicated Chrome may also be stuck on a URL containing `_security_check`, which looks like an anti-bot slider.

**Cause:** Boss has two login-state stores, which authenticate different channels:

| Store | Who uses it |
|---|---|
| `~/.boss-agent/auth/session.enc` | `boss status` / `status --live`; low-risk operations on the httpx channel (`detail` / `cities` / `job_card_httpx`). CDP search also reads it (if it can't be read, it fails immediately with "not logged in"), but when reusing a real Chrome context its cookies never actually take effect |
| Browser cookies inside `~/.boss-chrome-profile` | The credentials actually sent by high-risk operations such as search / greet in `existing-browser` strict CDP mode |

`boss status` only validates the local session.enc. When the local store holds stale credentials from days ago and the dedicated Chrome
profile itself is not logged in, it still reports `logged_in: true`; this is not proof of a valid login state.
Meanwhile, the `_security_check` page is an anti-bot challenge that **appears even when logged in**, so it cannot be used to judge login state;
together, these make it easy to misdiagnose "browser not logged in" as "stuck on a slider".

> Do not delete either store. If session.enc is missing, CDP search fails before it even connects to the browser;
> when you need to refresh it, run `login --cdp` instead of deleting files by hand.

**Order of judgment:**

1. `AUTH_EXPIRED` is the ground truth: whenever it appears, the browser is not logged in, regardless of what `boss status` says;
2. The boss row in `weblens doctor` directly probes whether the browser has a `wt2` cookie; trust it;
3. `boss status` is for reference only; the page URL is never used as a signal.

**Solution:** In the dedicated Chrome window, visually confirm and manually log in to zhipin.com, then sync the login state:

```bash
boss --cdp-url http://localhost:9222 login --cdp
weblens doctor    # the boss row message should show "Login cookie present in browser (wt2)"
```

> After launching the dedicated Chrome, the first step is always to have the user visually confirm the login state; do not substitute `boss status` for that.
