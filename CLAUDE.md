# CLAUDE.md

## Project
WebLens — Python CLI + library that gives AI agents read/search access to the web and 20 sources
(web, Exa web search, YouTube, GitHub, Hacker News, Wikipedia, arXiv, Stack Overflow, RSS, Reddit,
Twitter/X, LinkedIn, Facebook, Instagram, plus a China pack: Bilibili, Xiaohongshu, V2EX, Xueqiu,
Xiaoyuzhou, BOSS Zhipin).
Positioning: installer + doctor + unified `read`/`search`. WebLens selects, installs (pinned
versions) and health-checks upstream backends, and exposes one `weblens read <url>` /
`weblens search <query>` interface (CLI, Python API, MCP server) that routes to them. For anything
`read`/`search` don't cover, agents call the upstream tools directly (commands in `weblens/skill/`).
Repo: github.com/YOUR_GITHUB_USER/weblens | PyPI: `weblens` | License: MIT | Version: 1.0.0

## Commands
- `python -m venv .venv && .venv/bin/pip install -e ".[dev]"` — Dev install (pytest, ruff, mypy)
- `.venv/bin/pytest -q` — All tests
- `.venv/bin/pytest tests/test_cli.py -v` — CLI tests only
- `.venv/bin/ruff check weblens tests` — Lint (rules in `[tool.ruff]`)
- `.venv/bin/mypy weblens` — Type-check (config in `[tool.mypy]`)
- `bash test.sh` — Clean-venv integration test (install, read-only doctor, test suite)
- `weblens read '<url>' [--json] [--max-chars N]` — Unified read
- `weblens search '<query>' [-s SOURCE] [-n N] [--json]` — Unified search
- `weblens doctor [--json]` — Diagnostics
- `weblens install --env=auto [--system] [--dry-run]` — Check / install dependencies
- `python -m weblens.integrations.mcp_server` — MCP stdio server (`pip install -e ".[mcp]"`)

## Structure
- `weblens/cli.py` — argparse parser + `main()` dispatch only (thin). Global `-v`/`--debug`;
  `_run_command` maps `WebLensError` to exit codes (1 runtime, 2 usage)
- `weblens/commands/` — One module per command, each exposing `_cmd_<name>(args)`:
  `read.py`, `search.py`, `install.py` (installers + pinned versions), `doctor.py`,
  `configure.py`, `setup.py`, `uninstall.py`, `skill.py`, `update.py` (`check-update`, `watch`),
  `transcribe.py`, `format.py`
- `weblens/unified/` — Shared engine behind `read`/`search` (CLI, `core.py`, MCP):
  - `read.py` — URL routing (`ROUTE_ORDER`, native adapters, upstream-CLI adapters, Jina fallback)
  - `search.py` — sources (`SOURCES`, `ALL_SOURCES`), Exa via mcporter, parallel `all`
  - `github.py`, `youtube.py` — gh/public-API and yt-dlp adapters
  - `upstream.py` — subprocess runner for upstream CLIs; `models.py` — `ReadResult`,
    `SearchResult`, `SearchResponse`; `render.py` — text output; `errors.py` — `WebLensError`,
    `UsageError`, `describe_exception`
- `weblens/channels/` — One file per platform, registered in `channels/__init__.py`
  - `base.py` — `Channel` base class (`can_handle`, `check`, ordered `backends`, `active_backend`)
  - `_http.py` — Bounded HTTPS helper for public-API channels: host allowlist, size cap,
    retries with backoff on 429/5xx, `fetch_public` for arbitrary public hosts (RSS)
- `weblens/core.py` — `WebLens` Python API: `read()`, `search()`, `doctor()`, `doctor_report()`
- `weblens/integrations/mcp_server.py` — MCP tools `get_status`, `read`, `search`
- `weblens/utils/url.py` — `normalize_public_http_url` (private/internal URL blocking)
- `weblens/config.py` — Config (`~/.weblens/config.yaml`, mode 600, env overrides)
- `weblens/doctor.py` — Diagnostics engine
- `weblens/skill/` — Agent skill: `SKILL.md` and `SKILL_en.md` (identical content; `skill.py`
  installs `SKILL_en.md` for English locales) + `references/*.md`
- `weblens/guides/` — Per-platform setup guides
- `docs/` — install / update / troubleshooting guides (agents fetch these by URL)
- `tests/` — pytest tests (several assert phrases in the docs and skill files)

## Conventions
- Python 3.10+ with type hints
- Tests patch functions where they are looked up: `weblens.commands.<module>.<name>` (not
  `weblens.cli`), except `main`/`_cmd_*` dispatch which is patched on `weblens.cli`
- Each channel is a single file in `channels/`, subclasses `Channel`, sets `name`,
  `description`, `backends`, `tier`; implements `can_handle(url)` and `check(config)` (must set
  `active_backend`); public-API channels also expose `read(url)` / `search(query, ...)` using
  `channels/_http.py`
- New readable/searchable sources are wired in `unified/read.py` (`ROUTE_ORDER`, `_ADAPTERS`,
  `_NATIVE_SHAPES`) and `unified/search.py` (`SOURCES`, `_search_<name>`)
- Use `loguru` for logging, `rich` for CLI output
- Commit format: `type(scope): message` (one commit = one thing)
- All upstream tool calls go through public API/CLI, never hack internals

## Rules
- NEVER modify upstream open source projects' source code
- Upstream installs are pinned (exact versions / git commits in `commands/install.py`);
  never install from a moving branch
- Untrusted URLs/queries: validate with `normalize_public_http_url`, pass to subprocesses as
  argv lists (never a shell string); docs must show single-quoted `'URL'` placeholders
- Never send private/internal URLs to Jina Reader or Exa
- Secrets never go in process arguments or docs examples (hidden prompt or `--stdin`)
- Version in THREE places must match: `pyproject.toml`, `__init__.py`, `tests/test_cli.py`
- Keep `SKILL.md` and `SKILL_en.md` identical; description ≤ 1024 chars
- Always new branch for changes, PR to main, never push to main directly
- Run `pytest` and `ruff check weblens tests` before committing — all must pass
- Cookie-based auth (Twitter, XHS): Cookie-Editor export only, no QR scan, no automatic login
