"""Twitter/X — check if twitter-cli or bird CLI is available."""

import os
import shutil

from weblens.utils.url import host_matches

from .base import Channel


def twitter_cli_child_env(config=None) -> dict[str, str]:
    """Return saved credentials missing from the current process environment.

    The returned mapping is meant for a single child process.  Existing shell
    variables remain authoritative and ``os.environ`` is never mutated.
    """
    if config is None:
        return {}

    child_env = {}
    for env_name, config_key in (
        ("TWITTER_AUTH_TOKEN", "twitter_auth_token"),
        ("TWITTER_CT0", "twitter_ct0"),
    ):
        if env_name in os.environ:
            continue
        value = config.get(config_key)
        if value:
            child_env[env_name] = str(value)
    return child_env


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X tweets"
    backends = ["twitter-cli", "OpenCLI", "bird CLI (legacy)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "x.com", "twitter.com")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins.

        Same two-phase scheme as the other multi-backend channels: collect every
        candidate's status first, and the first ok wins; only if there is no ok
        does the first warn get its turn - otherwise an "installed but not logged
        in" twitter-cli would shut out a fully working OpenCLI ranked after it.
        """
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "twitter-cli":
                result = self._check_twitter_cli(config)
            elif backend == "OpenCLI":
                result = self._check_opencli()
            elif backend == "bird CLI (legacy)":
                result = self._check_bird()
            else:
                continue

            if result is None:
                continue  # not installed - not a candidate
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend if status == "ok" else None
                    return status, message

        if findings:  # only broken/timeout candidates left
            return "error", "\n".join(m for _, _, m in findings)

        return "warn", (
            "Twitter CLI is not installed. Install with:\n"
            "  pipx install twitter-cli\n"
            "or:\n"
            "  uv tool install twitter-cli"
        )

    def _check_twitter_cli(self, config=None):
        """Inspect explicit credentials without starting twitter-cli.

        Upstream ``twitter status`` automatically reads browser cookies when
        credentials are missing *or invalid*. Doctor cannot disable that
        fallback, so executing it would violate the Cookie-Editor-only policy.
        """
        if not shutil.which("twitter"):
            return None

        child_env = twitter_cli_child_env(config)
        auth_token = os.environ.get("TWITTER_AUTH_TOKEN") or child_env.get(
            "TWITTER_AUTH_TOKEN"
        )
        ct0 = os.environ.get("TWITTER_CT0") or child_env.get("TWITTER_CT0")
        if auth_token and ct0:
            return "warn", (
                "twitter-cli is installed and Cookie-Editor credentials are configured; "
                "Doctor will not run `twitter status` because upstream automatically reads "
                "browser cookies when verification fails. Verify manually when you explicitly consent."
            )
        return "warn", (
            "twitter-cli is installed but has no complete explicit credentials. Export them "
            "from x.com with Cookie-Editor, then run:\n"
            "  weblens configure twitter-cookies\n"
            "Doctor will not read browser cookies automatically."
        )

    def _check_opencli(self):
        """OpenCLI candidate. None = not installed."""
        from weblens.backends import opencli_status

        st = opencli_status()
        if not st.installed:
            return None
        if st.broken:
            return "error", st.hint
        if st.ready:
            return "warn", (
                "OpenCLI bridge is connected, but Twitter/X login state and actual commands were not verified live; "
                "Doctor does not run platform commands, so it is not marked as available for now."
            )
        return "warn", st.hint

    def _check_bird(self):
        """Inspect legacy bird credentials without launching browser fallback."""
        for cmd in ("bird", "birdx"):
            if not shutil.which(cmd):
                continue
            if os.environ.get("AUTH_TOKEN") and os.environ.get("CT0"):
                return (
                    "warn",
                    f"{cmd} is installed and explicit environment credentials exist; to avoid the upstream "
                    "browser cookie fallback, Doctor does not run `check`, so this is not verified live.",
                )
            return "warn", (
                f"{cmd} is installed but no explicit AUTH_TOKEN/CT0 was detected; "
                "only credentials manually exported with Cookie-Editor are used."
            )
        return None
