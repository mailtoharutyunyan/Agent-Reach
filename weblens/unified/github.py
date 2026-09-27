"""GitHub read/search: ``gh api`` when gh is installed and authenticated,
otherwise the public REST API (api.github.com only).

The REST path sends ``Authorization: Bearer <token>`` when a token is
available — ``GH_TOKEN`` / ``GITHUB_TOKEN`` first, then the ``github_token``
saved by ``weblens configure github-token`` / ``weblens setup``. The token is
never logged or included in notes/errors."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from weblens.channels import _http
from weblens.channels.github import (
    _GH_READ_ONLY_ENV,
    GitHubConfigError,
    _saved_github_host_configured,
)

from . import upstream
from .errors import WebLensError
from .models import ReadResult, SearchResult

_API = "https://api.github.com"
_ALLOWED_HOSTS = frozenset({"api.github.com"})
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_MAX_COMMENTS = 30
_RATE_HINT = ("unauthenticated GitHub API limit is 60 req/h; save a token with "
              "`weblens configure github-token` (or brew install gh && gh auth login)")
_TOKEN_RATE_HINT = "authenticated GitHub API limit is 5000 req/h; wait for the reset and retry"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{1,255}$")
_PUBLIC_BACKEND = "GitHub REST API (public)"
_TOKEN_BACKEND = "GitHub REST API (token)"

Runner = Callable[..., upstream.CommandResult]


def gh_ready() -> bool:
    """gh is on PATH and has credentials (env token or saved hosts.yml login)."""
    if not upstream.which("gh"):
        return False
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return True
    try:
        return _saved_github_host_configured()
    except GitHubConfigError:
        return False


def _load_config(config: Any) -> Any:
    if config is not None:
        return config
    try:
        from weblens.config import Config

        return Config(read_only=True)
    except Exception:
        return None


def rest_token(config: Any = None) -> tuple[str | None, list[str]]:
    """Return ``(token, notes)`` for the REST path; env vars beat saved config."""
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = (os.environ.get(name) or "").strip()
        if value:
            if _TOKEN_RE.match(value):
                return value, []
            return None, [f"{name} contains unexpected characters; ignored"]
    config = _load_config(config)
    try:
        data = getattr(config, "data", None)
        saved = data.get("github_token") if isinstance(data, dict) else None
    except Exception:
        saved = None
    if not saved:
        return None, []
    value = str(saved).strip()
    if not _TOKEN_RE.match(value):
        return None, ["saved github_token contains unexpected characters; ignored "
                      "(re-run `weblens configure github-token`)"]
    return value, []


class _Client:
    """Fetch REST paths via gh (preferred) or the REST API; records the backend."""

    def __init__(self, run: Runner | None = None, use_gh: bool | None = None,
                 config: Any = None) -> None:
        self.run = run or upstream.run
        self.use_gh = gh_ready() if use_gh is None else use_gh
        self.notes: list[str] = []
        self._token: str | None = None
        if not self.use_gh:
            self._token, token_notes = rest_token(config)
            self.notes.extend(token_notes)
        self._config = config
        self.backend = "gh CLI" if self.use_gh else self._rest_backend()

    def _rest_backend(self) -> str:
        return _TOKEN_BACKEND if self._token else _PUBLIC_BACKEND

    def __repr__(self) -> str:  # never expose the token
        return f"<github _Client backend={self.backend!r}>"

    def get(self, path: str) -> Any:
        if self.use_gh:
            proc = self.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                            timeout=60, env=_GH_READ_ONLY_ENV)
            if proc.ok:
                return json.loads(proc.stdout or "null")
            line = upstream.last_error_line(proc.stderr)
            if "404" in line or "Not Found" in line:
                raise WebLensError(f"GitHub: not found ({path})", "check the URL; private repos need `gh auth login`")
            self.notes.append(f"gh api failed ({line}); fell back to the REST API")
            self.use_gh = False
            self._token, token_notes = rest_token(self._config)
            self.notes.extend(token_notes)
            self.backend = self._rest_backend()
        extra = {"Authorization": f"Bearer {self._token}"} if self._token else None
        try:
            return _http.get_json(f"{_API}/{path}", allowed_hosts=_ALLOWED_HOSTS,
                                  accept="application/vnd.github+json", extra_headers=extra)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
                raise WebLensError("GitHub API rate limit exceeded",
                                   _TOKEN_RATE_HINT if self._token else _RATE_HINT) from exc
            if exc.code == 401 and self._token:
                raise WebLensError(
                    "GitHub rejected the configured token (HTTP 401)",
                    "check GH_TOKEN/GITHUB_TOKEN or re-run `weblens configure github-token`",
                ) from exc
            if exc.code == 404:
                raise WebLensError(f"GitHub: not found ({path})",
                                   "check the URL; private repos need gh: brew install gh && gh auth login") from exc
            raise


_HOSTS = frozenset({"github.com", "www.github.com"})
_SHAPES_HINT = ("native: https://github.com/<owner>/<repo>, …/issues/N, …/pull/N, "
                "…/blob/<ref>/<path>")
#: First path segments that are GitHub site pages, never an ``<owner>``.
RESERVED_OWNERS = frozenset({
    "about", "account", "apps", "blog", "codespaces", "collections", "contact",
    "customer-stories", "dashboard", "enterprise", "events", "explore", "features",
    "github-copilot", "issues", "join", "login", "logout", "marketplace", "new",
    "notifications", "organizations", "orgs", "pricing", "pulls", "readme", "search",
    "security", "sessions", "settings", "signup", "site", "solutions", "sponsors",
    "stars", "team", "topics", "trending", "users", "watching",
})


def _github_path(url: str) -> list[str] | None:
    """Path segments of a github.com URL, or None for other hosts."""
    parsed = urlsplit(url)
    if (parsed.hostname or "").lower() not in _HOSTS:
        return None
    return [p for p in parsed.path.split("/") if p]


def is_site_page(url: str) -> bool:
    """A github.com site page (features, topics, marketplace, …), not repo content."""
    parts = _github_path(url)
    return bool(parts and parts[0].lower() in RESERVED_OWNERS)


def parse_url(url: str) -> dict[str, str]:
    """Parse the exact URL shapes the native reader supports; raise otherwise.

    ``/<owner>/<repo>``, ``/<owner>/<repo>/issues/<n>``, ``/<owner>/<repo>/pull/<n>``
    and ``/<owner>/<repo>/blob/<ref>/<path>``. Everything else (site pages,
    tree/releases/wiki/actions/commits/… subpages) is read as a web page.
    """
    parts = _github_path(url)
    if not parts or len(parts) < 2 or parts[0].lower() in RESERVED_OWNERS:
        raise WebLensError("unsupported GitHub URL", _SHAPES_HINT)
    owner, repo, rest = parts[0], parts[1], parts[2:]
    if not rest:
        repo = repo.removesuffix(".git")
    if not (_NAME_RE.match(owner) and _NAME_RE.match(repo)):
        raise WebLensError("invalid GitHub owner/repo in URL", "check the URL")
    info = {"owner": owner, "repo": repo, "kind": "repo"}
    if not rest:
        return info
    if len(rest) == 2 and rest[0] in ("issues", "pull") and rest[1].isdigit():
        info.update(kind="pull" if rest[0] == "pull" else "issue", number=rest[1])
    elif len(rest) >= 3 and rest[0] == "blob":
        info.update(kind="blob", ref=rest[1], path="/".join(rest[2:]))
    else:
        raise WebLensError("unsupported GitHub URL", _SHAPES_HINT)
    return info


def is_native_url(url: str) -> bool:
    """Whether :func:`read` has a native reader for *url*."""
    try:
        parse_url(url)
    except (WebLensError, ValueError):
        return False
    return True


def _decode_content(data: Any) -> str:
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        return ""
    return base64.b64decode(data.get("content") or "").decode("utf-8", errors="replace")


def _read_repo(client: _Client, owner: str, repo: str) -> ReadResult:
    data = client.get(f"repos/{owner}/{repo}") or {}
    meta = {
        "description": data.get("description") or "",
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues": data.get("open_issues_count"),
        "language": data.get("language") or "",
        "license": ((data.get("license") or {}).get("spdx_id")) or "",
        "topics": ", ".join(data.get("topics") or []),
        "default_branch": data.get("default_branch") or "",
        "updated": data.get("pushed_at") or data.get("updated_at") or "",
        "homepage": data.get("homepage") or "",
    }
    readme = ""
    try:
        readme = _decode_content(client.get(f"repos/{owner}/{repo}/readme"))
    except WebLensError as exc:
        if "not found" not in exc.message:
            raise
        client.notes.append("repository has no README")
    return ReadResult(
        title=data.get("full_name") or f"{owner}/{repo}",
        url=data.get("html_url") or f"https://github.com/{owner}/{repo}",
        source="github",
        body=readme,
        metadata={k: v for k, v in meta.items() if v not in (None, "")},
    )


def _read_issue(client: _Client, owner: str, repo: str, number: str, kind: str) -> ReadResult:
    data = client.get(f"repos/{owner}/{repo}/issues/{number}") or {}
    # The issues API serves both; only its `pull_request` key says which one it is.
    is_pr = isinstance(data, dict) and "pull_request" in data
    if kind == "pull" and not is_pr:
        client.notes.append(f"#{number} is an issue, not a pull request")
    elif kind == "issue" and is_pr:
        client.notes.append(f"#{number} is a pull request; read as one")
    meta: dict[str, Any] = {
        "type": "pull request" if is_pr else "issue",
        "state": data.get("state") or "",
        "author": (data.get("user") or {}).get("login", ""),
        "created": data.get("created_at") or "",
        "comments": data.get("comments"),
        "labels": ", ".join(lbl.get("name", "") for lbl in data.get("labels") or []
                            if isinstance(lbl, dict)),
    }
    if is_pr:
        pr = client.get(f"repos/{owner}/{repo}/pulls/{number}") or {}
        meta.update({
            "merged": pr.get("merged"),
            "branch": f"{(pr.get('head') or {}).get('label', '')} → {(pr.get('base') or {}).get('label', '')}",
            "changes": f"+{pr.get('additions', 0)} −{pr.get('deletions', 0)} in {pr.get('changed_files', 0)} files",
        })
    body = (data.get("body") or "").strip()
    if data.get("comments"):
        comments = client.get(
            f"repos/{owner}/{repo}/issues/{number}/comments?{urlencode({'per_page': _MAX_COMMENTS})}"
        ) or []
        rendered = [
            f"### {(c.get('user') or {}).get('login', '?')} · {c.get('created_at', '')}\n\n{(c.get('body') or '').strip()}"
            for c in comments if isinstance(c, dict)
        ]
        if rendered:
            body += "\n\n## Comments\n\n" + "\n\n".join(rendered)
    return ReadResult(
        title=f"{data.get('title', '')} (#{number})",
        url=data.get("html_url")
        or f"https://github.com/{owner}/{repo}/{'pull' if is_pr else 'issues'}/{number}",
        source="github",
        body=body,
        metadata={k: v for k, v in meta.items() if v not in (None, "")},
    )


def _read_directory(owner: str, repo: str, ref: str, path: str, entries: list[Any]) -> ReadResult:
    items = sorted(
        (e for e in entries if isinstance(e, dict)),
        key=lambda e: (e.get("type") != "dir", str(e.get("name") or "").lower()),
    )
    lines = []
    for entry in items:
        name, kind = str(entry.get("name") or "?"), entry.get("type")
        if kind == "dir":
            lines.append(f"- {name}/")
        elif kind == "file" and entry.get("size") is not None:
            lines.append(f"- {name} ({entry['size']} bytes)")
        else:
            lines.append(f"- {name}" + (f" ({kind})" if kind and kind != "file" else ""))
    shown = path.rstrip("/")
    return ReadResult(
        title=f"{owner}/{repo}: {shown}/",
        url=f"https://github.com/{owner}/{repo}/tree/{ref}/{shown}",
        source="github",
        body=f"## Directory {shown}/ ({len(items)} entries)\n\n" + "\n".join(lines),
        metadata={"ref": ref, "type": "directory", "entries": len(items)},
    )


def _read_blob(client: _Client, owner: str, repo: str, ref: str, path: str) -> ReadResult:
    data = client.get(
        f"repos/{owner}/{repo}/contents/{quote(path)}?{urlencode({'ref': ref})}"
    )
    if isinstance(data, list):  # the contents API lists directories
        return _read_directory(owner, repo, ref, path, data)
    return ReadResult(
        title=f"{owner}/{repo}: {path}",
        url=f"https://github.com/{owner}/{repo}/blob/{ref}/{path}",
        source="github",
        body=_decode_content(data),
        metadata={"ref": ref, "size": (data or {}).get("size")},
    )


def read(url: str, run: Runner | None = None, use_gh: bool | None = None,
         config: Any = None) -> ReadResult:
    info = parse_url(url)
    client = _Client(run, use_gh, config)
    if info["kind"] in ("issue", "pull"):
        result = _read_issue(client, info["owner"], info["repo"], info["number"], info["kind"])
    elif info["kind"] == "blob":
        result = _read_blob(client, info["owner"], info["repo"], info["ref"], info["path"])
    else:
        result = _read_repo(client, info["owner"], info["repo"])
    result.backend = client.backend
    result.notes.extend(client.notes)
    return result


def search(query: str, limit: int, run: Runner | None = None,
           use_gh: bool | None = None, config: Any = None) -> tuple[list[SearchResult], list[str]]:
    client = _Client(run, use_gh, config)
    limit = max(1, min(int(limit), 100))
    data = client.get(f"search/repositories?{urlencode({'q': query, 'per_page': limit})}") or {}
    results = []
    for item in (data.get("items") or [])[:limit]:
        results.append(SearchResult(
            title=item.get("full_name") or "",
            url=item.get("html_url") or "",
            source="github",
            snippet=item.get("description") or "",
            extra={k: v for k, v in {
                "stars": item.get("stargazers_count"),
                "language": item.get("language"),
                "updated": item.get("pushed_at") or item.get("updated_at"),
            }.items() if v not in (None, "")},
        ))
    return results, [f"github backend: {client.backend}", *client.notes]
