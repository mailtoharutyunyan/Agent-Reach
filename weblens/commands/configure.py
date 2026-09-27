"""``weblens configure`` — set config values, import cookies."""

import sys

_MAX_CONFIGURE_VALUE_CHARS = 1024 * 1024
_SENSITIVE_CONFIG_KEYS = {
    "proxy",
    "github-token",
    "groq-key",
    "openai-key",
    "twitter-cookies",
    "xhs-cookies",
}


def _read_configure_value(args) -> str:
    """Read one configure value without echoing secrets by default."""
    values = getattr(args, "value", None) or []
    if getattr(args, "read_stdin", False):
        try:
            value = sys.stdin.read(_MAX_CONFIGURE_VALUE_CHARS + 1)
        except OSError:
            print("Could not read configure value from stdin", file=sys.stderr)
            raise SystemExit(1) from None
        if len(value) > _MAX_CONFIGURE_VALUE_CHARS:
            print("Configure value exceeds the 1 MiB safety limit", file=sys.stderr)
            raise SystemExit(1)
        return value.rstrip("\r\n")

    if values:
        if getattr(args, "key", None) in _SENSITIVE_CONFIG_KEYS:
            print(
                "Warning: positional secrets are deprecated because shell history "
                "and process listings may expose them; omit the value for a hidden "
                "prompt or use --stdin.",
                file=sys.stderr,
            )
        return " ".join(values)

    try:
        interactive = bool(sys.stdin.isatty())
    except (AttributeError, OSError):
        interactive = False
    if not interactive:
        return ""

    import getpass

    try:
        return getpass.getpass(f"Value for {args.key}: ")
    except (EOFError, KeyboardInterrupt):
        print("Configure input cancelled", file=sys.stderr)
        raise SystemExit(1) from None


def _cmd_configure(args):
    """Set a config value and test it, or auto-extract from browser."""
    import shutil
    from typing import cast

    from weblens.config import Config

    config = Config()

    # ── Auto-extract from browser ──
    if args.from_browser:
        from weblens.cookie_extract import configure_from_browser

        browser = args.from_browser
        platform = "xhs" if args.platform == "xiaohongshu" else args.platform
        print(f"Extracting {args.platform} cookies from {browser}...")
        print()

        try:
            results = configure_from_browser(
                browser,
                config,
                platform=platform,
                profile=args.profile,
            )
        except ValueError as exc:
            from weblens.utils.text import scrub_url_credentials

            print(
                f"weblens configure: error: "
                f"{scrub_url_credentials(exc)}",
                file=sys.stderr,
            )
            raise SystemExit(2) from None

        found_any = False
        for result in results:
            if hasattr(result, "platform"):
                result_platform = result.platform
                success = result.success
                message = result.message
                targets = getattr(result, "targets", ())
            else:
                legacy_result = cast(tuple[str, bool, str], result)
                result_platform, success, message = legacy_result
                targets = ()
            if success:
                print(f"  ✅ {result_platform}: {message}")
                if targets:
                    print(f"     Writing: {', '.join(targets)}")
                found_any = True
            else:
                print(f"  -- {result_platform}: {message}")

        print()
        if found_any:
            print("✅ Cookies configured! Run `weblens doctor` to see updated status.")
        else:
            print(f"No cookies found. Make sure you're logged into the platforms in {browser}.")
            raise SystemExit(1)
        return

    # ── Manual configure ──
    if not args.key:
        print("Usage: weblens configure <key> [--stdin]")
        print("   Omit the value to enter it through a hidden prompt.")
        print(
            "   or: weblens configure --from-browser chrome "
            "--platform xueqiu"
        )
        return

    value = _read_configure_value(args)
    if not value:
        print(f"Missing value for {args.key}")
        raise SystemExit(1)

    if args.key == "proxy":
        # Generic network proxy for restricted environments. `weblens read` /
        # `weblens search` use it for their own HTTP requests and pass it to the
        # tools they run as HTTP(S)_PROXY — unless HTTP(S)_PROXY / ALL_PROXY is
        # already set in the environment (env wins). The legacy bilibili_proxy
        # key is kept in sync for older configs.
        config.set("proxy", value)
        config.set("bilibili_proxy", value)
        print("✅ Proxy saved (used by `weblens read`/`weblens search` and the tools they run; "
              "HTTP(S)_PROXY environment variables take precedence)")
        print("  Note: Bilibili uses bili-cli; no proxy is needed on networks in China.")

    elif args.key == "twitter-cookies":
        # Accept two formats:
        # 1. auth_token ct0 (two separate values)
        # 2. Full cookie header string: "auth_token=xxx; ct0=yyy; ..."
        auth_token, ct0 = _parse_twitter_cookie_input(value)

        if auth_token and ct0:
            config.set("twitter_auth_token", auth_token)
            config.set("twitter_ct0", ct0)

            print("✅ Twitter cookies saved to ~/.weblens/config.yaml")
            if getattr(args, "sync_legacy_twitter", False):
                from weblens.cookie_extract import (
                    _sync_bird_env,
                    _sync_xfetch_session,
                )

                legacy_results = (
                    (
                        "~/.config/xfetch/session.json",
                        _sync_xfetch_session(auth_token, ct0),
                    ),
                    (
                        "~/.config/bird/credentials.env",
                        _sync_bird_env(auth_token, ct0),
                    ),
                )
                for path, success in legacy_results:
                    outcome = "written" if success else "failed"
                    print(f"  {outcome}: {path}")
                if all(success for _, success in legacy_results):
                    print("  Legacy copies written successfully.")

            print(
                "  Credentials not verified live: `twitter status` will not be run, because upstream "
                "automatically reads browser cookies when verification fails."
            )
            if not shutil.which("twitter"):
                print(
                    "  [!] twitter-cli is not installed. Run: pipx install twitter-cli"
                )
            else:
                print(
                    "  Note: the standalone `twitter` command does not read the WebLens config; "
                    "set TWITTER_AUTH_TOKEN/TWITTER_CT0 explicitly when using it directly."
                )
        else:
            print("[X] Could not find auth_token and ct0 in your input.")
            print("   Run `weblens configure twitter-cookies` and paste either:")
            print("   1. AUTH_TOKEN and CT0 separated by whitespace")
            print("   2. A Cookie-Editor Header String")
            print("   For automation, pass the same value through --stdin.")
            raise SystemExit(1)

    elif args.key == "youtube-cookies":
        from weblens.unified.youtube import COOKIES_CONFIG_KEY, parse_cookie_source

        try:
            source = parse_cookie_source(value)
        except ValueError as exc:
            print(f"[X] {exc}", file=sys.stderr)
            raise SystemExit(2) from None
        config.set(COOKIES_CONFIG_KEY, source)
        print(f"✅ YouTube cookie source configured: {source}")
        print("   `weblens read`/`weblens search --source youtube` now pass "
              f"--cookies-from-browser {source} to yt-dlp.")

    elif args.key == "xhs-cookies":
        if not _configure_xhs_cookies(value):
            raise SystemExit(1)

    elif args.key == "github-token":
        config.set("github_token", value)
        print("✅ GitHub token configured!")

    elif args.key == "groq-key":
        config.set("groq_api_key", value)
        print("✅ Groq key configured!")

    elif args.key == "openai-key":
        config.set("openai_api_key", value)
        print("✅ OpenAI key configured!")


