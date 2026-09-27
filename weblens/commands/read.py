"""``weblens read <url>`` — one command to read any URL."""

from __future__ import annotations

import json
import sys


def _cmd_read(args) -> None:
    from weblens.config import Config
    from weblens.unified.read import read_url
    from weblens.unified.render import render_read

    result = read_url(args.url, max_chars=args.max_chars, config=Config(read_only=True))
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_read(result))
