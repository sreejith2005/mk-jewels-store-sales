import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    ALERT_THRESHOLD = os.getenv("ALERT_THRESHOLD", "medium")
    CHUNK_DURATION_SECONDS = int(os.getenv("CHUNK_DURATION_SECONDS", "8"))
    SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
    DB_PATH = os.getenv("DB_PATH", "sessions.db")
