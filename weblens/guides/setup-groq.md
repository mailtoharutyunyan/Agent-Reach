# Groq Whisper Setup Guide

## What It Does
When a YouTube/Bilibili video has no subtitles, Groq's Whisper API is used for speech-to-text. Groq offers a free tier.

## Steps the Agent Can Complete Automatically

1. Check whether it is already configured:
```bash
weblens doctor | grep -i "groq\|whisper"
```

2. If the user has provided a key, write it to the config:
```python
from weblens.config import Config
c = Config()
c.set("groq_api_key", "USER_PROVIDED_KEY")
```

3. Test (optional):
```bash
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer USER_PROVIDED_KEY" \
  -o /dev/null -w "%{http_code}"
```
A 200 response = working

## Steps the User Must Do Manually

Tell the user:

> Video speech-to-text needs a Groq API key (free).
>
> Steps:
> 1. Open https://console.groq.com
> 2. Sign up with a Google account or email
> 3. Click "API Keys" in the left sidebar
> 4. Click "Create API Key"
> 5. Copy the generated key and send it to me
>
> Groq's free tier is more than enough for everyday use.

## What the Agent Does After Receiving the Key

1. Write it to the config: `config.set("groq_api_key", key)`
2. Test that the API works
3. Report back: "✅ Speech-to-text is enabled! Now, when a video has no subtitles, I can still extract its content for you."
