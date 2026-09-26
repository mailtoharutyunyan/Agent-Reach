# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast (podcast app) — transcribe podcasts via Groq Whisper API."""

import os

from weblens.config import Config
from weblens.probe import probe_command

from .base import Channel


class XiaoyuzhouChannel(Channel):
    name = "xiaoyuzhou"
    description = "Xiaoyuzhou podcast transcription"
    backends = ["groq-whisper", "ffmpeg"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from weblens.utils.url import host_matches

        return host_matches(url, "xiaoyuzhoufm.com")

    def check(self, config=None):
        self.active_backend = None

        # Check ffmpeg — really execute it: a stale pip-installed ffmpeg shim
        # passes shutil.which() but cannot run
        probe = probe_command("ffmpeg", ["-version"], timeout=10, package="ffmpeg")
        if probe.status == "missing":
            return "off", (
                "Requires ffmpeg (audio transcoding and splitting). Install:\n"
                "  Ubuntu/Debian: apt install -y ffmpeg\n"
                "  macOS: brew install ffmpeg"
            )
        if not probe.ok:
            return "error", (
                "ffmpeg cannot be executed, reinstall: brew install ffmpeg (macOS) / apt install ffmpeg (Linux)"
            )

        # Check script exists
        script = os.path.expanduser("~/.weblens/tools/xiaoyuzhou/transcribe.sh")
        if not os.path.isfile(script):
            return "off", (
                "Transcription script is not installed. Run:\n"
                "  weblens install --env=auto --system --channels=xiaoyuzhou\n"
                "  or manually copy transcribe.sh to ~/.weblens/tools/xiaoyuzhou/"
            )

        # Check GROQ_API_KEY — prefer env var, fall back to WebLens config
        has_key = bool(os.environ.get("GROQ_API_KEY"))
        if not has_key:
            try:
                cfg = config if config is not None else Config()
                has_key = bool(cfg.get("groq_api_key"))
            except Exception:
                has_key = False
        if not has_key:
            return "warn", (
                "Requires a Groq API Key (free). Steps:\n"
                "  1. Sign up at https://console.groq.com\n"
                "  2. Run: weblens configure groq-key (hidden input)"
            )

        self.active_backend = "groq-whisper"
        return "ok", "Fully available (podcast download + Whisper transcription)"
