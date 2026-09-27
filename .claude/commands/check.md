---
description: Run WebLens tests, lint and type-check, then fix failures
---
Run the full WebLens quality gate and fix anything that fails. $ARGUMENTS

!`.venv/bin/pytest tests/ -q 2>&1 | tail -25`
!`.venv/bin/ruff check weblens tests 2>&1 | tail -25`
!`.venv/bin/mypy weblens 2>&1 | tail -25`

For each failure: find the root cause, fix it minimally, and re-run that check. Remember the version must match in pyproject.toml, weblens/__init__.py and tests/test_cli.py.
