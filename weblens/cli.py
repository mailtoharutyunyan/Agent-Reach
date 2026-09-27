"""
WebLens CLI — installer, doctor, and configuration tool.

Usage:
    weblens read <url> [--json] [--max-chars N]
    weblens search <query> [--source S] [--limit N] [--json]
    weblens install --env=auto
    weblens doctor
    weblens configure twitter-cookies
    weblens setup
"""

import argparse
import os
import sys

from weblens import __version__
from weblens.commands.configure import _cmd_configure
from weblens.commands.doctor import _cmd_doctor
from weblens.commands.format import _cmd_format
from weblens.commands.install import _cmd_install
from weblens.commands.read import _cmd_read
from weblens.commands.search import _cmd_search
from weblens.commands.setup import _cmd_setup
from weblens.commands.skill import _cmd_skill
from weblens.commands.transcribe import _cmd_transcribe
from weblens.commands.uninstall import _cmd_uninstall
from weblens.commands.update import _cmd_check_update, _cmd_watch


def _ensure_utf8_console():
    """Best-effort Windows console UTF-8 setup for CLI runtime only."""
    if sys.platform != "win32":
        return
    # Avoid interfering with pytest/captured streams.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        # Do not crash CLI just because encoding patch failed.
        pass


def _configure_logging(verbose: bool = False):
    """Suppress loguru output unless --verbose (or --debug) is set."""
    from loguru import logger
    logger.remove()  # Remove default stderr handler
    if verbose:
        logger.add(sys.stderr, level="INFO")


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}") from None
    if number <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}")
    return number


def _add_global_flags(parser: argparse.ArgumentParser, *, default) -> None:
    parser.add_argument("-v", "--verbose", action="store_true", default=default,
                        help="Show debug logs")
    parser.add_argument("--debug", action="store_true", default=default,
                        help="Show debug logs and full tracebacks on errors")


def _run_command(handler, *handler_args, debug: bool = False) -> None:
    """Run a command; map failures to one-line errors and exit codes.

    WebLensError carries its own exit code (1 runtime, 2 usage). Anything
    else is exit 1 with a one-line message; ``--debug`` shows the traceback.
    """
    from weblens.unified.errors import WebLensError, describe_exception

    try:
        handler(*handler_args)
        sys.stdout.flush()
    except BrokenPipeError:
        # Output piped into e.g. `head`: stop quietly like standard CLIs.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        sys.exit(0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
    except WebLensError as exc:
        if debug:
            raise
        print(f"error: {exc.one_line()}", file=sys.stderr)
        sys.exit(exc.exit_code)
    except Exception as exc:
        if debug:
            raise
        err = describe_exception(exc, getattr(handler, "__name__", "command").removeprefix("_cmd_"))
        print(f"error: {err.one_line()}", file=sys.stderr)
        sys.exit(1)


