"""``weblens skill`` — install/remove SKILL.md in agent skill directories."""

import os


def _install_skill(force: bool = True):
    """Install WebLens as an agent skill for supported agent clients."""
    import importlib.resources
    import os
    import shutil

    def _is_english_locale(value: str) -> bool:
        normalized = value.strip().lower()
        return normalized.startswith("en") or normalized.startswith("english")

    def _skill_resource_name() -> str:
        locale_candidates = (
            os.environ.get("WEBLENS_LANG", ""),
            os.environ.get("LC_ALL", ""),
            os.environ.get("LC_MESSAGES", ""),
            os.environ.get("LANG", ""),
        )
        if any(_is_english_locale(candidate) for candidate in locale_candidates):
            return "SKILL_en.md"
        return "SKILL.md"

    def _read_skill_markdown(skill_pkg):
        resource_name = _skill_resource_name()
        try:
            return skill_pkg.joinpath(resource_name).read_text(encoding="utf-8")
        except FileNotFoundError:
            return skill_pkg.joinpath("SKILL.md").read_text(encoding="utf-8")

    def _copy_skill_dir(target: str) -> str | None:
        """Copy entire skill directory (locale-specific SKILL.md + references/)."""
        try:
            if not force and os.path.exists(os.path.join(target, "SKILL.md")):
                return "preserved"

            # Clear existing installation. A symlinked skill dir (dotfiles
            # setups) breaks shutil.rmtree — unlink the link itself instead.
            if os.path.islink(target):
                os.unlink(target)
            elif os.path.exists(target):
                shutil.rmtree(target)
            os.makedirs(target, exist_ok=True)

            # Get skill directory from package (with fallback for editable installs)
            try:
                skill_pkg = importlib.resources.files("weblens").joinpath("skill")
                skill_md = _read_skill_markdown(skill_pkg)
            except Exception:
                from pathlib import Path
                skill_pkg = Path(__file__).resolve().parent.parent / "skill"
                skill_md = _read_skill_markdown(skill_pkg)

            # Copy SKILL.md using the selected locale file
            with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(skill_md)

            # Copy references/ directory
            refs_pkg = skill_pkg.joinpath("references")
            refs_target = os.path.join(target, "references")
            os.makedirs(refs_target, exist_ok=True)

            for ref_file in refs_pkg.iterdir():
                name = ref_file.name if hasattr(ref_file, 'name') else str(ref_file).split('/')[-1]
                if name.endswith(".md"):
                    content = ref_file.read_text(encoding="utf-8") if hasattr(ref_file, 'read_text') else ref_file.read_text()
                    with open(os.path.join(refs_target, name), "w", encoding="utf-8") as f:
                        f.write(content)

            return "installed"
        except Exception as e:
            print(f"  Warning: Could not install skill: {e}")
            return None

    # Install into every known skill root that already exists.
    skill_dirs = [
        (os.path.expanduser("~/.agents/skills"), "Agent"),
        (os.path.expanduser("~/.config/opencode/skills"), "OpenCode"),
        (os.path.expanduser("~/.openclaw/skills"), "OpenClaw"),
        (os.path.expanduser("~/.claude/skills"), "Claude Code"),
    ]

    # Insert OPENCLAW_HOME path at the beginning if environment variable is set
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(
            0,
            (os.path.join(openclaw_home, ".openclaw", "skills"), "OpenClaw"),
        )

    installed = False
    for skill_dir, platform_name in skill_dirs:
        if os.path.isdir(skill_dir):
            target = os.path.join(skill_dir, "weblens")
            status = _copy_skill_dir(target)
            if status:
                if status == "preserved":
                    print(f"Skill already installed for {platform_name}, preserving existing files: {target}")
                else:
                    print(f"Skill installed for {platform_name}: {target}")
                installed = True

    if not installed:
        # No known skill directory found — create for .agents by default
        target = os.path.expanduser("~/.agents/skills/weblens")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        status = _copy_skill_dir(target)
        if status == "preserved":
            print(f"Skill already installed, preserving existing files: {target}")
        elif status == "installed":
            print(f"Skill installed: {target}")
            installed = True
        else:
            print("  -- Could not install agent skill (optional)")
            print(
                "  -- Tip: install OpenCode, OpenClaw, Claude Code, "
                "or create ~/.agents/skills/ manually"
            )
    return installed


def _uninstall_skill():
    """Remove SKILL.md from all known agent skill directories."""
    import shutil

    skill_dirs = [
        ("~/.config/opencode/skills/weblens", "OpenCode"),
        ("~/.openclaw/skills/weblens", "OpenClaw"),
        ("~/.claude/skills/weblens", "Claude Code"),
        ("~/.agents/skills/weblens", "Agent"),
    ]

    # Also check OPENCLAW_HOME
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(
            0,
            (os.path.join(openclaw_home, ".openclaw", "skills", "weblens"), "OpenClaw"),
        )

    removed = False
    for skill_path_template, platform_name in skill_dirs:
        skill_path = os.path.expanduser(skill_path_template)
        if os.path.isdir(skill_path):
            try:
                if os.path.islink(skill_path):
                    os.unlink(skill_path)
                else:
                    shutil.rmtree(skill_path)
                print(f"  Removed {platform_name} skill: {skill_path}")
                removed = True
            except Exception as e:
                print(f"  Could not remove {skill_path}: {e}")

    if not removed:
        print("  No skill installations found.")


def _cmd_skill(args):
    """Manage agent skill registration."""
    if args.install:
        if not _install_skill():
            raise SystemExit(1)
    elif args.uninstall:
        _uninstall_skill()
