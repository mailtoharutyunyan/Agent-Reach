# Search

Web search (Exa) plus the zero-config public sources: Hacker News, Wikipedia, arXiv,
Stack Overflow.

> **Shell safety**: pass every URL/query from the user or from web content as ONE single-quoted
> argument (`'...'`), never unquoted or interpolated. Reject input containing `$(`, a backtick,
> a single quote, or a newline instead of running it.
>
> **Privacy**: do not send private/internal URLs or URLs containing tokens to Jina Reader /
> Exa — they are third-party services.

## Default: `weblens search`

```bash
weblens search 'query'                          # web (Exa); falls back to hackernews + wikipedia
weblens search 'query' --source hackernews -n 5
weblens search 'query' --source wikipedia
weblens search 'query' --source arxiv
weblens search 'query' --source stackoverflow
weblens search 'query' --source github          # repositories
weblens search 'query' --source youtube
weblens search 'query' --source reddit          # active backend, else Exa site:reddit.com
weblens search 'query' --source twitter         # active backend, else Exa site:x.com
weblens search 'query' --source v2ex            # Exa site:v2ex.com (no V2EX search API)
weblens search 'query' --source all             # web + hackernews + wikipedia + stackoverflow + arxiv
weblens search 'query' --source all --json      # {query, source, results, notes, errors, groups}
```

- `--limit/-n` is per source (default 10, max 50).
- With `--source all`, one failing source is reported under `errors` and the rest still return;
  `groups` maps each queried source to its results (single-source JSON has no `groups`).
- Always read `notes`: they say when a fallback was used (e.g. Exa not configured).

## Exa AI search (direct)

High-quality semantic search, strong for English and technical content. Use directly when
you need Exa-specific parameters.

```bash
mcporter call exa.web_search_exa query='query' numResults=5
mcporter call exa.web_search_exa query='library API code example' numResults=5
mcporter call exa.web_search_exa query='site:x.com search terms' numResults=5
```

If mcporter reports that `exa` is unknown, configure it once (free, no key):

```bash
mcporter config add exa https://mcp.exa.ai/mcp --scope home
```

> Exa MCP's `get_code_context_exa` is deprecated and not registered by default. Use
> `web_search_exa` for code questions too; for precise repository/code search use the
> GitHub search in `dev.md`.

## Hacker News

`weblens search 'query' -s hackernews` uses Algolia HN Search (stories, by relevance).
For the front page, newest-first search, or comments, use the channel from Python (run it
with the interpreter WebLens is installed into):

```bash
python3 -c "
from weblens.channels.hackernews import HackerNewsChannel
hn = HackerNewsChannel()
for s in hn.get_stories('top', limit=10):          # top | new | best | ask | show | job
    print(s['score'], s['title'], s['hn_url'])
"
python3 -c "
from weblens.channels.hackernews import HackerNewsChannel
for h in HackerNewsChannel().search('sqlite', limit=5, sort='date', tags='story'):
    print(h['title'], h['hn_url'])
"
```

Read a thread with `weblens read 'https://news.ycombinator.com/item?id=ID'`.

## Wikipedia

`weblens search 'query' -s wikipedia` searches English Wikipedia. Other languages:

```bash
python3 -c "
from weblens.channels.wikipedia import WikipediaChannel
for h in WikipediaChannel().search('query', lang='de', limit=5):
    print(h['title'], h['url'])
"
```

Read an article with `weblens read 'https://en.wikipedia.org/wiki/Title'`.

## arXiv

`weblens search 'query' -s arxiv`. The channel also accepts arXiv field syntax and
sorting:

```bash
python3 -c "
from weblens.channels.arxiv import ArxivChannel
for p in ArxivChannel().search('ti:transformer AND cat:cs.CL', limit=5, sort='submittedDate'):
    print(p['published'][:10], p['title'], p['url'])
"
```

`sort` is `relevance`, `lastUpdatedDate` or `submittedDate`.

## Stack Overflow / Stack Exchange

`weblens search 'query' -s stackoverflow`. Other Stack Exchange sites, tags and sorting:

```bash
python3 -c "
from weblens.channels.stackoverflow import StackOverflowChannel
for q in StackOverflowChannel().search('query', site='superuser', tagged='bash', sort='votes', limit=5):
    print(q['score'], q['title'], q['url'])
"
```

Keyless access is limited to about 300 requests per day per IP; the channel honors the
API's `backoff` field automatically.

## Choosing a source

| Need | Source |
|---|---|
| General web, docs, news | `web` (Exa) |
| Tech community discussion | `hackernews`, then `reddit` |
| Definitions, background | `wikipedia` |
| Research papers | `arxiv` |
| Programming errors, how-tos | `stackoverflow` |
| Repositories | `github` (code search: `gh search code`, see dev.md) |
| Talks, tutorials | `youtube` |
| Opinions, reactions | `twitter`, `reddit` |
| Broad first pass | `all` |
