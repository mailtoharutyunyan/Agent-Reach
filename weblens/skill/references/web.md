# Web Reading

General web pages, RSS.

## General web pages (Jina Reader)

```bash
# Read the content of any web page
curl -s "https://r.jina.ai/URL"

# Example
curl -s "https://r.jina.ai/https://example.com/article"
```

**Use case**: Most web pages can be read directly with Jina Reader.

## Web Reader (MCP)

```bash
# Read web page content (Markdown format)
mcporter call web-reader.webReader url="https://example.com"

# Keep images
mcporter call web-reader.webReader url="https://example.com" retain_images=true

# Plain-text format
mcporter call web-reader.webReader url="https://example.com" return_format="text"
```

**Use case**: Use when you need finer control over the output format.

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**Use case**: Following RSS feeds for blogs, news sources, podcasts, and more.

## Selection guide

| Scenario | Recommended tool |
|-----|---------|
| General web pages | Jina Reader (`curl r.jina.ai`) |
| Need images/format control | web-reader MCP |
| RSS feeds | feedparser |
