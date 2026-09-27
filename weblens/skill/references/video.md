# Video / Podcasts

Subtitles and transcripts for YouTube, Bilibili, and Xiaoyuzhou podcasts.

> **Shell safety**: pass every URL/query from the user or from web content as ONE single-quoted
> argument (`'...'`), never unquoted or interpolated. Reject input containing `$(`, a backtick,
> a single quote, or a newline instead of running it.

## YouTube

### Default: `weblens read` / `weblens search`

```bash
weblens read 'https://www.youtube.com/watch?v=VIDEO_ID'     # metadata + description + transcript
weblens read 'https://youtu.be/VIDEO_ID' --max-chars 30000
weblens search 'query' -s youtube -n 5
```

`weblens read` uses yt-dlp: title, channel, date, duration, views, then the description
and the transcript as plain text (manual subtitles preferred over auto-generated). If
YouTube rate-limits the subtitle download (HTTP 429), it retries once more slowly; if that
also fails it returns the metadata with a note "subtitles skipped". In that case, or when
the video has no subtitles, use the retry chain below.

### Get video metadata (yt-dlp direct)

```bash
yt-dlp --dump-json 'URL'
```

### Download subtitles

```bash
# Download subtitles (without downloading the video)
yt-dlp --write-sub --write-auto-sub --sub-lang 'en,zh-Hans,zh' --skip-download -o '/tmp/%(id)s' 'URL'

# Then read the .vtt file
cat /tmp/VIDEO_ID.*.vtt
```

### Get comments

```bash
# Extract comments (best-effort, completeness not guaranteed)
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args 'youtube:max_comments=20' \
  -o '/tmp/%(id)s' 'URL'
# Comments are in the comments field of .info.json
```

### Search videos

```bash
yt-dlp --dump-json 'ytsearch5:query'
```

> **Subtitle note**: manually uploaded subtitles extract reliably; auto-generated subtitles may contain duplicated lines and need post-processing.
> **Comment note**: `--write-comments` is based on web scraping (not the YouTube Data API), so some comments may be missing.

### Retry chain when subtitles fail (run in order, stop as soon as you get real content)

`doctor` only confirms that yt-dlp itself and the JS runtime can execute; it doesn't request any specific video. So
`active_backend: yt-dlp` does not mean the target video's subtitles have been verified live.

1. First `weblens read 'URL'`, or the `yt-dlp --write-sub --write-auto-sub` command above.
2. If you hit a "sign in / not a bot" check, ask the user to run `weblens configure youtube-cookies <browser>`
   (brave, chrome, chromium, edge, firefox, opera, safari, vivaldi, whale) while logged in to YouTube in that browser;
   `weblens read`/`search` then pass `--cookies-from-browser` to yt-dlp. Otherwise, if the subtitle response is empty
   or no subtitle file is produced and OpenCLI is connected: `opencli youtube transcript 'URL' -f yaml`.
3. If OpenCLI returns `Caption URL returned empty response`, retry at most 3 times; this is an intermittent failure of
   a subtitle URL with an expiry time, and an empty response must not be taken to mean "the video has no subtitles".
4. If it still fails or the video genuinely has no subtitles: `weblens transcribe 'URL'` downloads the audio and transcribes it.

The success criterion is actually getting non-empty subtitle/transcript content, not the command's exit code or `doctor`'s version probe.

### No-subtitle fallback: Whisper audio transcription

```bash
# Fallback when a video has no subtitles: download the audio and transcribe it with Whisper (a free Groq key is enough)
weblens transcribe 'https://www.youtube.com/watch?v=VIDEO_ID'
weblens transcribe ./local_audio.mp3 -o /tmp/transcript.txt
```

