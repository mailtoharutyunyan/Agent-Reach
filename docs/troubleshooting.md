# Troubleshooting

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
twitter search "test" -n 1
```

### Option 2: Use a global proxy tool

Let a proxy tool take over all network traffic so twitter-cli's requests also go through the proxy:

```bash
# macOS — enable "Enhanced Mode" in ClashX / Surge
# Linux — proxychains or tun2socks
proxychains twitter search "test" -n 1
```

### Option 3: Skip twitter-cli and use Exa search instead

When twitter-cli is unavailable, you can search Twitter content directly with Exa:

```bash
mcporter call exa.web_search_exa query="site:x.com search terms" numResults=5
```

### Option 4: Check authentication

```bash
twitter check
```

> If it returns "Missing credentials", you need to set
> `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the environment of the process running that command.
>
> **Fallback:** If you have already installed bird CLI (`npm install -g @steipete/bird`), it works fine too. WebLens automatically detects installed tools.
