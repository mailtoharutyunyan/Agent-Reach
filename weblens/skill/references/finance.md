# Finance & Market Data

Xueqiu (Snowball) stock quotes, search, and trending content. Quotes may be delayed and do not constitute investment advice.

## Check status first

```bash
weblens doctor --json
```

When `xueqiu.active_backend` has a value, use that backend; a value of `null` only means Doctor did not complete
a live content check. Xueqiu requires a logged-in session or a minimal cookie; do not treat HTTP 400 as meaning the stock does not exist.

## OpenCLI (preferred when desktop Chrome already has a logged-in session)

```bash
# Verify the current login state
opencli xueqiu whoami -f yaml

# Stock search and real-time quotes
opencli xueqiu search "NVIDIA" -f yaml
opencli xueqiu stock NVDA -f yaml

# Trending content and trending stocks
opencli xueqiu hot -f yaml
opencli xueqiu hot-stock -f yaml

# List all read-only commands
opencli xueqiu --help
```

OpenCLI only reuses a browser session that already exists and that the user explicitly controls. Do not run
`opencli xueqiu login` automatically; if there is no existing login session, have the user log in to Chrome first, or explicitly import
the minimal cookie Xueqiu needs:

```bash
weblens configure --from-browser chrome --platform xueqiu
```

This configuration reads and saves only `xq_a_token`; it does not collect cookies for any other platform along the way.

## Acceptance and failure handling

- Success means a stock name, ticker, price, or a non-empty content list is returned; exit code 0 with empty fields does not count as success.
- HTTP 400 is usually a session/cookie problem, not a sign that the ticker does not exist.
- When `whoami` succeeds but `stock`/`hot` fails, report it as an adapter parsing or platform API issue; do not misdiagnose it as not logged in.
