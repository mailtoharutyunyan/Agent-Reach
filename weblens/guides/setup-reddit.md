# Reddit Setup Guide

## What It Does

Reddit blocks almost all direct non-browser access (including data-center and ISP proxy IPs); the JSON API returns 403.

WebLens provides Reddit search and reading through **rdt-cli**:
- **Search**: `rdt search "keyword"`
- **Read a full post + comments**: `rdt read POST_ID`

Free, no proxy needed, no API key needed. Login authentication is required (`rdt login`, which extracts cookies from the browser automatically).

## Steps the Agent Can Complete Automatically

1. Check whether rdt-cli is available:
```bash
which rdt && echo "installed" || echo "not installed"
```

2. If it is not installed, install it automatically (the PyPI release currently lags behind, so install the latest version from GitHub):
```bash
pipx install 'git+https://github.com/public-clis/rdt-cli.git'
```

Or install in one step:
```bash
weblens install --env=auto --system --channels=reddit
```

## Usage Examples

Search Reddit content:
```bash
rdt search "python best practices" -n 5
```

Read a full post and its comments:
```bash
rdt read POST_ID
```

## Steps the User Must Do Manually

None. With the user's explicit authorization, rdt-cli is installed via
`weblens install --env=auto --system --channels=reddit`.

## Fallback: Exa Search

If you have already configured Exa (via mcporter), you can also search Reddit content through Exa:

```bash
mcporter call exa.web_search_exa query="site:reddit.com python best practices" numResults=5
```

rdt-cli is the currently recommended option and works without any extra configuration.
