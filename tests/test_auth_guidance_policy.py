"""Documentation must preserve the project's explicit auth boundaries."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _policy_documents() -> list[Path]:
    documents = list(ROOT.glob("README*.md"))
    for directory in (
        ROOT / "docs",
        ROOT / "weblens" / "guides",
        ROOT / "weblens" / "skill",
    ):
        documents.extend(directory.rglob("*.md"))
    return sorted(set(documents))


def test_xiaohongshu_guidance_never_starts_implicit_login():
    """Do not reintroduce QR or automatic browser-cookie login guidance."""
    xhs_markers = ("xiaohongshu", "xhs")
    legacy_auth_markers = (
        "qr login",
        "qr scan",
        "qrcode",
    )
    forbidden_commands = (
        "xhs " + "login",
        "get_login_" + "qrcode",
    )

    violations = []
    for path in _policy_documents():
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for command in forbidden_commands:
            if command in lowered:
                violations.append(f"{path.relative_to(ROOT)}: {command}")
        for line_number, line in enumerate(lowered.splitlines(), 1):
            if not any(marker in line for marker in xhs_markers):
                continue
            if any(marker in line for marker in legacy_auth_markers):
                violations.append(
                    f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                )

    assert not violations, "\n".join(violations)


def test_xiaohongshu_opencli_and_export_boundaries_are_truthful():
    """Cookie import is for MCP/legacy tools, never OpenCLI or Chrome."""
    boundary_docs = (
        ROOT / "docs" / "install.md",
        ROOT / "weblens" / "guides" / "setup-xiaohongshu.md",
        ROOT / "weblens" / "skill" / "references" / "social.md",
    )
    for path in boundary_docs:
        text = path.read_text(encoding="utf-8")
        assert "explicitly control" in text, path.relative_to(ROOT)
        assert "cookies into OpenCLI" in text, path.relative_to(ROOT)

    xhs_guide = boundary_docs[1].read_text(encoding="utf-8")
    assert "same-domain xiaohongshu.com cookie set" in xhs_guide
    assert "domains other than xiaohongshu.com" in xhs_guide


def test_twitter_operational_docs_explain_the_environment_boundary():
    """Saved cookies help doctor only; direct twitter commands need env vars."""
    operational_docs = (
        ROOT / "README.md",
        ROOT / "docs" / "cookie-export.md",
        ROOT / "docs" / "install.md",
        ROOT / "docs" / "troubleshooting.md",
        ROOT / "weblens" / "guides" / "setup-twitter.md",
        ROOT / "weblens" / "skill" / "SKILL.md",
        ROOT / "weblens" / "skill" / "SKILL_en.md",
        ROOT / "weblens" / "skill" / "references" / "social.md",
    )

    for path in operational_docs:
        text = path.read_text(encoding="utf-8")
        assert "TWITTER_AUTH_TOKEN" in text, path.relative_to(ROOT)
        assert "TWITTER_CT0" in text, path.relative_to(ROOT)

    twitter_guide = (
        ROOT / "weblens" / "guides" / "setup-twitter.md"
    ).read_text(encoding="utf-8")
    assert "does not run `twitter status`" in twitter_guide
    assert "does not modify the current shell" in twitter_guide
    assert "Export → Header String" in twitter_guide
    assert "cookie JSON" not in twitter_guide
    assert "Copy all" not in twitter_guide

    for expected in (
        "--sync-legacy-twitter",
        "~/.weblens/config.yaml",
        "~/.config/xfetch/session.json",
        "~/.config/bird/credentials.env",
    ):
        assert expected in twitter_guide
    assert "By default it only writes" in twitter_guide
    assert "does not delete them automatically" in twitter_guide

    rendered_as_verified = (
        "✅ Twitter/X tweets",
    )
    all_text = "\n".join(
        path.read_text(encoding="utf-8") for path in _policy_documents()
    )
    assert not any(claim in all_text for claim in rendered_as_verified)


def test_localized_readmes_keep_current_bilibili_and_xhs_routes():
    """Translations must not revive retired yt-dlp/Bilibili or XHS defaults."""
    readmes = (
        ROOT / "README.md",
    )

    for path in readmes:
        text = path.read_text(encoding="utf-8")
        assert "bilibili.py     → yt-dlp" not in text, path.relative_to(ROOT)
        assert "YouTube + Bilibili" not in text, path.relative_to(ROOT)
        assert "bili-cli" in text, path.relative_to(ROOT)
        assert (
            "xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli"
            in text
        ), path.relative_to(ROOT)



def test_public_guidance_uses_the_weblens_pypi_package():
    """The PyPI distribution is `weblens` (pyproject name); docs must agree.

    Docs must not warn users away from the PyPI package any more.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pip install weblens" in readme
    candidates = _policy_documents() + [
        ROOT / "weblens" / "integrations" / "mcp_server.py",
    ]
    stale_warning = re.compile(r"same name from PyPI|not this project", re.IGNORECASE)
    violations = []
    for path in candidates:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if stale_warning.search(line):
                violations.append(
                    f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                )

    assert not violations, "\n".join(violations)


def test_public_guidance_never_puts_secrets_in_process_arguments():
    """Operational docs should use hidden prompts or stdin for credentials."""
    forbidden = (
        'weblens configure twitter-cookies "',
        "weblens configure twitter-cookies '",
        'weblens configure xhs-cookies "',
        "weblens configure xhs-cookies '",
        "weblens configure groq-key gsk_",
        "weblens configure openai-key sk-",
        "weblens configure github-token gh",
        "weblens configure proxy http",
    )
    violations = []
    for path in _policy_documents():
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")

    assert not violations, "\n".join(violations)


def test_skill_explains_unverified_backend_state():
    """A null backend is an explicit safety state, not a routing instruction."""
    skills = (
        ROOT / "weblens" / "skill" / "SKILL.md",
        ROOT / "weblens" / "skill" / "SKILL_en.md",
    )
    for path in skills:
        text = path.read_text(encoding="utf-8")
        assert "active_backend: null" in text, path.relative_to(ROOT)
        assert "Doctor" in text, path.relative_to(ROOT)


def test_video_reference_has_content_level_youtube_fallbacks():
    """Version-only health must not be presented as proof subtitles work."""
    text = (
        ROOT / "weblens" / "skill" / "references" / "video.md"
    ).read_text(encoding="utf-8")
    assert "opencli youtube transcript" in text
    assert "retry at most 3 times" in text
    assert "weblens transcribe" in text


def test_skill_routes_finance_and_documents_opencli_discovery():
    skills = (
        ROOT / "weblens" / "skill" / "SKILL.md",
        ROOT / "weblens" / "skill" / "SKILL_en.md",
    )
    for path in skills:
        text = path.read_text(encoding="utf-8")
        assert "references/finance.md" in text, path.relative_to(ROOT)
        assert "opencli list" in text, path.relative_to(ROOT)
        assert "--help" in text, path.relative_to(ROOT)

    finance = ROOT / "weblens" / "skill" / "references" / "finance.md"
    text = finance.read_text(encoding="utf-8")
    assert "opencli xueqiu stock" in text
    assert "weblens configure --from-browser chrome --platform xueqiu" in text
