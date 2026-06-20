import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
    ALERT_THRESHOLD = os.getenv("ALERT_THRESHOLD", "medium")
    CHUNK_DURATION_SECONDS = int(os.getenv("CHUNK_DURATION_SECONDS", "8"))
    SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
    SILENCE_THRESHOLD = int(os.getenv("SILENCE_THRESHOLD", "200"))
    DB_PATH = os.getenv("DB_PATH", "sessions.db")
