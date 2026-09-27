"""Run upstream CLIs safely: argv lists only (never a shell), bounded time."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import yaml

from weblens.utils.process import utf8_subprocess_env

from .errors import ToolMissingError, WebLensError

DEFAULT_TIMEOUT = 90
_MAX_OUTPUT_CHARS = 8 * 1024 * 1024


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def which(tool: str) -> str | None:
    """PATH lookup, then the running interpreter's bin dir (un-activated venvs
    ship yt-dlp as a dependency next to the ``weblens`` entry point)."""
    found = shutil.which(tool)
    if found:
        return found
    return shutil.which(tool, path=os.path.dirname(sys.executable))


def run(
    argv: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run ``argv`` (resolved via PATH) and capture text output.

    Raises :class:`ToolMissingError` when the tool is absent and
    :class:`WebLensError` on timeout / exec failure. A non-zero exit is
    returned, not raised, so callers can inspect stderr.
    """
    if not argv:
        raise ValueError("empty command")
    tool = argv[0]
    path = which(tool)
    if not path:
        raise ToolMissingError(tool)
    child_env = utf8_subprocess_env()
    # The proxy saved by `weblens configure proxy`, only when the environment
    # names none (env vars win); explicit per-call env overrides both.
    from weblens.channels._http import proxy_env

    child_env.update(proxy_env())
    if env:
        child_env.update(env)
    try:
        proc = subprocess.run(
            [path, *argv[1:]],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=child_env,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WebLensError(
            f"{tool} timed out after {int(timeout)}s", "retry later or check your network"
        ) from exc
    except OSError as exc:
        raise WebLensError(
            f"{tool} could not be executed ({exc.strerror or exc})",
            f"reinstall {tool}",
        ) from exc
    return CommandResult(
        proc.returncode,
        (proc.stdout or "")[:_MAX_OUTPUT_CHARS],
        (proc.stderr or "")[:_MAX_OUTPUT_CHARS],
    )


def last_error_line(text: str) -> str:
    """The most informative line of a tool's stderr (prefers ``ERROR:`` lines)."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.upper().startswith("ERROR"):
            return line[:300]
    return lines[-1][:300] if lines else "no error output"


def parse_structured(text: str) -> Any:
    """Parse JSON/YAML tool output; returns None if it is not structured."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None
