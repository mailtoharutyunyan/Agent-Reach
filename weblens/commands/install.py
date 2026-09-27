"""``weblens install`` — deterministic installer and per-channel dependency setup."""

import os
import sys

from weblens.commands import skill as _skill

# Exact pins keep installs reproducible and prevent a compromised or broken
# "latest" release from being pulled in silently. Bump deliberately.
_UNDICI_VERSION = "8.11.2"
_UNDICI_NPM_SPEC = f"undici@{_UNDICI_VERSION}"
_MCPORTER_VERSION = "0.14.1"
_MCPORTER_NPM_SPEC = f"mcporter@{_MCPORTER_VERSION}"
_OPENCLI_VERSION = "1.8.8"
_TWITTER_CLI_VERSION = "0.8.5"
_TWITTER_CLI_SPEC = f"twitter-cli=={_TWITTER_CLI_VERSION}"
_BILIBILI_CLI_VERSION = "0.6.2"
_BILIBILI_CLI_SPEC = f"bilibili-cli=={_BILIBILI_CLI_VERSION}"

_PROXY_ENV_VARS = (
    "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
    "ALL_PROXY", "all_proxy",
)


def _opencli_npm_spec():
    from weblens.backends import OPENCLI_PACKAGE

    return f"{OPENCLI_PACKAGE}@{_OPENCLI_VERSION}"


def _proxy_configured():
    """True when a proxy is set in the environment or WebLens config.

    undici is only useful for Node.js proxy support, so it is skipped otherwise.
    """
    if any(os.environ.get(name) for name in _PROXY_ENV_VARS):
        return True
    try:
        from weblens.config import Config

        config = Config(read_only=True)
        return bool(config.get("proxy") or config.get("bilibili_proxy"))
    except Exception:
        return False

# Pinned to the 0.4.2 state — PyPI still only has 0.4.1 (upstream issue #10).
_RDT_GIT_SOURCE = "git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66"
# boss-agent-cli PRs #403-#407 are all merged into upstream master. Pin to a fixed
# upstream commit that contains strict CDP, JobItem.lid, job_card_browser(), and the
# throttle progress feedback. Never point the installer at a moving branch. Once an
# upstream release containing #403/#404/#406 ships, switch to a version specifier.
_BOSS_AGENT_CLI_PR_COMMIT = "4c991b77086a203173bf08a4cb64a23af6514fe6"
_BOSS_AGENT_CLI_SOURCE = (
    "git+https://github.com/can4hou6joeng4/boss-agent-cli.git@"
    + _BOSS_AGENT_CLI_PR_COMMIT
)


