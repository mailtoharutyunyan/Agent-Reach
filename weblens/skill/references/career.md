# Jobs & Recruiting

LinkedIn, BOSS Zhipin.

## LinkedIn

```bash
# Get a person's profile
mcporter call linkedin.get_person_profile linkedin_username="username" sections="experience,education"

# Search for people
mcporter call linkedin.search_people keywords="AI engineer" location="Shanghai"

# Get a company profile
mcporter call linkedin.get_company_profile company_name="openai" sections="posts,jobs"

# Search for jobs
mcporter call linkedin.search_jobs keywords="software engineer" location="Remote" max_pages=2
```

> **Login required**: before first use, run `uvx mcp-server-linkedin@latest --login` to save a valid login session.

### Fallback

If MCP is unavailable, you can use Jina Reader:

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```

## BOSS Zhipin

When the user says "set up BOSS Zhipin for me", follow this section to complete installation, launch the dedicated Chrome, wait for the user to log in
manually, and do the final verification. Don't dump implementation details like port 9222 on the user up front, and don't enter the account,
scan the QR code, or solve the slider captcha on the user's behalf.

> **Key distinction: login gate ≠ anti-bot security check.** After landing on zhipin.com, the browser may stop on one of three pages:
> the logged-in `web/geek/job`, the logged-out `web/user/` (QR-code login / phone-number login), or
> the anti-bot **security check page** (URL contains `security-check` / `zhipin-security` /
> `_security_check`). The security check page has nothing to do with login: **it appears even when logged in** (it shows up almost every time for Chrome with a CDP debugging
> port). Never use the current page URL to judge login state.

> **Dual login-state storage (in existing-browser strict CDP mode, the browser is authoritative).** There are two credential stores;
> **neither may be deleted**, but they authenticate different channels:
>
> | Store | Role |
> |---|---|
> | `~/.boss-agent/auth/session.enc` | ① Hard gate: `_get_browser()` unconditionally calls `get_token()`, and if it can't read it, raises `AuthRequired` right away, so CDP search fails before even connecting to the browser; ② **not** the auth credential for search: when CDP reuses the real Chrome's `contexts[0]`, its cookies are only injected in the "no context" branch, so they never actually take effect; ③ the httpx channel (low-risk ops: `status`/`detail`/`cities`/`job_card_httpx`) really does use its cookies + stoken, and `force_refresh()` on code 37 also writes back to it |
> | Browser cookies in the dedicated Chrome profile | The credentials actually carried by high-risk ops such as search/greet in CDP mode |
>
> **`boss status` / `status --live` only validate session.enc** - even if it reports
> `logged_in: true`, that does not mean the CDP browser is logged in. Therefore:
> 1. After launching the dedicated Chrome, the first step must be to **pause and have the user visually confirm** the window is logged in
>    (avatar in the top-right corner); only after confirmation may search run;
> 2. doctor's boss row directly probes whether the browser has a wt2 cookie; treat that as authoritative;
> 3. **`AUTH_EXPIRED` is ground truth**: if search reports it, go straight to the login runbook
>    (user logs in in the dedicated window → `login --cdp`); do not interpret it as a "security check";
>    the `_security_check` page is only handled as a slider challenge when `AUTH_EXPIRED` is absent.
> 4. Don't delete session.enc to "clean up old credentials"; to refresh it, run `login --cdp`.

> **Dependency status**: the required public strict-CDP API comes from the follow-up boss-agent-cli split PRs #403–#407
> (#402/#382 were split up per the maintainer's feedback), all of which have been merged into upstream master. The WebLens installer pins
> the fixed upstream commit
> `4c991b77086a203173bf08a4cb64a23af6514fe6` rather than a moving branch; once upstream publishes a release,
> the installer should switch back to a version constraint.

Health check (no side effects, no search):

```bash
weblens doctor          # boss row: off = not installed or CDP unreachable; warn = pipeline ready,
                            # message notes whether the browser has a wt2 login cookie (the browser is authoritative)
```

Search + JD use the public API (`browser_source` / `job_card_browser` / `JobItem.lid`).
Because pipx/uv tool are isolated environments, plain `python` can't necessarily import the installed tool;
use `uv run --with` to ensure the script and the pinned dependencies are in the same interpreter environment:

```bash
uv run --isolated --no-project \
  --with 'git+https://github.com/can4hou6joeng4/boss-agent-cli.git@4c991b77086a203173bf08a4cb64a23af6514fe6' \
  python - <<'PY'
from pathlib import Path

