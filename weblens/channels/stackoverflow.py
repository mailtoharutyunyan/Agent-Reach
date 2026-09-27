"""Stack Overflow / Stack Exchange — public API 2.3 (keyless, gzip, quota-aware).

Keyless access is limited to ~300 requests/day per IP. Every response carries
``quota_remaining`` / ``quota_max`` (exposed on ``channel.last_quota``) and may
carry ``backoff`` (seconds): the API requires waiting that long before hitting
the same method again, which this module enforces process-wide.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from loguru import logger

from weblens.utils.url import host_matches

from . import _http
from .base import Channel

_API_BASE = "https://api.stackexchange.com/2.3"
_ALLOWED_HOSTS = frozenset({"api.stackexchange.com"})
_TIMEOUT = 15
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_LIMIT = 100
_MAX_IDS = 100
_MAX_BACKOFF_WAIT = 10.0
_LOW_QUOTA = 20
_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,49}$")
_SORTS = {"relevance", "votes", "creation", "activity"}
# Hosts whose API site parameter is the host minus its TLD (plus *.stackexchange.com).
_SITE_DOMAINS = (
    "stackoverflow.com",
    "stackexchange.com",
    "superuser.com",
    "serverfault.com",
    "askubuntu.com",
    "mathoverflow.net",
    "stackapps.com",
)

_backoff_lock = threading.Lock()
_backoff_until: dict[str, float] = {}


def _validate_site(site: str) -> str:
    site = (site or "stackoverflow").strip().lower()
    if not _SITE_RE.match(site):
        raise ValueError(f"invalid Stack Exchange site: {site!r}")
    return site


def _ids(values: int | str | list[int] | list[str]) -> str:
    raw = values if isinstance(values, list) else [values]
    out: list[str] = []
    for value in raw:
        try:
            number = int(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"invalid Stack Exchange id: {value!r}") from exc
        if number <= 0:
            raise ValueError(f"invalid Stack Exchange id: {value!r}")
        out.append(str(number))
    if not out or len(out) > _MAX_IDS:
        raise ValueError(f"between 1 and {_MAX_IDS} ids are required")
    return ";".join(out)


def _wait_for_backoff(method: str) -> None:
    with _backoff_lock:
        until = _backoff_until.get(method, 0.0)
    remaining = until - time.monotonic()
    if remaining <= 0:
        return
    if remaining > _MAX_BACKOFF_WAIT:
        raise RuntimeError(
            f"Stack Exchange API asked to back off from {method} for {remaining:.0f}s more"
        )
    time.sleep(remaining)


def _record_backoff(method: str, seconds: Any) -> None:
    try:
        delay = float(seconds)
    except (TypeError, ValueError):
        return
    if delay > 0:
        with _backoff_lock:
            _backoff_until[method] = time.monotonic() + delay


class StackOverflowChannel(Channel):
    name = "stackoverflow"
    description = "Stack Overflow / Stack Exchange questions and answers"
    backends = ["Stack Exchange API 2.3 (public)"]
    tier = 0

    def __init__(self) -> None:
        #: quota_remaining / quota_max from the most recent API response.
        self.last_quota: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        return host_matches(url, *_SITE_DOMAINS)

    # ------------------------------------------------------------------ #
    # Health check — zero-cost, no network (keyless quota is precious)
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        self.active_backend = self.backends[0]
        return "ok", "Public API (search, questions + answers; keyless ~300 req/day)"

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #

    def _call(self, method: str, path: str, params: dict[str, Any]) -> dict:
        """Call one API method, honoring backoff and surfacing API errors."""
        _wait_for_backoff(method)
        url = f"{_API_BASE}{path}?{urlencode(params)}"
        status, body = _http.get_bytes(
            url,
            allowed_hosts=_ALLOWED_HOSTS,
            timeout=_TIMEOUT,
            max_bytes=_MAX_RESPONSE_BYTES,
            error_body=True,
        )
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError as exc:
            raise RuntimeError(f"Stack Exchange API returned HTTP {status} (non-JSON)") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Stack Exchange API returned an unexpected payload")

        _record_backoff(method, data.get("backoff"))
        if "quota_remaining" in data:
            self.last_quota = {
                "quota_remaining": int(data.get("quota_remaining") or 0),
                "quota_max": int(data.get("quota_max") or 0),
            }
            if self.last_quota["quota_remaining"] < _LOW_QUOTA:
                logger.warning(
                    "Stack Exchange keyless quota low: {} of {} requests left today",
                    self.last_quota["quota_remaining"],
                    self.last_quota["quota_max"],
                )
        if "error_id" in data or status >= 400:
            raise RuntimeError(
                "Stack Exchange API error "
                f"{data.get('error_id', status)} ({data.get('error_name', 'http_error')}): "
                f"{data.get('error_message', '')}".rstrip(": ")
            )
        return data

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        site: str = "stackoverflow",
        limit: int = 10,
        tagged: str | list[str] | None = None,
        sort: str = "relevance",
        accepted: bool | None = None,
    ) -> list[dict]:
        """Search questions (/search/advanced).

        Args:
            query:    free-text query
            site:     API site slug: stackoverflow, superuser, serverfault,
                      askubuntu, unix, math, ...
            limit:    max questions (1-100)
            tagged:   tag or list of tags that must all be present
            sort:     relevance | votes | creation | activity (descending)
            accepted: True/False to require (or exclude) an accepted answer

        Returns a list of dicts with keys:
          question_id, title, url, score, answer_count, is_answered,
          accepted_answer_id, tags, author, creation_date
        """
        if sort not in _SORTS:
            raise ValueError(f"sort must be one of {', '.join(sorted(_SORTS))}")
        params: dict[str, Any] = {
            "q": query,
            "site": _validate_site(site),
            "pagesize": max(1, min(int(limit), _MAX_LIMIT)),
            "order": "desc",
            "sort": sort,
        }
        if tagged:
            params["tagged"] = ";".join(tagged) if isinstance(tagged, list) else tagged
        if accepted is not None:
            params["accepted"] = "True" if accepted else "False"
        data = self._call("search/advanced", "/search/advanced", params)
        return [self._shape_question(q) for q in data.get("items") or []]

    def get_question(
        self,
        question_id: int | str,
        site: str = "stackoverflow",
        answer_limit: int = 10,
    ) -> dict:
        """Get a question with its body and top-voted answers (2 API calls).

        Returns the search() dict plus ``body`` (plain text) and ``answers``
        (see get_answers). Pass answer_limit=0 to skip fetching answers.
        """
        ids = _ids(question_id)
        site = _validate_site(site)
        data = self._call(
            "questions",
            f"/questions/{quote(ids, safe=';')}",
            {"site": site, "filter": "withbody"},
        )
        items = data.get("items") or []
        if not items:
            raise ValueError(f"question {ids} not found on {site}")
        result = self._shape_question(items[0])
        result["body"] = _http.html_to_text(items[0].get("body"))
        result["answers"] = (
            self.get_answers(ids, site=site, limit=answer_limit) if answer_limit > 0 else []
        )
        return result

    def get_answers(
        self,
        question_ids: int | str | list[int] | list[str],
        site: str = "stackoverflow",
        limit: int = 10,
    ) -> list[dict]:
        """Get answers for one or more questions, highest-voted first.

        Returns a list of dicts with keys:
          answer_id, question_id, score, is_accepted, author, creation_date,
          url, body (plain text)
        """
        ids = _ids(question_ids)
        site = _validate_site(site)
        data = self._call(
            "questions/answers",
            f"/questions/{quote(ids, safe=';')}/answers",
            {
                "site": site,
                "filter": "withbody",
                "sort": "votes",
                "order": "desc",
                "pagesize": max(1, min(int(limit), _MAX_LIMIT)),
            },
        )
        answers = []
        for a in data.get("items") or []:
            answer_id = a.get("answer_id", 0)
            answers.append(
                {
                    "answer_id": answer_id,
                    "question_id": a.get("question_id", 0),
                    "score": a.get("score", 0),
                    "is_accepted": bool(a.get("is_accepted")),
                    "author": (a.get("owner") or {}).get("display_name", ""),
                    "creation_date": a.get("creation_date", 0),
                    "url": f"https://{self._site_host(site)}/a/{answer_id}",
                    "body": _http.html_to_text(a.get("body")),
                }
            )
        return answers

    def read(self, url: str) -> dict:
        """Read a question URL (…/questions/<id>/… or …/q/<id>) on any supported site."""
        if not self.can_handle(url):
            raise ValueError("not a Stack Exchange URL")
        parsed = urlsplit(url)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2 or parts[0] not in {"questions", "q"} or not parts[1].isdigit():
            raise ValueError("URL must look like /questions/<id>/... or /q/<id>")
        return self.get_question(parts[1], site=self.site_from_host(parsed.hostname or ""))

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def site_from_host(host: str) -> str:
        """Map a site hostname to its API slug (unix.stackexchange.com -> unix)."""
        host = host.lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        if host.endswith(".stackexchange.com"):
            return _validate_site(host[: -len(".stackexchange.com")])
        return _validate_site(host.rsplit(".", 1)[0])

    @staticmethod
    def _site_host(site: str) -> str:
        known = {d.rsplit(".", 1)[0]: d for d in _SITE_DOMAINS}
        if site in known:
            return known[site]
        prefix, _, parent = site.rpartition(".")
        if prefix and parent in known:  # ru.stackoverflow, meta.superuser
            return f"{prefix}.{known[parent]}"
        return f"{site}.stackexchange.com"

    def _shape_question(self, q: dict) -> dict:
        return {
            "question_id": q.get("question_id", 0),
            "title": _http.html_to_text(q.get("title")),
            "url": q.get("link", ""),
            "score": q.get("score", 0),
            "answer_count": q.get("answer_count", 0),
            "is_answered": bool(q.get("is_answered")),
            "accepted_answer_id": q.get("accepted_answer_id"),
            "tags": q.get("tags") or [],
            "author": (q.get("owner") or {}).get("display_name", ""),
            "creation_date": q.get("creation_date", 0),
        }
