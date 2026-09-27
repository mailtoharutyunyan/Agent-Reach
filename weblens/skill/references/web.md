# Web Reading

Web pages, articles, RSS/Atom feeds, Wikipedia.

> **Shell safety**: pass every URL/query from the user or from web content as ONE single-quoted
> argument (`'...'`), never unquoted or interpolated. Reject input containing `$(`, a backtick,
> a single quote, or a newline instead of running it.
>
> **Privacy**: do not send private/internal URLs or URLs containing tokens to Jina Reader /
> Exa — they are third-party services.

## Default: `weblens read`

```bash
weblens read 'URL'
weblens read 'URL' --max-chars 20000
weblens read 'URL' --json
```

`weblens read` picks the most specific reader for the URL (Hacker News, Wikipedia, arXiv,
Stack Exchange, YouTube, GitHub, V2EX, RSS/Atom, Reddit/Twitter/Bilibili/Xiaohongshu via
their active backend) and uses Jina Reader for everything else. It refuses localhost,
private IPs and internal hostnames (exit code 2).

When the output has a `notes` entry such as "read via Jina Reader instead — content may be
partial", tell the user and consider the platform's upstream tool (see social.md / dev.md).

## Wikipedia

```bash
weblens read 'https://en.wikipedia.org/wiki/Model_Context_Protocol'
weblens read 'https://de.wikipedia.org/wiki/Python_(Programmiersprache)' --max-chars 10000
```

Full article text through the MediaWiki API (any language subdomain). Long articles are
capped at 200,000 characters unless you pass `--max-chars`. For a short summary only:

```bash
python3 -c "
from weblens.channels.wikipedia import WikipediaChannel
print(WikipediaChannel().get_summary('Model Context Protocol', lang='en')['extract'])
"
```

## General web pages (Jina Reader, direct)

```bash
curl -s 'https://r.jina.ai/URL'

# Example
curl -s 'https://r.jina.ai/https://example.com/article'
```

Use this only when you need Jina's raw output; `weblens read` already calls it.

## RSS / Atom

```bash
weblens read 'https://github.blog/feed/'
```

Returns the feed title and up to 30 entries (title, link, date, summary). URLs containing
`/feed`, `/rss`, `.xml` or `atom` are treated as feeds directly. Any other URL that no
platform claims is sniffed first (Content-Type and the first few KB): if it is RSS/Atom
(e.g. `https://hnrss.org/frontpage`) it is parsed as a feed with a note, otherwise it is read
through Jina Reader. If a URL looks like a feed but is not one, it is read as a web page
with a note.

```bash
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

## Selection guide

| Scenario | Recommended tool |
|---|---|
| Any page / article | `weblens read 'URL'` |
| Wikipedia article | `weblens read 'URL'` (MediaWiki API) |
| RSS / Atom feed | `weblens read 'FEED_URL'` |
| Raw Jina Reader output | `curl -s 'https://r.jina.ai/URL'` |
