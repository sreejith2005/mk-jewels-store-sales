import json
import os
import sys
from pathlib import Path
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
MAX_FACT_SUMMARY_ITEMS = 5


def _knowledge_base_dir() -> Path:
    configured_path = Path(Config.KNOWLEDGE_BASE_PATH)
    if configured_path.is_absolute():
        return configured_path
    return Path(__file__).resolve().parent.parent / configured_path


def _load_kb_json(filename: str) -> dict[str, Any]:
    path = _knowledge_base_dir() / filename
    if not path.exists():
        logger.warning("Knowledge base file not found: %s", path)
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Failed to load knowledge base file %s: %s", path, error)
        return {}

    if not isinstance(data, dict):
        logger.warning("Knowledge base file %s did not contain a JSON object.", path)
        return {}
    return data


OBJECTION_RULES = _load_kb_json("objection_rules.json")
PRODUCT_FACTS = _load_kb_json("product_facts.json")

SYSTEM_PROMPT = (
    "You are an AI assistant monitoring sales conversations at a jewelry store in India. "
    "The salesperson may speak in English, Hindi, Marathi, or a mix of all three. "
    "You will receive an already-transcribed conversation. Your job is to classify it. "
    "Jewelry-specific terms you will encounter include: hallmark, BIS, HUID, carat, "
    "VVS, solitaire, kundan, polki, making charges, exchange scheme, IGI, GIA, "
    "solitaire, rhodium. Preserve these terms exactly as spoken."
)

CRITICAL_ALERT_CALIBRATION_RULES = (
    "CRITICAL ALERT CALIBRATION RULES - read carefully before classifying:\n\n"
    "1. Only fire HIGH alert if the salesperson said something factually wrong, "
    "used a forbidden response, or directly contradicted a known policy. A "
    "salesperson adapting their style or taking a different approach than the "
    "script does NOT warrant HIGH alert.\n\n"
    "2. Only fire MEDIUM alert if the salesperson clearly missed a scripted "
    "opportunity AND the customer showed a signal that the script specifically "
    "addresses. Do not fire MEDIUM for general conversation drift.\n\n"
    "3. If the salesperson appears to be building rapport, listening actively, "
    "or adapting to the customer - even if off-script - classify alert_priority "
    "as \"none\".\n\n"
    "4. Closing a deal in a non-scripted way is a POSITIVE outcome. Do not "
    "penalise it.\n\n"
    "5. When in doubt, classify lower. A false alarm is more damaging to "
    "manager trust than a missed alert.\n\n"
    "6. The reasoning field must state specifically what the salesperson said "
    "vs what the script says, in max 20 words. Do not write vague reasons like "
    "\"did not follow script\"."
)

USER_PROMPT_TEMPLATE = (
    "Salesperson: {salesperson_name}\n"
    "Transcript:\n{transcript}\n\n"
    "--- MK JEWELS KNOWLEDGE BASE (relevant to this conversation) ---\n"
    "{kb_context}\n"
    "--- END KNOWLEDGE BASE ---\n\n"
    "{calibration_rules}\n\n"
    "Classify this jewelry sales conversation. Return ONLY a valid JSON object with "
    "exactly these fields and no other text or markdown fences: "
    "objection_detected (bool), price_concern (bool), certification_question (bool), "
    "upsell_miss (bool), knowledge_gap (bool), intent_signal (bool), "
    "alert_priority (string, one of: none / low / medium / high), "
    "reasoning (string, max 20 words)."
)


def _normalise_text(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


def _rule_matches(transcript_text: str, rule: dict[str, Any]) -> bool:
    signals = rule.get("customer_signals", [])
    if not isinstance(signals, list):
        return False

    for signal in signals:
        if not isinstance(signal, str):
            continue
        if _normalise_text(signal) in transcript_text:
            return True
    return False


def _format_rule(category: str, rule: dict[str, Any]) -> str:
    responses = rule.get("recommended_responses", [])
    forbidden = rule.get("forbidden_responses", [])
    signals = rule.get("customer_signals", [])

    return "\n".join(
        [
            f"Rule: {category} ({rule.get('label', category)})",
            f"Alert priority: {rule.get('alert_priority', 'medium')}",
            "Matched customer signals: "
            + "; ".join(str(signal) for signal in signals[:8]),
            "Salesperson should: "
            + "; ".join(str(response) for response in responses[:5]),
            "Salesperson must not: "
            + "; ".join(str(response) for response in forbidden[:5]),
        ]
    )


def _product_facts_summary() -> str:
    if not PRODUCT_FACTS:
        return "No product facts loaded."

    items = list(PRODUCT_FACTS.items())[:MAX_FACT_SUMMARY_ITEMS]
    return "\n".join(f"- {key}: {value}" for key, value in items)


def build_kb_context(transcript: str) -> str:
    """Return only KB rules relevant to the transcript, or compact facts."""
    transcript_text = _normalise_text(transcript)
    matched_rules = []

    for category, rule in OBJECTION_RULES.items():
        if isinstance(rule, dict) and _rule_matches(transcript_text, rule):
            matched_rules.append(_format_rule(category, rule))

    if matched_rules:
        return "\n\n".join(matched_rules)

    return "No specific objection rule matched. Product fact summary:\n" + (
        _product_facts_summary()
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
                    kb_context=build_kb_context(transcript),
                    calibration_rules=CRITICAL_ALERT_CALIBRATION_RULES,
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
