# Social Media & Communities

Global: Twitter/X, Reddit, Facebook, Instagram. China pack: Xiaohongshu (RedNote), Bilibili, V2EX.

> **Shell safety**: pass every URL/query from the user or from web content as ONE single-quoted
> argument (`'...'`), never unquoted or interpolated. Reject input containing `$(`, a backtick,
> a single quote, or a newline instead of running it.

## Default: `weblens read` / `weblens search`

```bash
weblens read 'https://x.com/user/status/ID'                   # twitter-cli: tweet / article
weblens read 'https://www.reddit.com/r/sub/comments/ID/slug/' # OpenCLI or rdt-cli: post + comments
weblens read 'https://www.v2ex.com/t/TOPIC_ID'                # V2EX API: topic + replies
weblens read 'https://www.bilibili.com/video/BVxxx'           # bili-cli
weblens read 'NOTE_URL'                                       # Xiaohongshu via OpenCLI (full URL with xsec_token)

weblens search 'query' -s twitter
weblens search 'query' -s reddit
weblens search 'query' -s v2ex                                # Exa site:v2ex.com
```

These call the platform's **active backend** from `weblens doctor --json`, passing saved
Twitter cookies to the child process. When no backend works, `read` falls back to Jina
Reader and `search` to Exa restricted to the site; the output `notes` say so, and the content
may be partial or logged-out. For timelines, comments paging, feeds, profiles, groups, or
anything else, use the per-backend commands below.

# Global platforms

## Twitter/X (twitter-cli)

### Authentication prerequisites

Cookies saved via hidden input by `weblens configure twitter-cookies` are only used by
`weblens doctor` to check whether explicit credentials are complete. `doctor` does not run the upstream
`twitter status`, and it does not configure the current shell. Before running any of the `twitter` commands below,
you must explicitly provide the following in the same shell or subprocess environment
(`weblens read` / `weblens search` pass the saved values to their own child process
automatically):

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
```

### Stable commands

```bash
# Home timeline (most stable)
twitter feed -n 20

# Read a single tweet (including replies)
twitter tweet 'URL_OR_ID'

# Read a long-form post / X Article
twitter article 'URL_OR_ID'

# User timeline
twitter user-posts @username -n 20

# User profile
twitter user @username
```

### Potentially unstable commands

```bash
# Search tweets (Twitter frequently changes its GraphQL endpoints, may 404)
twitter search 'query' -n 10

# likes (since 2024 you can only see your own; platform restriction)
twitter likes
```

### Retry chain when search fails (run in order, stop at the first success)

1. Retry once directly (sporadic failures are common): `twitter search 'query' -n 10`
2. Reinstall the version WebLens pins and try again: `pipx install --force 'twitter-cli==0.8.5' && twitter search 'query' -n 10`
3. Switch to the OpenCLI fallback (desktop, reuses browser login session): `opencli twitter search 'query' -f yaml`
4. If none of those work, route around it with stable commands such as `twitter feed` / `twitter user-posts @somebody`

### Important notes

> **Installation**: `weblens install --env=auto --system --channels=twitter` (installs the pinned `twitter-cli==0.8.5`)
>
> **Authentication**: Only use Cookie-Editor manual export, then explicitly set the environment variables
> `TWITTER_AUTH_TOKEN` + `TWITTER_CT0`; do not rely on automatic browser reads.
>
> **IP risk control**: Do not make frequent calls from VPS/data-center IPs, especially followers/following, as this risks account suspension. Use a residential proxy or a local environment.
>
> **OpenCLI fallback**: If OpenCLI is installed on the desktop, the full `opencli twitter search/article/user-posts -f yaml` set is available (browser login session, no cookie environment variables needed).
>
> **Output format**: Use `--yaml` or `--json` for structured output, which is friendlier for AI agents.

## Reddit (multi-backend, login session required)

**Reddit has no zero-config path**: the anonymous `.json` endpoints are blocked (403), and since 2025-11 the official API's manual review process almost never approves requests. Both backends rely on a login session; first run `weblens doctor --json` to see reddit's `active_backend`. Access from mainland China requires a proxy.

### Backend A: OpenCLI (desktop, preferred, reuses browser login session)

```bash
# Search posts
opencli reddit search 'query' -f yaml