def _parse_twitter_cookie_input(value: str):
    """Parse Twitter cookie input from either separate values or a cookie header."""
    auth_token = None
    ct0 = None

    if "auth_token=" in value and "ct0=" in value:
        # Full cookie string — parse it.
        for part in value.replace(";", " ").split():
            if part.startswith("auth_token="):
                auth_token = part.split("=", 1)[1]
            elif part.startswith("ct0="):
                ct0 = part.split("=", 1)[1]
    elif len(value.split()) == 2 and "=" not in value:
        # Two separate values: AUTH_TOKEN CT0.
        parts = value.split()
        auth_token = parts[0]
        ct0 = parts[1]

    return auth_token, ct0


def _configure_xhs_cookies(value) -> bool:
    """Import cookies into xiaohongshu-mcp Docker container.

    Accepts two formats:
    1. Cookie-Editor JSON export (array of cookie objects)
    2. Header String: "name1=value1; name2=value2; ..."

    The xiaohongshu-mcp container stores cookies at $COOKIES_PATH
    (default: /app/data/cookies.json or cookies.json in workdir).
    Format: JSON array of {name, value, domain, path, expires, httpOnly, secure, sameSite}.
    """
    import json
    import os
    import shutil
    import subprocess

    value = value.strip()
    if not value:
        print("[X] Missing cookie value.")
        print("   Run `weblens configure xhs-cookies` and paste the Cookie-Editor export.")
        print("   For automation, pass the same value through --stdin.")
        return False

    # Detect format and parse
    cookies_json = None

    # Try JSON format first (Cookie-Editor JSON export)
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list) and parsed:
                from weblens.utils.url import domain_matches

                valid_cookies = []
                ignored_domains = 0
                ignored_invalid = 0
                for cookie in parsed:
                    if (
                        not isinstance(cookie, dict)
                        or not isinstance(cookie.get("name"), str)
                        or not cookie["name"]
                        or not isinstance(cookie.get("value"), str)
                    ):
                        ignored_invalid += 1
                        continue
                    if not domain_matches(
                        cookie.get("domain", ""),
                        "xiaohongshu.com",
                    ):
                        ignored_domains += 1
                        continue
                    valid_cookies.append(cookie)

                if ignored_domains:
                    print(
                        f"  [!] Ignored {ignored_domains} cookie(s) not on the "
                        "xiaohongshu.com domain"
                    )
                if ignored_invalid:
                    print(
                        f"  [!] Ignored {ignored_invalid} malformed cookie(s)"
                    )
                if not valid_cookies:
                    print(
                        "[X] Cookie-Editor JSON contains no valid "
                        "xiaohongshu.com domain cookies"
                    )
                    return False
                cookies_json = json.dumps(valid_cookies)
                print(
                    f"  Parsed {len(valid_cookies)} "
                    "xiaohongshu.com cookies from JSON format"
                )
            else:
                print("[X] Empty or invalid JSON array")
                return False
        except json.JSONDecodeError as e:
            print(f"[X] Invalid JSON: {e}")
            return False

    # Header String format: "key1=val1; key2=val2; ..."
    if cookies_json is None and "=" in value:
        cookies = []
        for part in value.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, val = part.split("=", 1)
            name = name.strip()
            val = val.strip()
            if name:
                cookies.append({
                    "name": name,
                    "value": val,
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                    "expires": -1,
                    "size": len(name) + len(val),
                    "httpOnly": False,
                    "secure": False,
                    "session": True,
                    "sameSite": "Lax",
                })
        if cookies:
            cookies_json = json.dumps(cookies)
            print(f"  Parsed {len(cookies)} cookies from Header String format")
        else:
            print("[X] Could not parse any cookies from input")
            return False

    if not cookies_json:
        print("[X] Could not parse cookies. Accepted formats:")
        print('   1. JSON array: \'[{"name":"x","value":"y","domain":".xiaohongshu.com",...}]\'')
        print('   2. Header String: "key1=val1; key2=val2; ..."')
        return False

    # Find the container
    docker = shutil.which("docker")
    if not docker:
        # No Docker - write to a local file for manual import.
        from weblens.utils.paths import (
            PrivatePathError,
            atomic_write_private_text,
            home_dir,
        )

        cookie_path = home_dir() / ".weblens" / "xhs-cookies.json"
        try:
            atomic_write_private_text(cookie_path, cookies_json)
        except (OSError, PrivatePathError) as exc:
            print(f"[X] Could not save cookies safely: {exc}")
            return False
        print(f"  Cookies saved to {cookie_path}")
        print("  Docker not found. Copy manually:")
        print(f"  docker cp {cookie_path} xiaohongshu-mcp:/app/data/cookies.json")
        return True

    # Check if xiaohongshu-mcp container is running
    try:
        result = subprocess.run(
            [docker, "ps", "--filter", "name=xiaohongshu-mcp", "--format", "{{.Names}}"],
            capture_output=True, encoding="utf-8", timeout=5,
        )
        container_name = result.stdout.strip()
        if not container_name:
            print("[X] xiaohongshu-mcp container is not running.")
            print("   Start it first:")
            print("   docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp")
            return False
    except Exception as e:
        print(f"[X] Could not check Docker: {e}")
        return False

    # Find the cookies path inside the container
    try:
        result = subprocess.run(
            [docker, "exec", container_name, "printenv", "COOKIES_PATH"],
            capture_output=True, encoding="utf-8", timeout=5,
        )
        cookie_path_in_container = result.stdout.strip()
        if not cookie_path_in_container:
            cookie_path_in_container = "/app/cookies.json"  # fallback: absolute path in workdir
    except Exception:
        cookie_path_in_container = "/app/cookies.json"

    # Write cookies into the container
    tmp_path = None
    try:
        # Write to temp file then docker cp
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(cookies_json)
            tmp_path = f.name

        result = subprocess.run(
            [docker, "cp", tmp_path, f"{container_name}:{cookie_path_in_container}"],
            capture_output=True, encoding="utf-8", timeout=10,
        )

        if result.returncode != 0:
            print(f"[X] Failed to copy cookies: {result.stderr}")
            return False

        print(f"✅ Cookies written to {container_name}:{cookie_path_in_container}")
        # Restart container so it reloads cookies from disk
        print("  Restarting container to reload cookies...", end=" ", flush=True)
        try:
            restart = subprocess.run(
                [docker, "restart", container_name],
                capture_output=True, encoding="utf-8", timeout=30,
            )
            if restart.returncode != 0:
                detail = (
                    (restart.stderr or "").strip()[:200]
                    or f"exit {restart.returncode}"
                )
                print(f"\n  [!] Could not restart container: {detail}")
                print(f"  Restart manually: docker restart {container_name}")
                return False
            print("done")
        except Exception as e:
            print(f"\n  [!] Could not restart container: {e}")
            print(f"  Restart manually: docker restart {container_name}")
            return False
    except Exception as e:
        print(f"[X] Failed to write cookies: {e}")
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"  [!] Could not remove temporary cookie file: {e}")

    # Verify login status via mcporter
    mcporter = shutil.which("mcporter")
    if mcporter:
        print("  Verifying login status...", end=" ")
        try:
            result = subprocess.run(
                [mcporter, "call", "xiaohongshu.check_login_status()"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15,
            )
            # xiaohongshu-mcp reports success in Chinese ("logged in", written as escapes)
            if "\u5df2\u767b\u5f55" in result.stdout or "logged" in result.stdout.lower():
                print("✅ Login verified!")
            else:
                print("[!] Login check returned unexpected result:")
                print(f"  {result.stdout.strip()[:200]}")
                print("  Cookies were written but login might not be valid. Try fresh cookies.")
        except Exception as e:
            print(f"[!] Could not verify: {e}")
    else:
        print("  (mcporter not found, skipping verification)")
    return True
