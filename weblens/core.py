# -*- coding: utf-8 -*-
"""
WebLens — installer, doctor, and configuration tool.

WebLens helps AI agents install and configure upstream platform tools
(twitter-cli, yt-dlp, mcporter, gh CLI, etc.). After installation, agents
call the upstream tools directly — no wrapper layer needed.

Usage:
    from weblens.doctor import check_all, format_report, print_report
    from weblens.config import Config

    config = Config()
    results = check_all(config)
    print_report(format_report(results))
"""

from typing import Dict, Optional

from weblens.config import Config


class WebLens:
    """Give your AI agent a clear view of the web.

    This class provides health-check functionality.
    For reading/searching, use the upstream tools directly
    (see SKILL.md for commands).
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    def doctor(self) -> Dict[str, dict]:
        """Check all channel availability."""
        from weblens.doctor import check_all
        return check_all(self.config)

    def doctor_report(self) -> str:
        """Get formatted health report."""
        from weblens.doctor import check_all, format_report
        return format_report(check_all(self.config))
