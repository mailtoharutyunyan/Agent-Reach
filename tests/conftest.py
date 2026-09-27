"""Suite-wide containment for tests that exercise user-facing installers."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from weblens.config import Config


@pytest.fixture(scope="session")
def bash_executable() -> str:
    """Return a real GNU Bash, avoiding Windows' WSL launcher stub."""
    candidates: list[Path] = []
    override = os.environ.get("WEBLENS_TEST_BASH")
    if override:
        candidates.append(Path(override))

    if os.name == "nt":
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            program_files = os.environ.get(env_name)
            if program_files:
                git_root = Path(program_files) / "Git"
                candidates.extend(
                    (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
                )

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            git_root = Path(local_app_data) / "Programs" / "Git"
            candidates.extend(
                (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
            )

        git = shutil.which("git")
        if git:
            git_parent = Path(git).resolve().parent
            if git_parent.name.lower() in {"bin", "cmd"}:
                git_root = git_parent.parent
                candidates.extend(
                    (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
                )

    discovered = shutil.which("bash")
    if discovered:
        candidates.append(Path(discovered))

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.fspath(candidate))
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        try:
            result = subprocess.run(
                [os.fspath(candidate), "--version"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and "GNU bash" in result.stdout:
            return os.fspath(candidate)

    pytest.fail("GNU Bash is required for shell-script tests")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect every common home/config root before each test runs."""
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.delenv("OPENCLAW_HOME", raising=False)

    config_dir = home / ".weblens"
    monkeypatch.setattr(Config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", config_dir / "config.yaml")
    return home


@pytest.fixture(autouse=True)
def isolated_xueqiu_cookie_jar(monkeypatch):
    """Prevent the module-level Xueqiu session from leaking between tests."""
    from weblens.channels import xueqiu

    xueqiu._cookie_jar.clear()
    monkeypatch.setattr(xueqiu, "_cookies_initialized", False)
    yield
    xueqiu._cookie_jar.clear()


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    """Retry backoff must never really sleep in tests; record requested delays."""
    from weblens.channels import _http

    delays: list[float] = []
    monkeypatch.setattr(_http, "_sleep", delays.append)
    return delays


@pytest.fixture(autouse=True)
def no_feed_sniff(monkeypatch):
    """`weblens read` sniffs unclaimed URLs for feeds; never hit the network in tests.

    Tests covering the sniff patch ``weblens.unified.read._sniff_feed`` (or the
    lower-level ``_http`` openers) themselves.
    """
    from weblens.unified import read as unified_read

    real = unified_read._sniff_feed
    monkeypatch.setattr(unified_read, "_sniff_feed", lambda url: None)
    return real
