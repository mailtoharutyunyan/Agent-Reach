"""
Channel base class — platform availability checking.

Each channel represents a platform (YouTube, Twitter, GitHub, etc.)
and provides:
  - can_handle(url) → does this URL belong to this platform?
  - check(config) → is the upstream tool installed and configured?

Channels back the installer and ``weblens doctor``; the unified
``read``/``search`` layer (``weblens.unified``) uses them for routing and
backend selection. Upstream tools remain available for direct use.

Backend routing semantics:
  - `backends` is an ORDERED candidate list: backends[0] is the preferred
    backend, the rest are fallbacks. "Switching backends" for a platform
    means reordering this list (or a user override) — not rewriting code.
  - check() must set `self.active_backend` to the backend that is actually
    serving the channel right now (None when nothing usable is found).
    shutil.which() alone is NOT proof of health — a stale venv shim passes
    which() but cannot execute (see weblens.probe). Channels should
    really execute a lightweight command before claiming a backend active.
  - Users can force a backend with config key `<channel>_backend`
    (or env var `<CHANNEL>_BACKEND`); ordered_backends() applies it.
"""

from abc import ABC, abstractmethod


class Channel(ABC):
    """Base class for all channels."""

    name: str = ""                    # e.g. "youtube"
    description: str = ""             # e.g. "YouTube videos and subtitles"
    backends: list[str] = []          # ordered candidates — backends[0] = preferred
    tier: int = 0                     # 0=zero-config, 1=needs free key, 2=needs setup

    #: Backend currently serving this channel; set by check(), None = unavailable.
    active_backend: str | None = None

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this channel can handle this URL."""
        ...

    def ordered_backends(self, config=None) -> list[str]:
        """Candidate backends in probe order, honoring the user override.

        The config key `<channel>_backend` (env `<CHANNEL>_BACKEND`) moves the
        named backend to the front of the list; unknown values are ignored so
        a stale override can never hide working backends.
        """
        candidates = list(self.backends)
        override = config.get(f"{self.name}_backend") if config else None
        if override:
            for i, b in enumerate(candidates):
                if b == override or b.startswith(override):
                    candidates.insert(0, candidates.pop(i))
                    break
        return candidates

    def check(self, config=None) -> tuple[str, str]:
        """
        Check if this channel's upstream tool is available.
        Returns (status, message) where status is 'ok'/'warn'/'off'/'error'.

        Subclasses with external backends must really probe them (see
        weblens.probe.probe_command) and set self.active_backend.
        """
        self.active_backend = self.backends[0] if self.backends else "built-in"
        return "ok", f"{', '.join(self.backends) if self.backends else 'built-in'}"