def main():
    _ensure_utf8_console()

    parser = argparse.ArgumentParser(
        prog="weblens",
        description="Give your AI agent a clear view of the web",
    )
    _add_global_flags(parser, default=False)
    parser.add_argument("--version", action="version", version=f"WebLens v{__version__}")
    # The same flags on every subcommand, so `weblens read URL --debug` works like
    # `weblens --debug read URL`. SUPPRESS keeps a subcommand that was not given the
    # flag from resetting a value set before the subcommand name.
    global_flags = argparse.ArgumentParser(add_help=False)
    _add_global_flags(global_flags, default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", help="Available commands")

    def add_command(name: str, **kwargs) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[global_flags], **kwargs)

    # ── read ──
    p_read = add_command(
        "read",
        help="Read any URL as clean text (auto-routes: HN, Wikipedia, arXiv, "
             "Stack Overflow, YouTube, GitHub, V2EX, RSS, ... then any web page)",
    )
    p_read.add_argument("url", help="URL to read")
    p_read.add_argument("--json", action="store_true", help="Structured JSON output")
    p_read.add_argument("--max-chars", type=_positive_int, default=None, metavar="N",
                        help="Truncate the body to N characters")

    # ── search ──
    from weblens.unified.search import SOURCES as _SEARCH_SOURCES

    p_search = add_command("search", help="Search the web or a specific source")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--source", "-s", default="web", choices=_SEARCH_SOURCES,
                          help="Where to search (default: web; 'all' = web + hackernews + "
                               "wikipedia + stackoverflow + arxiv in parallel)")
    p_search.add_argument("--limit", "-n", type=_positive_int, default=10, metavar="N",
                          help="Max results per source (default 10, max 50)")
    p_search.add_argument("--json", action="store_true", help="Structured JSON output")

    # ── setup ──
    add_command("setup", help="Interactive configuration wizard")

    # ── install ──
    p_install = add_command("install", help="One-shot installer with flags")
    p_install.add_argument("--env", choices=["local", "server", "auto"], default="auto",
                           help="Environment: local, server, or auto-detect")
    p_install.add_argument("--proxy", default="",
                           help="Network proxy saved for `weblens read`/`search` (and for agents to "
                                "export as HTTP(S)_PROXY) in restricted networks (http://user:pass@ip:port)")
    install_mode = p_install.add_mutually_exclusive_group()
    install_mode.add_argument(
        "--system",
        action="store_true",
        help="Explicitly allow system dependency, global tool, config, and skill installation",
    )
    install_mode.add_argument(
        "--safe",
        action="store_true",
        help="Safe check-only mode (default; retained for compatibility)",
    )
    p_install.add_argument("--dry-run", action="store_true",
                           help="Show what would be done without making any changes")
    p_install.add_argument("--channels", default="",
                           help="Comma-separated optional channels to install "
                                "(twitter,xiaoyuzhou,xueqiu,xiaohongshu,"
                                "reddit,facebook,instagram,bilibili,linkedin,boss,"
                                "opencli,all)")

    # ── configure ──
    p_conf = add_command("configure", help="Set a config value or auto-extract from browser")
    p_conf.add_argument("key", nargs="?", default=None,
                        choices=["proxy", "github-token", "groq-key", "openai-key",
                                 "twitter-cookies", "youtube-cookies",
                                 "xhs-cookies"],
                        help="What to configure (omit if using --from-browser)")
    p_conf.add_argument("value", nargs="*", help="The value(s) to set")
    p_conf.add_argument(
        "--stdin",
        dest="read_stdin",
        action="store_true",
        help="Read the value from stdin instead of exposing it in process arguments",
    )
    p_conf.add_argument("--from-browser", metavar="BROWSER",
                        choices=["chrome", "firefox", "edge", "brave", "opera"],
                        help="Extract cookies for one explicitly selected platform")
    p_conf.add_argument(
        "--platform",
        choices=["twitter", "xiaohongshu", "bilibili", "xueqiu"],
        help="Platform to import (required with --from-browser)",
    )
    p_conf.add_argument(
        "--profile",
        help="Exact browser profile; a missing profile fails instead of falling back",
    )
    p_conf.add_argument(
        "--sync-legacy-twitter",
        action="store_true",
        help="With twitter-cookies, also write legacy xfetch/bird credential files",
    )

    # ── doctor ──
    p_doctor = add_command("doctor", help="Check platform availability")
    p_doctor.add_argument("--json", action="store_true",
                          help="Output machine-readable JSON instead of the text report")

    # ── uninstall ──
    p_uninstall = add_command("uninstall", help="Remove all WebLens config, tokens, and skill files")
    p_uninstall.add_argument("--dry-run", action="store_true",
                             help="Show what would be removed without making any changes")
    p_uninstall.add_argument("--keep-config", action="store_true",
                             help="Remove skill files only, keep ~/.weblens/ config and tokens")

    # ── skill ──
    p_skill = add_command("skill", help="Manage agent skill registration")
    p_skill_group = p_skill.add_mutually_exclusive_group(required=True)
    p_skill_group.add_argument("--install", action="store_true",
                               help="Install SKILL.md to agent skill directories")
    p_skill_group.add_argument("--uninstall", action="store_true",
                               help="Remove SKILL.md from agent skill directories")

    # ── format ──
    p_format = add_command("format", help="Clean and format platform API output")
    p_format.add_argument("platform", choices=["xhs"], help="Platform to format (xhs)")

    # ── check-update ──
    # ── transcribe ──
    p_tr = add_command("transcribe", help="Transcribe a URL or local audio file (Whisper via Groq/OpenAI)")
    p_tr.add_argument("source", help="Audio/video URL or local file path")
    p_tr.add_argument("--provider", choices=["auto", "groq", "openai"], default="auto",
                      help="Transcription provider (default: first configured provider)")
    p_tr.add_argument(
        "--allow-provider-fallback",
        action="store_true",
        help=(
            "With --provider auto, allow sending audio to the next "
            "configured provider after a failure"
        ),
    )
    p_tr.add_argument("-o", "--output", default=None,
                      help="Write transcript to a file instead of stdout")

    add_command("check-update", help="Check for new versions and changes")

    # ── watch ──
    add_command("watch", help="Quick health check + update check (for scheduled tasks)")

    # ── version ──
    add_command("version", help="Show version")

    args = parser.parse_args()

    if args.command == "configure" and args.from_browser:
        if args.read_stdin:
            p_conf.error("--stdin cannot be combined with --from-browser")
        if not args.platform:
            p_conf.error("--platform is required with --from-browser")
        manual_keys = {
            "twitter": "twitter-cookies",
            "xiaohongshu": "xhs-cookies",
        }
        if args.platform in manual_keys:
            p_conf.error(
                f"{args.platform} requires Cookie-Editor export; use "
                f"`weblens configure {manual_keys[args.platform]} ...`"
            )
        if args.profile and args.from_browser not in {"chrome", "edge", "brave"}:
            p_conf.error(
                "--profile is supported only for Chrome/Edge/Brave"
            )
        if args.sync_legacy_twitter:
            p_conf.error("--sync-legacy-twitter is only valid with twitter-cookies")
    elif args.command == "configure":
        if args.read_stdin and args.value:
            p_conf.error("--stdin cannot be combined with a positional value")
        if args.read_stdin and not args.key:
            p_conf.error("--stdin requires a configure key")
        if args.profile or args.platform:
            p_conf.error("--platform/--profile require --from-browser")
        if args.sync_legacy_twitter and args.key != "twitter-cookies":
            p_conf.error("--sync-legacy-twitter is only valid with twitter-cookies")

    if (
        args.command == "transcribe"
        and args.allow_provider_fallback
        and args.provider != "auto"
    ):
        p_tr.error("--allow-provider-fallback requires --provider auto")

    if args.command == "search" and args.limit > 50:
        p_search.error("--limit must be at most 50")

    # Suppress loguru noise unless --verbose / --debug
    debug = getattr(args, "debug", False)
    _configure_logging(getattr(args, "verbose", False) or debug)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "version":
        print(f"WebLens v{__version__}")
        sys.exit(0)

    if args.command == "read":
        _run_command(_cmd_read, args, debug=debug)
    elif args.command == "search":
        _run_command(_cmd_search, args, debug=debug)
    elif args.command == "doctor":
        _cmd_doctor(args)
    elif args.command == "check-update":
        _cmd_check_update()
    elif args.command == "watch":
        _cmd_watch()
    elif args.command == "setup":
        _cmd_setup()
    elif args.command == "install":
        _cmd_install(args)
    elif args.command == "configure":
        _cmd_configure(args)
    elif args.command == "uninstall":
        _cmd_uninstall(args)
    elif args.command == "skill":
        _cmd_skill(args)
    elif args.command == "format":
        _cmd_format(args)
    elif args.command == "transcribe":
        _cmd_transcribe(args)


if __name__ == "__main__":
    main()