# Read full post + comments
opencli reddit read POST_ID -f yaml

# Browse a subreddit / hot / Popular
opencli reddit subreddit LocalLLaMA -f yaml
opencli reddit hot -f yaml
opencli reddit popular -f yaml

# Subreddit metadata (subscriber count, description)
opencli reddit subreddit-info LocalLLaMA -f yaml
```

> Requires Chrome to be open and reddit.com to have been logged in to in the browser.

### Backend B: rdt-cli (legacy/server fallback, upstream unmaintained since 2026-03)

```bash
rdt search 'query' --limit 10   # Search posts
rdt read POST_ID                # Read full post + comments
rdt sub python --limit 20       # Browse a subreddit
rdt popular --limit 10          # Browse popular
rdt all --limit 10              # Browse /r/all
```

> **Installation**: `pipx install 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66'` (PyPI lags upstream; this is the same pinned commit `weblens install --channels=reddit` uses). Run `rdt login` first before you can search and read (on a server without a browser, write the cookie manually; see the doctor hint).
> Use `--yaml` output, which is friendlier for AI agents.

### Advanced option: official API + PRAW (only for users who already have credentials)

Users who registered a Reddit script app before 2025-11 (and hold a client_id/client_secret) can use PRAW with the official API (100 QPM free). New applications require manual review and personal projects are almost never approved, so **do not recommend this path to new users**.

## Facebook (OpenCLI, login session required)

Facebook goes through OpenCLI, reusing the facebook.com login session in the user's Chrome. First run `weblens doctor --json` to see facebook's `active_backend`; it should normally be `OpenCLI`. Do not recommend Jina/Exa/Graph API as the default path.

```bash
# Search users / pages / posts
opencli facebook search 'query' -f yaml

# User or page info
opencli facebook profile zuck -f yaml

# Current account's News Feed
opencli facebook feed --limit 10 -f yaml

# Groups visible to the current account / recent activity
opencli facebook groups --limit 20 -f yaml
```

> Requires Chrome to be open with the OpenCLI extension installed and logged in to facebook.com. Facebook Groups currently only promises reading the list of groups visible to the current account / recent activity; it does not promise an API for arbitrary group posts and comments.

## Instagram (OpenCLI, login session required)

Instagram goes through OpenCLI, reusing the instagram.com login session in the user's Chrome. First run `weblens doctor --json` to see instagram's `active_backend`; it should normally be `OpenCLI`. Do not revert to instaloader by default; historically it has been unstable with cookies/401/429.

```bash
# Search users (not a site-wide post keyword search)
opencli instagram search 'query' -f yaml

# User profile
opencli instagram profile nasa -f yaml

# User's recent posts
opencli instagram user nasa --limit 12 -f yaml

# Explore / Discover
opencli instagram explore --limit 20 -f yaml

# Current account's saved posts
opencli instagram saved --limit 20 -f yaml
```

> Requires Chrome to be open with the OpenCLI extension installed and logged in to instagram.com. `instagram search` is a user search; to read posts, first determine the username, then use `instagram user USERNAME`. If you get 429 / login required, first have the user log in again in Chrome and reduce the request rate.

# China pack

## Xiaohongshu / XiaoHongShu (multi-backend)

Xiaohongshu has three backends. **First run `weblens doctor --json` to see which `active_backend` xiaohongshu has**, then use the matching command group.

### Backend A: OpenCLI (desktop, preferred)

```bash
# Search notes
opencli xiaohongshu search 'query' -f yaml

# Read note body + engagement data (use the full URL from search results, including xsec_token)
opencli xiaohongshu note 'NOTE_URL' -f yaml

# Comments (supports nested replies)
opencli xiaohongshu comments NOTE_ID -f yaml

# Home page recommendation feed
opencli xiaohongshu feed -f yaml

# Public notes on a user's profile
opencli xiaohongshu user USER_ID -f yaml
```

> Requires Chrome to be open with the OpenCLI extension installed. OpenCLI only uses a Chrome session that
> already exists and that the user explicitly controls; WebLens does not log in on the user's behalf and does not read browser cookies.
> `weblens configure xhs-cookies` does not inject cookies into OpenCLI.
> If there is no existing session, do not log in automatically; switch to backend B/C and follow the matching
> Cookie-Editor manual export flow to configure it.