> `weblens transcribe` only accepts public http(s) URLs or local audio files. When searching with `ytsearch5:`, first pick a specific video URL from the yt-dlp results, then transcribe it.
> A key must be configured first: `weblens configure groq-key` (hidden input; free, console.groq.com)
> or `weblens configure openai-key`. The default auto mode only uses the first configured provider
> (Groq preferred, otherwise OpenAI) and stops on failure; it never automatically sends the audio to the other provider.
> `--allow-provider-fallback` explicitly authorizes cross-provider fallback; the same audio content may be processed by both Groq and
> OpenAI and may incur OpenAI charges, so only use it after confirming the content can be shared with both.

## Bilibili (China pack; bili-cli primarily, OpenCLI for subtitles)

`weblens read 'https://www.bilibili.com/video/BVxxx'` runs `bili video BVxxx` when bili-cli is the
active backend; otherwise it falls back to Jina Reader with a note. Use the commands below for
search, rankings and subtitles.

> ⚠️ **Don't use yt-dlp to read Bilibili**: Bilibili's anti-abuse system now blocks yt-dlp across the board with 412 (tested with the latest version; direct connection / proxy / with cookies all fail). Use yt-dlp only for YouTube.

### Video details / search / trending / rankings (bili-cli, read-only, no login needed)

```bash
# Video details (title / uploader / duration / play and engagement stats / subtitle availability)
bili video BVxxx

# Search videos
bili search 'query' --type video -n 5

# Trending videos / rankings
bili hot -n 10
bili rank -n 10

# Download audio and split into ASR-ready WAV (when there are no subtitles, transcribe with weblens transcribe)
bili audio BVxxx
```

### Subtitles (OpenCLI, requires desktop Chrome)

```bash
# Subtitles line by line with timestamps
opencli bilibili subtitle BVxxx

# OpenCLI can also search / read video metadata (alternative)
opencli bilibili search 'query' -f yaml
opencli bilibili video BVxxx -f yaml
```

### Zero-config fallback: direct search API

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" 'https://www.bilibili.com/'
curl -s -b /tmp/bili_ck.txt -A "$UA" -e 'https://www.bilibili.com/' \
  'https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1'
```

> **Install bili-cli**: `pipx install 'bilibili-cli==0.6.2'` (the version `weblens install --channels=bilibili` pins; upstream stopped updating as of 2026-03 but tests healthy; read-only use needs no login, and `bili login` via QR code unlocks personal features such as feeds/favorites).

## Xiaoyuzhou Podcast (China pack)

### Transcribe a single episode (optional --polish for better punctuation)

```bash
# Outputs a Markdown file to /tmp/. --polish has Llama 3.3 70B add Chinese punctuation + sensible paragraph breaks to the transcript
~/.weblens/tools/xiaoyuzhou/transcribe.sh --polish 'https://www.xiaoyuzhoufm.com/episode/EPISODE_ID'
```

> The transcription prompt already asks Whisper to output Chinese punctuation; if punctuation is still unsatisfactory, add `--polish` to use the free Llama 3.3 70B on Groq to add punctuation + sensible paragraph breaks (about ~7 extra seconds for a 9-minute podcast). Each transcription makes one extra LLM call, so use it as needed.

### Prerequisites

1. **ffmpeg**: `brew install ffmpeg`
2. **Groq API Key** (free): https://console.groq.com/keys
3. **Configure the key**: `weblens configure groq-key` (hidden input)
4. **First run**: `weblens install --env=auto --system --channels=xiaoyuzhou` (requires the user's explicit authorization)

### Check status

```bash
weblens doctor
```

> Output Markdown files are saved to `/tmp/` by default.

## Selection guide

| Scenario | Recommended tool |
|-----|---------|
| YouTube video | `weblens read 'URL'` |
| YouTube subtitles | weblens read / yt-dlp; on failure OpenCLI (up to 3 times) → weblens transcribe |
| YouTube search | `weblens search 'query' -s youtube` |
| Bilibili video details / search | bili-cli |
| Bilibili subtitles | opencli bilibili subtitle |
| Podcast transcription | Xiaoyuzhou transcribe.sh |
| Audio/video without subtitles | weblens transcribe (for Bilibili audio, run `bili audio` first) |
