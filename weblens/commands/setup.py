"""``weblens setup`` — interactive configuration wizard."""

from weblens.commands.install import _RDT_GIT_SOURCE


def _cmd_setup():
    import getpass

    from weblens.config import Config

    config = Config()
    print()
    print("WebLens Setup")
    print("=" * 40)
    print()

    # Step 1: Exa (via mcporter, no API key required)
    import shutil
    import subprocess

    print("[Recommended] Web search — Exa (via mcporter)")
    print("  Free, no API key required")

    if not shutil.which("mcporter"):
        print("  Current status: -- mcporter not installed")
        print("  Install: npm install -g mcporter")
        print("  Then: mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        print()
    else:
        try:
            from weblens.channels.mcporter import (
                McporterConfigError,
                configured_server_names,
            )

            r = subprocess.run(
                ["mcporter", "config", "list", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if r.returncode != 0:
                raise McporterConfigError("mcporter config query failed")
            if "exa" in configured_server_names(r.stdout):
                print("  Current status: ✅ configured")
            else:
                print("  Current status: -- not configured")
                setup_now = input("  Configure Exa automatically now? [Y/n]: ").strip().lower()
                if setup_now in ("", "y", "yes"):
                    add_r = subprocess.run(
                        [
                            "mcporter",
                            "config",
                            "add",
                            "exa",
                            "https://mcp.exa.ai/mcp",
                            "--scope",
                            "home",
                        ],
                        capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                    )
                    if add_r.returncode == 0:
                        print("  ✅ Exa configured")
                    else:
                        print("  [!] Automatic configuration failed; run manually:")
                        print("     mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        except Exception:
            print("  [!] Could not check the Exa config; run manually:")
            print("     mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        print()

    # Step 2: GitHub token
    print("[Optional] GitHub Token — raises the API rate limit")
    print("  Without token: 60 requests/hour | With token: 5000 requests/hour")
    print("  Get one: https://github.com/settings/tokens (no scopes required)")
    current = config.get("github_token")
    if current:
        print("  Current status: ✅ configured")
    else:
        key = getpass.getpass("  GITHUB_TOKEN (press Enter to skip): ").strip()
        if key:
            config.set("github_token", key)
            print("  ✅ GitHub API limit raised to 5000 requests/hour!")
        else:
            print("  Skipped. The public API works too")
    print()

    # Step 3: Reddit — rdt-cli
    print("[Info] Reddit — requires a logged-in session (no zero-config path). OpenCLI is recommended on desktop; or rdt-cli:")
    print(f"  Install: pipx install '{_RDT_GIT_SOURCE}'")
    print("  Then run: rdt login (log in to reddit.com in the browser first)")
    print()

    # Step 4: Groq (Whisper)
    print("[Optional] Groq API — speech-to-text for videos without subtitles")
    print("  Free tier, sign up: https://console.groq.com")
    current = config.get("groq_api_key")
    if current:
        print("  Current status: ✅ configured")
    else:
        key = getpass.getpass("  GROQ_API_KEY (press Enter to skip): ").strip()
        if key:
            config.set("groq_api_key", key)
            print("  ✅ Speech-to-text enabled!")
        else:
            print("  Skipped")
    print()

    # Summary
    print("=" * 40)
    print(f"✅ Config saved to {config.config_path}")
    print("Run weblens doctor to see the full status")
    print()
