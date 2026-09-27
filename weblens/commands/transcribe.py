"""``weblens transcribe`` — transcribe a URL or local audio file."""

import sys


def _cmd_transcribe(args):
    """Transcribe a URL or local audio file via an explicitly selected provider."""
    from pathlib import Path

    from weblens.transcribe import TranscribeError, transcribe
    from weblens.utils.text import scrub_url_credentials

    try:
        text = transcribe(
            args.source,
            provider=args.provider,
            allow_provider_fallback=getattr(
                args,
                "allow_provider_fallback",
                False,
            ),
        )
    except TranscribeError as e:
        print(f"❌ {scrub_url_credentials(e)}")
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"✅ Transcript written to {args.output}")
    else:
        print(text)
