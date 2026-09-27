"""``weblens uninstall`` — remove WebLens config, tokens, and skill files."""

import os


def _cmd_uninstall(args):
    """Remove all WebLens config, tokens, and skill files."""
    import shutil
    import subprocess

    from weblens.utils.paths import home_dir

    dry_run = args.dry_run
    keep_config = args.keep_config

    print()
    print("WebLens Uninstaller")
    print("=" * 40)

    if dry_run:
        print("DRY RUN — showing what would be removed (no changes)")
        print()

    removed_any = False
    mcporter_cleanup_skipped = False

    # ── 1. Config directory (~/.weblens/) ──
    config_dir = home_dir() / ".weblens"
    if not keep_config:
        if os.path.isdir(config_dir):
            if dry_run:
                print(f"[dry-run] Would remove config directory: {config_dir}")
                print("          (contains config.yaml with all tokens/cookies/API keys)")
            else:
                try:
                    shutil.rmtree(config_dir)
                    print(f"  Removed config directory: {config_dir}")
                    removed_any = True
                except Exception as e:
                    print(f"  Could not remove {config_dir}: {e}")
        else:
            print(f"  Config directory not found (already clean): {config_dir}")
    else:
        print(f"  Skipping config directory (--keep-config): {config_dir}")

    # Opt-in legacy copies may be shared with upstream tools. Without a
    # provenance marker it would be unsafe to delete them automatically, so
    # surface every exact path that may still contain Twitter credentials.
    legacy_credential_paths = (
        home_dir() / ".config" / "xfetch" / "session.json",
        home_dir() / ".config" / "bird" / "credentials.env",
    )
    present_legacy_paths = [
        path for path in legacy_credential_paths if os.path.lexists(path)
    ]
    if present_legacy_paths:
        print("  [!] Optional legacy Twitter credential copies detected; they will not be deleted automatically:")
        for path in present_legacy_paths:
            print(f"      {path}")
        print("      If you confirm they are no longer used by xfetch/bird, delete them manually.")

    # ── 2. Skill files ──
    skill_dirs = [
        ("~/.config/opencode/skills/weblens", "OpenCode"),
        ("~/.openclaw/skills/weblens", "OpenClaw"),
        ("~/.claude/skills/weblens", "Claude Code"),
        ("~/.agents/skills/weblens", "Agent"),
    ]

    for skill_path_template, platform_name in skill_dirs:
        skill_path = os.path.expanduser(skill_path_template)
        if os.path.isdir(skill_path):
            if dry_run:
                print(f"[dry-run] Would remove {platform_name} skill: {skill_path}")
            else:
                try:
                    if os.path.islink(skill_path):
                        os.unlink(skill_path)
                    else:
                        shutil.rmtree(skill_path)
                    print(f"  Removed {platform_name} skill: {skill_path}")
                    removed_any = True
                except Exception as e:
                    print(f"  Could not remove {skill_path}: {e}")

    # ── 3. mcporter MCP entries ──
    if shutil.which("mcporter"):
        from weblens.channels.mcporter import (
            McporterConfigError,
            configured_server_names,
        )

        try:
            result = subprocess.run(
                [
                    "mcporter",
                    "config",
                    "list",
                    "--json",
                ],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if result.returncode != 0:
                raise McporterConfigError("mcporter config query failed")
            server_names = configured_server_names(result.stdout)
        except (
            McporterConfigError,
            OSError,
            subprocess.TimeoutExpired,
        ):
            mcporter_cleanup_skipped = True
            print(
                "  [!] Could not safely verify the origin of the mcporter config; "
                "exa/xiaohongshu entries will not be deleted automatically."
            )
        else:
            for mcp_name in ("exa", "xiaohongshu"):
                if mcp_name not in server_names:
                    continue
                mcporter_cleanup_skipped = True
                print(
                    f"  [!] mcporter entry {mcp_name} cannot be proven to be managed by "
                    "WebLens; kept. If you confirm it is no longer needed, remove it manually."
                )

    # ── 4. Summary and optional steps ──
    print()
    if dry_run:
        print("Dry run complete. No changes were made.")
        print("Run without --dry-run to actually remove the above.")
    else:
        if removed_any:
            print("WebLens data removed.")
        elif mcporter_cleanup_skipped:
            print("No proven WebLens-managed mcporter data was removed.")
        else:
            print("Nothing to remove — already clean.")

    print()
    print("Optional: remove the WebLens Python package itself:")
    print("  pip uninstall weblens")
    print()
    print("Optional: remove tools installed by WebLens:")
    print("  npm uninstall -g mcporter")
    print("  pipx uninstall twitter-cli")
    print("  npm uninstall -g undici")