def _cmd_install(args):
    """One-shot deterministic installer."""
    import os

    from weblens.config import Config
    from weblens.doctor import check_all, format_report, print_report

    safe_mode = getattr(args, "safe", False) or not getattr(args, "system", False)
    dry_run = args.dry_run

    # Validate channel names before constructing config or changing the system.
    CHANNEL_INSTALLERS = {
        "twitter":     _install_twitter_deps,
        "xiaoyuzhou":  _install_xiaoyuzhou_deps,
        "xiaohongshu": _install_xhs_deps,
        "reddit":      _install_reddit_deps,
        "facebook":    _install_opencli_deps,
        "instagram":   _install_opencli_deps,
        "bilibili":    _install_bili_deps,
        "boss":        _install_boss_deps,
        "opencli":     _install_opencli_deps,  # cross-channel backend, desktop only
        # xueqiu: cookie-only, no install step
        # linkedin: manual setup, no auto-install
    }
    supported_channels = set(CHANNEL_INSTALLERS) | {"xueqiu", "linkedin"}
    raw_channels = [
        channel.strip().lower()
        for channel in args.channels.split(",")
        if channel.strip()
    ]
    unknown_channels = set(raw_channels) - supported_channels - {"all"}
    if unknown_channels:
        supported = ", ".join(sorted(supported_channels | {"all"}))
        unknown = ", ".join(sorted(unknown_channels))
        print(
            f"weblens install: error: unknown channel(s): {unknown}. "
            f"Supported: {supported}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if "all" in raw_channels:
        requested_channels = supported_channels
    else:
        requested_channels = set(raw_channels)

    config = Config(read_only=dry_run or safe_mode)
    print()
    print("WebLens Installer")
    print("=" * 40)

    if dry_run:
        print("DRY RUN — showing what would be done (no changes)")
        print()
    if safe_mode:
        print("SAFE MODE — skipping automatic system changes")
        print()

    # Only a real installation may create persistent directories.
    if not dry_run and not safe_mode:
        tools_dir = os.path.expanduser("~/.weblens/tools")
        os.makedirs(tools_dir, exist_ok=True)

    DESKTOP_ONLY_CHANNELS = {"opencli", "facebook", "instagram", "boss"}
    COOKIE_CHANNELS = {"twitter", "xueqiu", "bilibili", "xiaohongshu"}

    # Auto-detect environment
    env = args.env
    if env == "auto":
        env = _detect_environment()

    if env == "server":
        print("Environment: Server/VPS (auto-detected)")
    else:
        print("Environment: Local computer (auto-detected)")

    server_skipped_desktop_channels = set()
    if env == "server" and requested_channels:
        # Browser-session channels require a real desktop Chrome.
        server_skipped_desktop_channels = requested_channels & DESKTOP_ONLY_CHANNELS
        requested_channels -= server_skipped_desktop_channels

    # Apply explicit flags
    if args.proxy:
        if dry_run or safe_mode:
            mode = "dry-run" if dry_run else "safe"
            print(f"[{mode}] Would save network proxy")
        else:
            config.set("proxy", args.proxy)
            config.set("bilibili_proxy", args.proxy)  # legacy key
            print("✅ Proxy saved (used when the Agent accesses restricted networks)")

    # ── Install core system dependencies (lightweight, always) ──
    print()
    core_install_ok = True
    if dry_run:
        _install_system_deps_dryrun()
    elif safe_mode:
        _install_system_deps_safe()
    else:
        core_install_ok = _install_system_deps() is not False

    # ── mcporter (for Exa search) ──
    print()
    if dry_run:
        print("[dry-run] Would install mcporter and configure Exa search")
    elif safe_mode:
        _install_mcporter_safe()
    else:
        core_install_ok = (_install_mcporter() is not False) and core_install_ok

    if server_skipped_desktop_channels:
        print()
        print("  -- The following channels need a desktop environment + Chrome; skipped on server: "
              f"{', '.join(sorted(server_skipped_desktop_channels))}")

    # ── Install optional channels (only if --channels specified) ──
    if requested_channels and not dry_run and not safe_mode:
        print()
        print("Installing optional channels...")
        ran_installers = set()
        optional_install_ok = True
        for ch_name in sorted(requested_channels):
            installer = CHANNEL_INSTALLERS.get(ch_name)
            if installer and installer not in ran_installers:
                optional_install_ok = (
                    installer() is not False
                ) and optional_install_ok
                ran_installers.add(installer)
    else:
        optional_install_ok = True

    if requested_channels and dry_run:
        print()
        print(f"[dry-run] Would install optional channels: {', '.join(sorted(requested_channels))}")

    # ── Cookie setup (explicit only — install never reads browser credentials) ──
    needs_cookies = bool(requested_channels & COOKIE_CHANNELS)
    if env == "local" and needs_cookies and not dry_run:
        print()
        print("Cookie login is never read automatically.")
        print("Run only the platform command you intend to authorize:")
        for channel in sorted(requested_channels & COOKIE_CHANNELS):
            if channel == "twitter":
                print("  weblens configure twitter-cookies")
            elif channel == "xiaohongshu":
                print("  weblens configure xhs-cookies")
            else:
                print(
                    "  weblens configure --from-browser chrome "
                    f"--platform {channel}"
                )
    elif env == "local" and needs_cookies and dry_run:
        print()
        print("[dry-run] Cookie import remains explicit; install will not read a browser")

    # Environment-specific advice
    if env == "server":
        print()
        print("Tip: Some platforms apply risk controls to server IPs.")
        print("   Reddit requires a logged-in session (rdt-cli + Cookie, see doctor hints); networks in mainland China also need a proxy.")
        print("   Save a proxy for the Agent to use: weblens configure proxy (hidden input)")
        print("   Cheap option: https://www.webshare.io ($1/month)")

    # Test channels
    if not dry_run:
        print()
        print("Testing channels...")
        results = check_all(config)
        ok = sum(1 for r in results.values() if r["status"] == "ok")
        total = len(results)

        # Final status
        print()
        print_report(format_report(results))
        print()

        if safe_mode:
            print(
                "Safe mode check complete. No changes were made. "
                f"{ok}/{total} channels active."
            )
        else:
            # ── Install agent skill ──
            skill_install_ok = _skill._install_skill() is not False
            install_ok = (
                core_install_ok and optional_install_ok and skill_install_ok
            )

            if install_ok:
                print(f"Installation complete. {ok}/{total} channels active.")
            else:
                print(
                    "Installation incomplete: one or more requested "
                    f"steps failed. {ok}/{total} channels active."
                )

            if not requested_channels:
                # First install — hint about optional channels
                print()
                print("More channels available! Use --channels to install:")
                print("   weblens install --system --channels=twitter,xiaohongshu,reddit,facebook,instagram,...")
                print("   weblens install --system --channels=all  (install everything)")

            # Star reminder
            print()
            print("If WebLens helped you, give it a Star so more people can discover it:")
            print("   https://github.com/YOUR_GITHUB_USER/weblens")
            print("   It only takes a second and means a lot to an indie developer. Thank you!")
            if not install_ok:
                raise SystemExit(1)
    else:
        print()
        print("Dry run complete. No changes were made.")


def _install_system_deps():
    """Install system dependencies through an existing OS package manager."""
    import platform
    import shutil
    import subprocess

    print("Checking system dependencies...")

    gh_installed = bool(shutil.which("gh"))
    node_installed = bool(shutil.which("node") and shutil.which("npm"))

    if gh_installed:
        print("  ✅ gh CLI already installed")
    if node_installed:
        print("  ✅ Node.js already installed")

    missing_labels = []
    if not gh_installed:
        missing_labels.append("gh CLI")
    if not node_installed:
        missing_labels.append("Node.js")
    system_install_ok = not missing_labels

    os_type = platform.system().lower()
    if missing_labels and os_type == "linux":
        apt_get = shutil.which("apt-get")
        if not apt_get:
            system_install_ok = False
            print(
                "  [!]  Missing system dependencies: "
                f"{', '.join(missing_labels)}. apt-get is not available; "
                "install them manually."
            )
        else:
            packages = []
            if not gh_installed:
                packages.append("gh")
            if not node_installed:
                packages.extend(("nodejs", "npm"))
            print(f"  Installing {', '.join(missing_labels)} with apt-get...")
            try:
                update_result = subprocess.run(
                    [apt_get, "update", "-qq"],
                    capture_output=True,
                    timeout=120,
                )
                if update_result.returncode != 0:
                    system_install_ok = False
                    print(
                        "  [!]  apt-get update failed; no packages were installed."
                    )
                else:
                    install_result = subprocess.run(
                        [apt_get, "install", "-y", "-qq", *packages],
                        capture_output=True,
                        timeout=180,
                    )
                    if install_result.returncode == 0:
                        system_install_ok = True
                        print(
                            "  ✅ Installed with apt-get: "
                            f"{', '.join(missing_labels)}"
                        )
                    else:
                        system_install_ok = False
                        print(
                            "  [!]  apt-get install failed for: "
                            f"{', '.join(missing_labels)}"
                        )
            except (OSError, subprocess.TimeoutExpired):
                system_install_ok = False
                print(
                    "  [!]  apt-get failed for: "
                    f"{', '.join(missing_labels)}"
                )
    elif missing_labels and os_type == "darwin":
        brew = shutil.which("brew")
        if not brew:
            system_install_ok = False
            print(
                "  [!]  Missing system dependencies: "
                f"{', '.join(missing_labels)}. Homebrew is not available; "
                "install them manually."
            )
        else:
            system_install_ok = True
            brew_packages = []
            if not gh_installed:
                brew_packages.append(("gh", "gh CLI"))
            if not node_installed:
                brew_packages.append(("node", "Node.js"))
            for package, label in brew_packages:
                print(f"  Installing {label} with Homebrew...")
                try:
                    brew_result = subprocess.run(
                        [brew, "install", package],
                        capture_output=True,
                        timeout=180,
                    )
                    if brew_result.returncode == 0:
                        print(f"  ✅ {label} installed")
                    else:
                        system_install_ok = False
                        print(f"  [!]  {label} install failed")
                except (OSError, subprocess.TimeoutExpired):
                    system_install_ok = False
                    print(f"  [!]  {label} install failed")
    elif missing_labels:
        system_install_ok = False
        print(
            "  [!]  Missing system dependencies: "
            f"{', '.join(missing_labels)}. Install them manually."
        )

    # ── undici (proxy support for Node.js fetch) — only when a proxy is set ──
    npm_cmd = shutil.which("npm")
    if npm_cmd and not _proxy_configured():
        print("  -- No proxy configured; skipping optional undici install")
    elif npm_cmd:
        try:
            npm_root_result = subprocess.run(
                [npm_cmd, "root", "-g"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            npm_root_result = None

        if npm_root_result is None or npm_root_result.returncode != 0:
            print(
                "  -- Could not inspect global npm packages; "
                "skipping optional undici install"
            )
        else:
            npm_root = npm_root_result.stdout.strip()
            undici_path = (
                os.path.join(npm_root, "undici", "index.js")
                if npm_root
                else ""
            )
            if os.path.exists(undici_path):
                print("  ✅ undici already installed (Node.js proxy support)")
            else:
                try:
                    result = subprocess.run(
                        [npm_cmd, "install", "-g", _UNDICI_NPM_SPEC],
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=60,
                    )
                    if result.returncode == 0:
                        print("  ✅ undici installed (Node.js proxy support)")
                    else:
                        print(
                            "  -- undici install failed "
                            "(optional — may not work behind proxies)"
                        )
                except (OSError, subprocess.TimeoutExpired):
                    print(
                        "  -- undici install failed "
                        "(optional — may not work behind proxies)"
                    )

    # ── yt-dlp JS runtime config (YouTube requires external JS runtime) ──
    if shutil.which("deno"):
        print("  ✅ yt-dlp can use the installed Deno JS runtime")
    elif shutil.which("node"):
        from weblens.channels.youtube import (
            _JS_RUNTIMES_SUPPORTED_FROM,
            _parse_ytdlp_version,
        )
        from weblens.utils.paths import (
            PrivatePathError,
            atomic_write_private_text,
            get_ytdlp_config_path,
            read_small_text_no_follow,
        )

        ytdlp_cmd = shutil.which("yt-dlp")
        installed_version = None
        if ytdlp_cmd:
            try:
                version_result = subprocess.run(
                    [ytdlp_cmd, "--version"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if version_result.returncode == 0:
                    installed_version = _parse_ytdlp_version(
                        version_result.stdout.strip()
                    )
            except (OSError, subprocess.TimeoutExpired):
                installed_version = None

        if (
            installed_version is None
            or installed_version < _JS_RUNTIMES_SUPPORTED_FROM
        ):
            print(
                "  -- yt-dlp JS runtime config not written: yt-dlp is missing, too old, or "
                "its version could not be determined. Upgrade first: python -m pip install -U "
                '"yt-dlp[default]"'
            )
        else:
            ytdlp_config = get_ytdlp_config_path()
            try:
                existing_config = read_small_text_no_follow(
                    ytdlp_config,
                    max_bytes=1024 * 1024,
                )
                if (
                    existing_config is not None
                    and "--js-runtimes" in existing_config
                ):
                    print("  ✅ yt-dlp JS runtime already configured")
                else:
                    existing_config = existing_config or ""
                    separator = (
                        ""
                        if not existing_config
                        or existing_config.endswith(("\n", "\r"))
                        else "\n"
                    )
                    atomic_write_private_text(
                        ytdlp_config,
                        existing_config
                        + separator
                        + "--js-runtimes node\n",
                    )
                    print(
                        "  ✅ yt-dlp configured to use Node.js as JS runtime "
                        "(YouTube)"
                    )
            except (OSError, UnicodeError, ValueError, PrivatePathError):
                print(
                    "  -- Could not configure yt-dlp JS runtime "
                    "(YouTube may not work)"
                )

    # NOTE: twitter-cli, xiaoyuzhou, xhs-cli etc. are optional.
    # They are installed via --channels flag, not here.
    # See CHANNEL_INSTALLERS in _cmd_install().
    return system_install_ok


def _install_xiaoyuzhou_deps():
    """Install Xiaoyuzhou podcast transcription script."""
    import shutil

    from weblens.config import Config
    from weblens.utils.paths import PrivatePathError, atomic_write_private_text

    config = Config()
    print("Setting up Xiaoyuzhou podcast transcription...")

    tools_dir = os.path.expanduser("~/.weblens/tools/xiaoyuzhou")
    script_dst = os.path.join(tools_dir, "transcribe.sh")

    script_src = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "scripts",
        "transcribe_xiaoyuzhou.sh",
    )
    script_ok = False
    if os.path.isfile(script_src):
        existed = os.path.isfile(script_dst)
        try:
            with open(script_src, encoding="utf-8") as source:
                script_text = source.read()
            atomic_write_private_text(script_dst, script_text)
            os.chmod(script_dst, 0o700)
            action = "updated" if existed else "installed"
            print(f"  ✅ Xiaoyuzhou transcription script {action}")
            script_ok = True
        except (OSError, UnicodeError, PrivatePathError) as exc:
            print(f"  [!]  Failed to install script: {exc}")
    else:
        print("  [!]  Script source not found in package")

    # Check ffmpeg
    ffmpeg_ok = bool(shutil.which("ffmpeg"))
    if ffmpeg_ok:
        print("  ✅ ffmpeg available")
    else:
        print("  -- ffmpeg not found. Install: apt install -y ffmpeg (or brew install ffmpeg)")

    # Check GROQ_API_KEY
    has_key = bool(os.environ.get("GROQ_API_KEY")) or bool(config.get("groq_api_key"))
    if has_key:
        print("  ✅ Groq API key configured")
    else:
        print("  -- Groq API key not set. Get free key at https://console.groq.com")
        print("     Then run: weblens configure groq-key (hidden input)")
    return script_ok and ffmpeg_ok


def _install_twitter_deps():
    """Install twitter-cli for Twitter search + timeline."""
    import shutil
    import subprocess

    print("Setting up Twitter (twitter-cli)...")
    if shutil.which("twitter"):
        print("  ✅ twitter-cli already installed")
        return True
    for tool, args in [
        ("pipx", ["install", _TWITTER_CLI_SPEC]),
        ("uv", ["tool", "install", _TWITTER_CLI_SPEC]),
    ]:
        tool_cmd = shutil.which(tool)
        if tool_cmd:
            try:
                result = subprocess.run(
                    [tool_cmd, *args], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=120,
                )
                if result.returncode == 0 and shutil.which("twitter"):
                    print("  ✅ twitter-cli installed")
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    print(
        "  [!]  twitter-cli install failed. Run: "
        f"pipx install '{_TWITTER_CLI_SPEC}'"
    )
    return False


def _install_boss_deps():
    """Install the strict-CDP boss-agent-cli build required by the Boss channel.

    Upstream boss-agent-cli PRs #403-#407 are all merged into master; the source is
    pinned to a fixed upstream commit containing those five PRs. Force-installing is
    intentional: PyPI 1.18.0 exposes the ``boss`` executable but lacks the public
    strict-CDP APIs required by this channel.
    """
    import shutil
    import subprocess

    print("Setting up BOSS Zhipin (boss-agent-cli upstream pinned commit)...")
    for tool, args in [
        ("pipx", ["install", "--force", _BOSS_AGENT_CLI_SOURCE]),
        ("uv", ["tool", "install", "--force", _BOSS_AGENT_CLI_SOURCE]),
    ]:
        tool_cmd = shutil.which(tool)
        if not tool_cmd:
            continue
        try:
            result = subprocess.run(
                [tool_cmd, *args],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            if result.returncode == 0 and shutil.which("boss"):
                print("  ✅ boss-agent-cli installed from pinned upstream commit")
                print("  Next step: launch a dedicated Chrome, have the user log in to zhipin.com manually, then run weblens doctor")
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass

    print("  [!]  boss-agent-cli install failed. Install pipx or uv, then retry:")
    print(f"       pipx install --force '{_BOSS_AGENT_CLI_SOURCE}'")
    return False


def _install_xhs_deps():
    """Set up XiaoHongShu — backend depends on environment.

    Desktop: OpenCLI (reuses the browser session, zero config).
    Server: xiaohongshu-mcp guide with an explicit Cookie-Editor export;
    we don't manage long-running services, so guide only.
    xhs-cli is no longer installed by default — upstream unmaintained
    since 2026-03; existing installs keep working as a fallback backend.
    """
    import shutil

    print("Setting up XiaoHongShu...")
    if _detect_environment() == "server":
        print("  xiaohongshu-mcp is recommended for server environments:")
        print("    1. Download the binary: https://github.com/xpzouying/xiaohongshu-mcp/releases")
        print("       (recommended location: ~/.weblens/tools/)")
        print("    2. Start the service (the first run downloads a ~150MB browser; wait for it to finish)")
        print("    3. Explicitly export cookies from xiaohongshu.com with Cookie-Editor")
        print("       weblens configure xhs-cookies (paste into the hidden input prompt)")
        print("    4. Connect: mcporter config add xiaohongshu http://localhost:18060/mcp --scope home")
        print("    5. Verify: weblens doctor")
        return False

    opencli_ok = _install_opencli_deps()
    xhs_ok = bool(shutil.which("xhs"))
    if xhs_ok:
        print("  ✅ Existing xhs-cli detected; it remains available as a fallback backend")
    return opencli_ok or xhs_ok


def _install_opencli_deps():
    """Install OpenCLI — cross-platform backend riding the user's Chrome session.

    Desktop-only. The npm package installs automatically; the Chrome
    extension CANNOT be installed programmatically (Chrome security model),
    so we print a one-click guide instead.
    """
    import shutil
    import subprocess

    from weblens.backends import (
        OPENCLI_EXTENSION_URL,
        opencli_status,
        opencli_summary,
    )

    print("Setting up OpenCLI (browser-session backend, desktop only)...")
    st = opencli_status()
    if st.installed and not st.broken:
        print(f"  ✅ {opencli_summary(st)}")
        if not st.ready:
            print(f"  {st.hint}")
        return True

    npm_cmd = shutil.which("npm")
    if not npm_cmd:
        print("  [!]  OpenCLI requires Node.js ≥ 20. Install Node first:")
        print("       https://nodejs.org  (or brew install node)")
        return False

    try:
        install_result = subprocess.run(
            [npm_cmd, "install", "-g", _opencli_npm_spec()],
            capture_output=True, encoding="utf-8", errors="replace", timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired):
        install_result = None

    st = opencli_status()
    if (
        install_result is not None
        and install_result.returncode == 0
        and st.installed
        and not st.broken
    ):
        print("  ✅ OpenCLI installed")
        print("  Final step (must be done manually due to Chrome security restrictions): install the browser extension")
        print(f"    1. Open {OPENCLI_EXTENSION_URL}")
        print("    2. Click \"Add to Chrome\"")
        print("    3. Run `opencli doctor` to verify the connection")
        return True
    else:
        print(
            "  [!]  OpenCLI install failed. Run: "
            f"npm install -g {_opencli_npm_spec()}"
        )
        return False


def _install_reddit_deps():
    """Set up Reddit — desktop prefers OpenCLI, rdt-cli for servers/legacy.

    No zero-config path exists (anonymous .json blocked, official API
    approval-gated since 2025-11) — every backend needs a logged-in session.
    """
    if _detect_environment() != "server":
        installed = _install_opencli_deps()
        print("  Reddit uses OpenCLI (works once you are logged in to reddit.com in the browser)")
        import shutil
        if shutil.which("rdt"):
            print("  ✅ Existing rdt-cli detected; it remains available as a fallback backend")
        return installed

    return _install_rdt_cli()


def _install_rdt_cli():
    """Install rdt-cli (pinned git source — PyPI lags upstream)."""
    import shutil
    import subprocess

    print("Setting up Reddit (rdt-cli)...")
    if shutil.which("rdt"):
        print("  ✅ rdt-cli already installed")
        return True
    for tool, args in [
        ("pipx", ["install", _RDT_GIT_SOURCE]),
        ("uv", ["tool", "install", "--from", _RDT_GIT_SOURCE, "rdt-cli"]),
    ]:
        tool_cmd = shutil.which(tool)
        if tool_cmd:
            try:
                result = subprocess.run(
                    [tool_cmd, *args], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=120,
                )
                if result.returncode == 0 and shutil.which("rdt"):
                    print("  ✅ rdt-cli installed")
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    print(f"  [!]  rdt-cli install failed. Run: pipx install '{_RDT_GIT_SOURCE}'")
    return False


def _install_bili_deps():
    """Install bili-cli for Bilibili hot/rank/search."""
    import shutil
    import subprocess

    print("Setting up Bilibili (bili-cli)...")
    if shutil.which("bili"):
        print("  ✅ bili-cli already installed")
        return True
    for tool, args in [
        ("pipx", ["install", _BILIBILI_CLI_SPEC]),
        ("uv", ["tool", "install", _BILIBILI_CLI_SPEC]),
    ]:
        tool_cmd = shutil.which(tool)
        if tool_cmd:
            try:
                result = subprocess.run(
                    [tool_cmd, *args], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=120,
                )
                if result.returncode == 0 and shutil.which("bili"):
                    print("  ✅ bili-cli installed")
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    print(
        "  [!]  bili-cli install failed. Run: "
        f"pipx install '{_BILIBILI_CLI_SPEC}'"
    )
    return False


def _install_system_deps_safe():
    """Safe mode: check what's installed, print instructions for what's missing."""
    import shutil

    print("Checking system dependencies (safe mode — no auto-install)...")

    deps = [
        ("gh", ["gh"], "GitHub CLI", "https://cli.github.com — or: apt install gh / brew install gh"),
        ("node", ["node", "npm"], "Node.js", "https://nodejs.org — or: apt install nodejs npm"),
    ]

    missing = []
    for _name, binaries, label, install_hint in deps:
        found = all(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label} already installed")
        else:
            print(f"  -- {label} not found")
            missing.append((label, install_hint))

    if missing:
        print()
        print("  To install missing dependencies manually:")
        for label, hint in missing:
            print(f"    {label}: {hint}")
    else:
        print("  All system dependencies are installed!")


def _install_system_deps_dryrun():
    """Dry-run: just show what would be checked/installed."""
    import shutil

    print("[dry-run] System dependency check:")

    checks = [
        ("gh CLI", ["gh"], "apt-get install gh / brew install gh"),
        (
            "Node.js",
            ["node", "npm"],
            "apt-get install nodejs npm / brew install node",
        ),
    ]

    for label, binaries, method in checks:
        found = all(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label}: already installed, skip")
        else:
            print(f"  {label}: would install via: {method}")


def _install_mcporter():
    """Install mcporter and configure Exa search."""
    import shutil
    import subprocess

    print("Setting up mcporter (search backend)...")

    mcporter_cmd = shutil.which("mcporter")
    if mcporter_cmd:
        print("  ✅ mcporter already installed")
    else:
        npm_cmd = shutil.which("npm")
        if not npm_cmd:
            print("  [!]  mcporter requires Node.js. Install Node.js first:")
            print("     https://nodejs.org/")
            return False
        try:
            install_result = subprocess.run(
                [npm_cmd, "install", "-g", _MCPORTER_NPM_SPEC],
                capture_output=True, encoding="utf-8", errors="replace", timeout=120,
            )
            mcporter_cmd = shutil.which("mcporter")
            if install_result.returncode == 0 and mcporter_cmd:
                print("  ✅ mcporter installed")
            else:
                print(
                    "  [X] mcporter install failed. Retry: "
                    f"npm install -g {_MCPORTER_NPM_SPEC} (check network/timeout)"
                )
                return False
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"  [X] mcporter install failed: {e}")
            return False

    # Configure Exa MCP (free, no key needed)
    try:
        from weblens.channels.mcporter import (
            McporterConfigError,
            configured_server_names,
        )

        # Run from HOME so a project-local ./config/mcporter.json in the current
        # directory is not mistaken for the user's home-scope configuration.
        home_dir = os.path.expanduser("~")
        r = subprocess.run(
            [mcporter_cmd, "config", "list", "--json"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            cwd=home_dir,
        )
        if r.returncode != 0:
            raise McporterConfigError("mcporter config query failed")
        server_names = configured_server_names(r.stdout)
        if "exa" not in server_names:
            add_result = subprocess.run(
                [
                    mcporter_cmd,
                    "config",
                    "add",
                    "exa",
                    "https://mcp.exa.ai/mcp",
                    "--scope",
                    "home",
                ],
                capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                cwd=home_dir,
            )
            if add_result.returncode == 0:
                print("  ✅ Exa search configured (free, no API key needed)")
                return True
            else:
                print(
                    "  [!]  Could not configure Exa. Run manually: "
                    "mcporter config add exa https://mcp.exa.ai/mcp --scope home"
                )
                return False
        else:
            print("  ✅ Exa search already configured")
            return True
    except Exception:
        print("  [!]  Could not configure Exa. Run manually: mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        return False

    # NOTE: xhs-cli is now optional, installed via --channels=xiaohongshu


def _install_mcporter_safe():
    """Safe mode: check mcporter status, print instructions."""
    import shutil

    print("Checking mcporter (safe mode)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
        print("  To configure Exa search: mcporter config add exa https://mcp.exa.ai/mcp --scope home")
    else:
        print("  -- mcporter not installed")
        print(f"  To install: npm install -g {_MCPORTER_NPM_SPEC}")
        print("  Then configure Exa: mcporter config add exa https://mcp.exa.ai/mcp --scope home")


def _detect_environment():
    """Auto-detect if running on local computer or server."""
    import os

    # Check common server indicators
    indicators = 0

    # SSH session
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        indicators += 2

    # Docker / container
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        indicators += 2

    # No display (headless)
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        indicators += 1

    # Cloud VM identifiers
    for cloud_file in ["/sys/hypervisor/uuid", "/sys/class/dmi/id/product_name"]:
        if os.path.exists(cloud_file):
            try:
                with open(cloud_file) as f:
                    content = f.read().lower()
                if any(x in content for x in ["amazon", "google", "microsoft", "digitalocean", "linode", "vultr", "hetzner"]):
                    indicators += 2
            except Exception:
                pass

    # systemd-detect-virt
    try:
        import subprocess
        result = subprocess.run(["systemd-detect-virt"], capture_output=True, encoding="utf-8", errors="replace", timeout=3)
        if result.returncode == 0 and result.stdout.strip() != "none":
            indicators += 1
    except Exception:
        pass

    return "server" if indicators >= 2 else "local"