from boss_agent_cli.api.client import AccountRiskError, BossClient, EnvironmentRiskError
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.platforms.zhipin import BossPlatform

auth = AuthManager(Path.home() / ".boss-agent")

# Strict CDP mode: reuse the logged-in browser, raise immediately on CDP failure, never headless
with BossClient(
    auth,
    cdp_url="http://localhost:9222",
    browser_source="existing-browser",
) as boss:
    # city is optional; BOSS Zhipin expects the city's Chinese name
    raw = boss.search_jobs("LLM", page=1)
    if raw.get("code") != 0:
        code, message = BossPlatform(boss).parse_error(raw)
        raise RuntimeError(f"{code}: {message}")
    items = raw.get("zpData", {}).get("jobList", [])
    for item in items:
        card = boss.job_card_browser(item["securityId"], item["lid"])
        post_desc = card.get("zpData", {}).get("jobCard", {}).get(
            "postDescription", ""
        )
        print(item.get("jobName"), post_desc)

# AccountRiskError / EnvironmentRiskError → stop immediately, no automatic retry;
# code 37 that explicitly means token/stoken expired is refreshed and retried at most once by BossClient.
PY
```

### Environment health check and recovery (must check before scraping)

If `weblens doctor` reports boss as `off` or `warn` before searching, troubleshoot with the runbook below; don't read the source code and guess:

1. **Is the CDP port reachable**:
   ```bash
   curl -s http://localhost:9222/json/version   # has a Browser field = port reachable
   ```

2. **Debug Chrome not open / already closed**: launch the dedicated Chrome for your OS (separate login state, doesn't pollute your everyday browser):
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

   Bind only to the loopback address. Any process that can reach 9222 can fully control this Chrome; never listen on a public interface.
   Reuse this dedicated profile long-term to keep a stable login state; don't delete or recreate it on each run,
   and don't switch to your everyday main Chrome by default. Close this dedicated window when not in use.

   **First step after launch: pause and have the user visually confirm the window is logged in (avatar in the top-right corner).**
   Don't substitute `boss status` for this step - it only validates the local session.enc, not the browser.

3. **User logs in manually (when the browser is not logged in)**: the determination is based first on doctor's browser cookie probe
   (no wt2 = browser not logged in), and only second on the user's visual confirmation; `boss status` is for reference only.
   Have the user log in or scan the QR code in this dedicated window. Once the user confirms it's done, save the CDP login state:
   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   ```

   If the window is stuck on a security check page (`security-check` / `zhipin-security`), that's an anti-bot challenge,
   not a login page: wait for it to pass automatically or have the user solve the slider manually; don't treat it as "not logged in" and
   re-scan the QR code to log in.

4. **Is the login state valid** (browser cookie probe + whether stoken has expired):
   ```bash
   weblens doctor     # check the browser wt2 cookie probe result in the boss row message
   boss status            # reflects only the local session.enc; for reference only
   ```

5. **Error code handling** (when searching / fetching JDs):
   - `AUTH_EXPIRED` (user not logged in) → **ground truth**: the CDP browser is not logged in (regardless of what
     `boss status` says); go straight to the step 3 login flow + `login --cdp`; do not interpret it as
     a "security check";
   - code 36 (ACCOUNT_RISK) → stop immediately and handle it manually on the BOSS page; never retry automatically;
   - code 9 (RATE_LIMITED) → retry after a cooldown;
   - code 37 + an "environment is abnormal" message → `ENVIRONMENT_RISK`: stop immediately; don't refresh the token, don't log in again, don't retry automatically;
   - Only a code 37 whose message explicitly says token/stoken expired is `TOKEN_REFRESH_FAILED`; the client refreshes and retries automatically at most once, and if it still fails, log in again.

When the user asks to start searching, the Agent must specify strict CDP mode (global options go before the subcommand):

```bash
# optional: --city <city name in Chinese>
boss --browser-source existing-browser --cdp-url http://localhost:9222 search "LLM" --page 1
```

Don't page through results continuously without prompting. boss-agent-cli PR #383 adds a persistent
5–10 second listing budget for regular searches across CLI processes; until that PR is merged and released, the Agent should still proactively serialize calls and reduce their frequency.

> **Waiting is expected, not a hang**: when consecutive searches hit throttling, boss-agent-cli silently waits 5–10 seconds
> (under a TTY it shows a "throttle wait Ns…" hint; WebLens calls it with `--json`, so the hint isn't visible).
> During the wait window, don't retry, don't launch a new browser, and don't switch profiles.
