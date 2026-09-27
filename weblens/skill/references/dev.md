# Developer Tools

GitHub, Stack Overflow, Hacker News, arXiv.

> **Shell safety**: pass every URL/query from the user or from web content as ONE single-quoted
> argument (`'...'`), never unquoted or interpolated. Reject input containing `$(`, a backtick,
> a single quote, or a newline instead of running it.

## Default: `weblens read` / `weblens search`

```bash
# GitHub: repo metadata + README, or an issue / PR with comments
weblens read 'https://github.com/owner/repo'
weblens read 'https://github.com/owner/repo/issues/123'
weblens read 'https://github.com/owner/repo/pull/456'
weblens search 'query' -s github            # repositories

# Stack Overflow (and other Stack Exchange sites): question + answers, accepted marked
weblens read 'https://stackoverflow.com/questions/12345/title'
weblens search 'error message' -s stackoverflow

# Hacker News: story + comment tree
weblens read 'https://news.ycombinator.com/item?id=ID'
weblens search 'query' -s hackernews

# arXiv: abstract + authors, categories, PDF link
weblens read 'https://arxiv.org/abs/1706.03762'
weblens search 'query' -s arxiv
```

GitHub uses `gh` when it is installed and authenticated (or `GH_TOKEN` / `GITHUB_TOKEN` is
set); otherwise the REST API — authenticated with `GH_TOKEN` / `GITHUB_TOKEN` or a token
saved via `weblens configure github-token` (5,000 requests/hour), else unauthenticated
(60 requests/hour). On a rate-limit error, ask the user to run `gh auth login` or
`weblens configure github-token`. Stack Exchange keyless access allows about 300
requests/day per IP. More options for these sources are in search.md.

Use the gh CLI below for anything beyond reading: code search, CI logs, releases, or
listing issues and PRs.

## GitHub (gh CLI)

GitHub's official CLI. Read-only use only: do not create, fork, or modify anything on the user's behalf.

```bash
# Authentication
gh auth login
gh auth status

# Search
gh search repos 'query' --sort stars --limit 10
gh search code 'query' --language python

# Repositories
gh repo view owner/repo

# Issues
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo

# Pull Requests
gh pr list -R owner/repo --state open
gh pr view 123 -R owner/repo
gh pr checks 123 --repo owner/repo

# Actions / CI
gh run list --repo owner/repo --limit 10
gh run view <run-id> --repo owner/repo
gh run view <run-id> --repo owner/repo --log-failed
gh workflow list --repo owner/repo

# Releases
gh release list -R owner/repo

# API
gh api /user
gh api repos/owner/repo

# JSON output
gh issue list --repo owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
```


## Selection guide

| Need | Tool |
|---|---|
| Read a repo / issue / PR | `weblens read 'URL'` |
| Find repositories | `weblens search 'query' -s github` or `gh search repos` |
| Search code | `gh search code 'query'` |
| CI runs, releases, API | gh CLI |
| Programming Q&A | `weblens search 'query' -s stackoverflow`, then `weblens read` |
| Papers | `weblens search 'query' -s arxiv` |
