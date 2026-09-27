# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-26

First release of WebLens.

### Added

**Unified read and search**

- `weblens read <url> [--json] [--max-chars N]` reads any public URL as clean text and routes
  it to the most specific backend: Hacker News (story + comment tree), Wikipedia (full
  article, any language), arXiv (abstract + metadata), Stack Overflow and other Stack Exchange
  sites (question + answers), YouTube (yt-dlp metadata + transcript), GitHub (repo README,
  issues and PRs via `gh` or the public REST API), V2EX topics, RSS/Atom feeds, and
  Reddit / Twitter/X / Bilibili / Xiaohongshu through the platform's active upstream backend.
  Everything else goes through Jina Reader. Every fallback is reported in `notes`.
- `weblens search <query> [--source/-s S] [--limit/-n N] [--json]` with sources `web`
  (Exa via mcporter, falling back to Hacker News + Wikipedia when Exa is not configured),
  `hackernews`, `wikipedia`, `arxiv`, `stackoverflow`, `youtube`, `github`, `v2ex`,
  `reddit`, `twitter`, and `all` (web + hackernews + wikipedia + stackoverflow + arxiv in
  parallel, with per-source errors that do not fail the whole search).
- Global `--debug` flag (debug logs + full tracebacks) and consistent exit codes: `1` for
  failures, `2` for bad usage.
- Python API: `WebLens().read()` and `WebLens().search()` in `weblens.core`, returning
  `ReadResult` / `SearchResponse` objects with `.to_dict()`.
- MCP server (`python -m weblens.integrations.mcp_server`) with tools `get_status`,
  `read(url, max_chars?, format?)` and `search(query, source?, limit?, format?)`, sharing the
  CLI code path.

**Channels**

- New zero-config channels: Hacker News (Firebase API + Algolia search), Wikipedia (REST +
  MediaWiki API), arXiv (arXiv API), Stack Overflow / Stack Exchange (API 2.3, quota-aware).
- Channels for Twitter/X, Reddit, Facebook, Instagram, YouTube, GitHub, LinkedIn, RSS, Exa web
  search, any web page, and a China pack: Bilibili, Xiaohongshu (RedNote), V2EX, Xueqiu,
  Xiaoyuzhou Podcast, BOSS Zhipin.
- Ordered per-platform backend lists with live probing; `weblens doctor [--json]` reports the
  active backend per channel. Override with `<channel>_backend` / `<CHANNEL>_BACKEND`.

**Reliability**

- Shared HTTPS helper for public-API channels with bounded retries (exponential backoff +
  jitter, honoring `Retry-After`) on HTTP 429/502/503/504 and transient network errors.
- YouTube subtitle downloads retry once more slowly after HTTP 429 and degrade to metadata
  with a note.
- Stack Exchange `backoff` instructions are honored automatically; low keyless quota is logged.
- Clear GitHub rate-limit errors pointing to `gh auth login`.

**Security**

- Private-URL blocking: `read` rejects localhost, private/link-local IPs and internal
  hostnames; RSS fetches re-validate every redirect hop; public-API channels only talk to an
  allowlist of HTTPS hosts with response-size caps.
- Pinned installs: `weblens install --system` installs exact versions of mcporter, OpenCLI,
  twitter-cli and bilibili-cli, and fixed git commits for rdt-cli and boss-agent-cli.
- Skill and docs teach agents to pass untrusted URLs/queries as single-quoted arguments and
  to refuse input with shell metacharacters; upstream CLIs are always run with argv lists.
- Credentials are stored only in `~/.weblens/config.yaml` (mode 600) and entered through a
  hidden prompt or `--stdin`, never process arguments.

**Tooling**

- `weblens install` (check-only by default; `--system`, `--dry-run`, `--channels`),
  `weblens configure`, `weblens setup`, `weblens skill --install/--uninstall` (Claude Code,
  OpenClaw, OpenCode, generic `~/.agents/skills`), `weblens uninstall`.
- `weblens watch` and `weblens check-update` for scheduled health and update checks.
- `weblens transcribe` for audio/video transcription with Groq or OpenAI Whisper, plus
  Xiaoyuzhou podcast transcription.
