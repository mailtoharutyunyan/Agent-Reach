"""``weblens search <query>`` — one command to search one source or all."""

from __future__ import annotations

import json
import sys


def _cmd_search(args) -> None:
    from weblens.config import Config
    from weblens.unified.render import render_search
    from weblens.unified.search import search

    response = search(args.query, source=args.source, limit=args.limit,
                      config=Config(read_only=True))
    if args.json:
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_search(response))
