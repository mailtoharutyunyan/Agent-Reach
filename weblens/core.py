"""
WebLens — installer, doctor, and configuration tool.

WebLens installs and configures upstream platform tools (twitter-cli, yt-dlp,
mcporter, gh CLI, etc.), checks their health (``weblens doctor``), and offers
a unified ``read``/``search`` layer (``weblens.unified``) that routes each
request to the best available backend. The upstream tools remain available
for agents to call directly when they need more than read/search.

Usage:
    from weblens.doctor import check_all, format_report, print_report
    from weblens.config import Config

    config = Config()
    results = check_all(config)
    print_report(format_report(results))
"""


from weblens.config import Config


class WebLens:
    """Give your AI agent a clear view of the web.

    Health checks plus the unified ``read``/``search`` used by the CLI
    (``weblens read`` / ``weblens search``) and the MCP server.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config()

    def doctor(self) -> dict[str, dict]:
        """Check all channel availability."""
        from weblens.doctor import check_all
        return check_all(self.config)

    def doctor_report(self) -> str:
        """Get formatted health report."""
        from weblens.doctor import check_all, format_report
        return format_report(check_all(self.config))

    def read(self, url: str, max_chars: int | None = None):
        """Read *url* via the best channel adapter; returns a ReadResult."""
        from weblens.unified.read import read_url
        return read_url(url, max_chars=max_chars, config=self.config)

    def search(self, query: str, source: str = "web", limit: int = 10):
        """Search one source (or ``"all"``); returns a SearchResponse."""
        from weblens.unified.search import search
        return search(query, source=source, limit=limit, config=self.config)
