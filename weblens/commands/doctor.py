"""``weblens doctor`` — report platform availability."""

import json


def _cmd_doctor(args=None):
    from weblens.config import Config
    from weblens.doctor import check_all, format_report, print_report
    config = Config(read_only=True)
    results = check_all(config)

    if args is not None and getattr(args, "json", False):
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print_report(format_report(results))
