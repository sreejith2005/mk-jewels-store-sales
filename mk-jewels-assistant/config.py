import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)


def _get_pipeline_mode() -> str:
    pipeline_mode = os.getenv("PIPELINE_MODE", "demo")
    if pipeline_mode not in {"demo", "production"}:
        print(
            f"Warning: Invalid PIPELINE_MODE={pipeline_mode!r}. Falling back to 'demo'.",
            file=sys.stderr,
        )
        return "demo"
    return pipeline_mode


class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
    PIPELINE_MODE = _get_pipeline_mode()
    ALERT_THRESHOLD = os.getenv("ALERT_THRESHOLD", "medium")
    CHUNK_DURATION_SECONDS = int(os.getenv("CHUNK_DURATION_SECONDS", "8"))
    SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
    SILENCE_THRESHOLD = int(os.getenv("SILENCE_THRESHOLD", "200"))
    DB_PATH = os.getenv("DB_PATH", "sessions.db")

    @classmethod
    def validate(cls) -> None:
        required_keys = [
            "GEMINI_API_KEY",
            "DISCORD_BOT_TOKEN",
            "DISCORD_CHANNEL_ID",
        ]
        missing_keys = [
            key
            for key in required_keys
            if not isinstance(getattr(cls, key), str) or not getattr(cls, key).strip()
        ]

        if missing_keys:
            print(
                "Startup error: missing required environment keys: "
                + ", ".join(missing_keys),
                file=sys.stderr,
            )
            raise SystemExit(1)
