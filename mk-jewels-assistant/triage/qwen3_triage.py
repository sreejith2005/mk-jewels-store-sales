import json
import os
import sys
from typing import Any

import requests

# Add parent directory to sys.path to allow running this file directly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from core.exceptions import TriageError
from core.logger import get_logger
from core.schemas import validate_event


logger = get_logger(__name__)

MODEL_NAME = "qwen3:8b"

SYSTEM_PROMPT = (
    "You are an AI assistant monitoring sales conversations at a jewelry store in India. "
    "The salesperson may speak in English, Hindi, Marathi, or a mix of all three. "
    "You will receive an already-transcribed conversation. Your job is to classify it. "
    "Jewelry-specific terms you will encounter include: hallmark, BIS, HUID, carat, "
    "VVS, solitaire, kundan, polki, making charges, exchange scheme, IGI, GIA, "
    "solitaire, rhodium. Preserve these terms exactly as spoken."
)

USER_PROMPT_TEMPLATE = (
    "Salesperson: {salesperson_name}\n"
    "Transcript:\n{transcript}\n\n"
    "Classify this jewelry sales conversation. Return ONLY a valid JSON object with "
    "exactly these fields and no other text or markdown fences: "
    "objection_detected (bool), price_concern (bool), certification_question (bool), "
    "upsell_miss (bool), knowledge_gap (bool), intent_signal (bool), "
    "alert_priority (string, one of: none / low / medium / high), "
    "reasoning (string, max 20 words)."
)


def _parse_json_response(text: str) -> dict[str, Any]:
    raw_text = text
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as error:
        raise TriageError(f"Invalid JSON from Qwen3: {raw_text[:200]}") from error


def _validate_triage_result(result: dict[str, Any]) -> dict:
    try:
        return validate_event(result)
    except ValueError as error:
        raise TriageError(str(error)) from error


def _empty_event() -> dict:
    return _validate_triage_result(
        {
            "transcript": "",
            "objection_detected": False,
            "price_concern": False,
            "certification_question": False,
            "upsell_miss": False,
            "knowledge_gap": False,
            "intent_signal": False,
            "alert_priority": "none",
            "reasoning": "empty transcript",
        }
    )


def triage(transcript: str, salesperson_name: str) -> dict:
    """Classify an English-language transcript with Qwen3 via Ollama."""
    transcript_text = transcript.strip()
    if not transcript_text:
        logger.info("Skipping Qwen3 triage for empty transcript.")
        return _empty_event()

    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    salesperson_name=salesperson_name,
                    transcript=transcript,
                ),
            },
        ],
    }

    try:
        response = requests.post(
            f"{Config.OLLAMA_HOST}/api/chat",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        logger.error("Ollama request failed: %s", error)
        raise TriageError(f"Ollama unreachable: {error}") from error

    response_json = response.json()
    raw_text = response_json["message"]["content"]
    result = _parse_json_response(raw_text)
    result["transcript"] = transcript
    return _validate_triage_result(result)


if __name__ == "__main__":
    sample_transcript = "Customer boli yeh necklace bohot mehnga hai, discount milega?"
    triage_result = triage(sample_transcript, "Test Salesperson")
    logger.info(json.dumps(triage_result, indent=2, ensure_ascii=False))
