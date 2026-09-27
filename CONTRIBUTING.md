# Contributing to WebLens

Thanks for helping improve WebLens. New channels, backend fixes, and doc corrections are
all welcome.

## Development setup

Requires Python 3.10+.

```bash
git clone https://github.com/YOUR_GITHUB_USER/weblens.git
cd weblens

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"              # pytest, ruff, mypy, type stubs
# Reproducible, pinned baseline (see docs/dependency-locking.md):
# pip install -c constraints.txt -e ".[dev]"

weblens --help                       # the editable install puts `weblens` on PATH
```

For the MCP server: `pip install -e ".[dev,mcp]"`.

## Checks

Run all three before opening a PR:

```bash
pytest -q                     # full test suite, no network needed
ruff check weblens tests      # lint (rules in [tool.ruff] in pyproject.toml)
mypy weblens                  # type-check (config in [tool.mypy])
```

`bash test.sh` runs the suite in a throwaway virtualenv with an isolated `$HOME`, the
closest thing to a clean install.

Some tests assert phrases in `README.md`, `docs/`, and `weblens/skill/` (security rules,
auth boundaries, quoting). If you change those files, run the tests; update a test only when
the phrase it guards is genuinely obsolete.

## Project layout

| Path | What lives there |
|---|---|
| `weblens/cli.py` | argparse parser and dispatch only |
| `weblens/commands/` | one module per CLI command (`_cmd_<name>(args)`) |
| `weblens/unified/` | the engine behind `read` / `search` (routing, adapters, rendering, errors) |
| `weblens/channels/` | one file per platform + `_http.py` shared HTTPS helper |
| `weblens/core.py` | Python API (`WebLens`) |
| `weblens/integrations/mcp_server.py` | MCP server |
| `weblens/skill/` | agent skill (`SKILL.md` = `SKILL_en.md`) and `references/` |
| `docs/` | install, update, troubleshooting guides |

## Adding a channel

1. **Create `weblens/channels/<name>.py`** with a `Channel` subclass:

   ```python
   from .base import Channel

   class ExampleChannel(Channel):
       name = "example"                     # unique, lowercase
       description = "Example posts and search"
       backends = ["Example API (public)"]  # ordered: preferred first
       tier = 0                             # 0 zero-config, 1 free key/login, 2 more setup

       def can_handle(self, url: str) -> bool:
           ...                              # host match for this platform

       def check(self, config=None):
           # Really probe external backends (see weblens.probe); never trust which() alone.
           self.active_backend = self.backends[0]
           return "ok", "Public API"
   ```

   `check()` must return `(status, message)` with status `ok` / `warn` / `off` / `error`
   and set `active_backend` (or `None` when nothing works). Channels that wrap an upstream
   CLI probe each backend in order and pick the first that actually runs.

2. **Use `channels/_http.py` for HTTP.** Public-API channels call
   `_http.get_json(url, allowed_hosts={"api.example.com"})` or `_http.get_bytes(...)`. That
   gives you HTTPS-only access to an explicit host allowlist, redirect re-validation, a
   timeout, a response-size cap, the `weblens/<version>` User-Agent, and retries on
   429/5xx. Do not call `urllib`/`requests` directly, and never fetch a user-supplied URL
   without `normalize_public_http_url` (or `_http.fetch_public` for arbitrary hosts).
   Expose `read(url)` and `search(query, limit=...)` methods that return plain dicts.

3. **Register it** in `weblens/channels/__init__.py` (import + `ALL_CHANNELS`). `weblens doctor`
   picks it up automatically.

4. **Wire up `read` / `search`** if the platform supports them:
   - `weblens/unified/read.py`: add the name to `ROUTE_ORDER` (most specific first), an
     adapter in `_ADAPTERS` that maps your dict to a `ReadResult`, and a URL shape in
     `_NATIVE_SHAPES` if only some page types have a native reader.
   - `weblens/unified/search.py`: add the source to `SOURCES`, a `_search_<name>` function
     returning `(results, notes)`, and to `ALL_SOURCES` only if it is fast, keyless and
     broadly useful.
   - Update the `--source` help text in `weblens/cli.py` and the MCP tool descriptions.

5. **Tests** — add `tests/test_<name>_channel.py` with mocked HTTP (patch `_http`; no real
   network), covering `can_handle`, parsing, error handling, and limits. The registry-wide
   contract tests in `tests/test_channel_contracts.py` must still pass. Add routing/search
   cases to `tests/test_unified_read.py` / `tests/test_unified_search.py`.

6. **Docs** — the supported-sources table in `README.md`, the routing table in
   `weblens/skill/SKILL.md` (and copy it to `SKILL_en.md`), the matching
   `weblens/skill/references/*.md`, and `CHANGELOG.md`.

If the channel needs an upstream tool, add its installer to `weblens/commands/install.py`
with a **pinned** version or commit, never a moving branch.

## Pull request guidelines

- One logical change per PR; small and focused beats large refactors.
- Branch from `main`; never push to `main` directly.
- Commit messages: `type(scope): message`, e.g. `feat(channels): add lobsters`,
  `fix(youtube): handle 429 on subtitles`.
- Include tests for new behavior and for bug fixes.
- Keep docs in sync with the code, and verify every command you document with
  `weblens <cmd> --help`.
- Security rules are not optional: no secrets in process arguments or examples,
  single-quoted `'URL'` placeholders in shell examples, no private URLs sent to third-party
  services, no modifications to upstream projects' source.
- Describe what you tested (commands and output) in the PR description.

## Reporting issues

Please include your OS and Python version, the output of `weblens version` and
`weblens doctor --json`, the exact command, and the full error (rerun with `--debug`).
Remove cookies, tokens, and private URLs before posting.

Security vulnerabilities: do not open a public issue; see [SECURITY.md](SECURITY.md).
