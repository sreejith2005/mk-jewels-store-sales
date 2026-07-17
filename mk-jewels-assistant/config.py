import os
import sys
from pathlib import Path

import requests
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
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    PIPELINE_MODE = _get_pipeline_mode()
    DASHBOARD_AUTH_PASS = os.getenv("DASHBOARD_AUTH_PASS", "5500")
    CHUNK_DURATION_SECONDS = int(os.getenv("CHUNK_DURATION_SECONDS", "8"))
    OVERLAP_SECONDS = float(os.getenv("OVERLAP_SECONDS", "0.75"))
    SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
    DEVICE = os.getenv("DEVICE", "cuda")
    INDIC_CONFORMER_LANGUAGE = os.getenv("INDIC_CONFORMER_LANGUAGE", "hi")
    DEBUG_SAVE_REPETITION_AUDIO = (
        os.getenv("DEBUG_SAVE_REPETITION_AUDIO", "false").lower() == "true"
    )
    DEBUG_REPETITION_AUDIO_DIR = os.getenv(
        "DEBUG_REPETITION_AUDIO_DIR",
        "/tmp/mkjewels_debug_audio",
    )
    TRANSLATE_TO_ENGLISH = os.getenv("TRANSLATE_TO_ENGLISH", "true")
    TRANSLATE_SERVICE_URL = os.getenv(
        "TRANSLATE_SERVICE_URL",
        "http://127.0.0.1:8811",
    )
    USE_LOCAL_DISPLAY_NORMALIZATION = (
        os.getenv("USE_LOCAL_DISPLAY_NORMALIZATION", "true").lower() == "true"
    )
    SILENCE_THRESHOLD = int(os.getenv("SILENCE_THRESHOLD", "200"))
    DIARIZATION_ENABLED = os.getenv("DIARIZATION_ENABLED", "false").lower() == "true"
    HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")
    MIN_SPEAKER_SEGMENT_SECONDS = float(
        os.getenv("MIN_SPEAKER_SEGMENT_SECONDS", "1.0")
    )
    DB_PATH = os.getenv("DB_PATH", "sessions.db")
    POSTGRES_URL = os.getenv("POSTGRES_URL", "")
    KNOWLEDGE_BASE_PATH = os.getenv("KNOWLEDGE_BASE_PATH", "knowledge/")
    REPORT_HOUR = int(os.getenv("REPORT_HOUR", "21"))
    WS_HOST = os.getenv("WS_HOST", "0.0.0.0")
    WS_PORT = int(os.getenv("WS_PORT", "8765"))
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )

    @classmethod
    def validate(cls):
        missing = []
        if not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        if missing:
            import sys
            print(f"ERROR: Missing required config: {', '.join(missing)}")
            sys.exit(1)

    @classmethod
    def validate_pipeline(cls):
        import logging

        logger = logging.getLogger(__name__)
        if cls.PIPELINE_MODE == "demo":
            if not cls.GEMINI_API_KEY:
                logger.warning(
                    "PIPELINE_MODE=demo but GEMINI_API_KEY is not set."
                )
            return

        if cls.PIPELINE_MODE == "production":
            try:
                requests.get(f"{cls.OLLAMA_HOST.rstrip('/')}/api/tags", timeout=2)
            except requests.RequestException as error:
                logger.warning(
                    "PIPELINE_MODE=production but Ollama is unreachable at %s: %s",
                    cls.OLLAMA_HOST,
                    error,
                )