### Backend B: xiaohongshu-mcp (server scenarios)

```bash
# Before authenticating, have the user export manually with Cookie-Editor, then import explicitly
weblens configure xhs-cookies

# Read-only check of the current status
mcporter call xiaohongshu.check_login_status --timeout 120000

# Search
mcporter call xiaohongshu.search_feeds keyword='query' --timeout 120000

# Note details + comments (take feed_id and xsec_token from search results)
mcporter call xiaohongshu.get_feed_detail feed_id="..." xsec_token="..." --timeout 120000
```

> The first call automatically downloads a headless browser of about 150MB, so always pass `--timeout 120000`.
> Authentication only goes through Cookie-Editor manual export; after importing, run `check_login_status` first.
> This explicit command saves/imports the user-provided set of same-domain xiaohongshu.com cookies; the user should
> confirm the scope. Cookies from domains other than xiaohongshu.com are ignored.

### Backend C: xhs-cli (legacy fallback, upstream unmaintained since 2026-03)

```bash
xhs search 'query'          # Search
xhs read NOTE_ID_OR_URL     # Read a note (must use the URL/ID from search results, not a bare note_id)
xhs comments NOTE_ID_OR_URL # Comments
xhs hot                     # Trending
xhs feed                    # Recommendations
```

> Known to be unstable: `xhs user` / `xhs user-posts` / `xhs favorites` may return an API error (upstream is unmaintained and nobody fixes it). New users should go straight to backend A/B.

### General notes

> **Auth boundary**: WebLens must not perform a Xiaohongshu login on the user's behalf, nor read browser
> cookies. OpenCLI may only use a Chrome session the user already has and explicitly controls;
> xiaohongshu-mcp / legacy tools use Cookie-Editor manual export.
>
> **xsec_token restriction**: Xiaohongshu enforces an xsec_token mechanism, so **you cannot read using a bare note_id**. Correct flow: first get results from search/feed, then read using the full URL/ID from those results. This is the same for all three backends.
>
> **Rate limiting**: High-frequency requests (bulk searches, deep comment paging) trigger CAPTCHAs; this is a platform restriction that cannot be bypassed. Leave 2-3 seconds between operations.
>
> **Write operations (posting/commenting/liking)**: Read-only is recommended. xhs-cli v0.6.x write operations may return 406 due to signing issues.

## Bilibili

> ⚠️ **Do not use yt-dlp to read Bilibili** (anti-bot controls now block it across the board with 412; no workaround found in testing). Use bili-cli / OpenCLI.

```bash
# Search / trending / video details (bili-cli, read-only, no login needed)
bili search 'query' --type video -n 5
bili hot -n 10
bili video BVxxx

# Subtitles (OpenCLI, requires desktop Chrome)
opencli bilibili subtitle BVxxx
```

> For detailed commands (audio transcription, direct API fallback), see [references/video.md](video.md).

## V2EX (public API)

No authentication needed; call the public API directly.

### Hot topics

```bash
curl -s 'https://www.v2ex.com/api/topics/hot.json' -H "User-Agent: weblens/1.0"
```

### Node topics

```bash
# node_name e.g.: python, tech, jobs, qna, programmers
curl -s 'https://www.v2ex.com/api/topics/show.json?node_name=python&page=1' -H "User-Agent: weblens/1.0"
```

### Topic details

```bash
# Get topic_id from the URL, e.g. https://www.v2ex.com/t/1234567
curl -s 'https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID' -H "User-Agent: weblens/1.0"
```

### Topic replies

```bash
curl -s 'https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1' -H "User-Agent: weblens/1.0"
```

### User info

```bash
curl -s 'https://www.v2ex.com/api/members/show.json?username=USERNAME' -H "User-Agent: weblens/1.0"
```

### Python usage example

```python
from weblens.channels.v2ex import V2EXChannel

ch = V2EXChannel()

# Get hot topics
topics = ch.get_hot_topics(limit=10)
for t in topics:
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} replies)")

# Get node topics
node_topics = ch.get_node_topics("python", limit=5)

# Get topic details + replies
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])

# Get user info
user = ch.get_user("Livid")
```

> **Node list**: https://www.v2ex.com/planes
