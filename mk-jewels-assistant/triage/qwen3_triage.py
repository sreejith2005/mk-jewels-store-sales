import json
import os
import sys
import time
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

SYSTEM_PROMPT = """You are a sales conversation classifier.
Analyze the conversation and return ONLY a JSON object.
No explanation, no markdown, no preamble. Only JSON.

JSON format:
{
  "objection_detected": true/false,
  "price_concern": true/false,
  "certification_question": true/false,
  "upsell_miss": true/false,
  "knowledge_gap": true/false,
  "intent_signal": true/false,
  "alert_priority": "none/low/medium/high",
  "reasoning": "max 15 words"
}

Rules:
- price_concern: true if customer mentions price, cost, expensive, discount
- objection_detected: true if customer shows resistance or doubt
- intent_signal: true if customer shows buying interest
- alert_priority high: if salesperson is rude or gives wrong facts
- alert_priority medium: if salesperson misses obvious opportunity
- alert_priority none: normal conversation"""

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
    "5. Be appropriately sensitive. If a customer clearly expresses a price "
    "concern, objection, or buying intent, classify it - even if the "
    "salesperson responds well. These signals describe the CUSTOMER's state, "
    "not just the salesperson's failure. objection_detected and price_concern "
    "describe what the customer said. upsell_miss and knowledge_gap describe "
    "the salesperson's response.\n\n"
    "6. Signals describe what happened in the conversation. If the customer "
    "clearly expresses price concern, dissatisfaction, objection, certification "
    "question, or buying intent, mark the relevant signal true even if the "
    "salesperson responds well. Examples: \"Price zyada hai\" => price_concern "
    "true; \"Making charges high hai\" => price_concern true and "
    "objection_detected true; \"Mujhe service pasand nahi hai\" => "
    "objection_detected true; \"Diamond certified hai kya?\" => "
    "certification_question true; \"Mujhe bridal collection dekhna hai\" => "
    "intent_signal true.\n\n"
    "7. The reasoning field must state specifically what the salesperson said "
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
    "Classify this jewelry sales conversation. Respond with ONLY the JSON object. "
    "No explanation, no preamble, no markdown code fences. Maximum response "
    "length: 150 tokens. Return exactly these fields: "
    "display_transcript (string), objection_detected (bool), price_concern (bool), certification_question (bool), "
    "upsell_miss (bool), knowledge_gap (bool), intent_signal (bool), "
    "alert_priority (string, one of: none / low / medium / high), "
    "reasoning (string, max 20 words).\n\n"
    "display_transcript rules: If transcript is Hindi in Devanagari, convert it "
    "to natural readable Hinglish, e.g. \"मुझे अच्छा लगा\" -> \"Mujhe acha "
    "laga\" and \"मुझे आपकी सर्विस बिल्कुल पसंद नहीं है\" -> \"Mujhe aapki "
    "service bilkul pasand nahi hai\". If transcript is English, keep natural "
    "English. If mixed Hindi-English, keep natural Hinglish. Do NOT use "
    "academic transliteration, ITRANS-style text, or capitalized phonetic "
    "symbols like prAijiMga, kaiMDa, brAiDala. Keep meaning the same."
)

SESSION_SCORE_PROMPT_TEMPLATE = (
    "You are a jewelry sales coach evaluating a salesperson's performance.\n"
    "Here is the full sales conversation transcript:\n\n"
    "{full_transcript}\n\n"
    "Score {salesperson_name} on each dimension from 0-10.\n"
    "Base scores on what actually happened in the transcript.\n"
    "Be fair but honest - a score of 5 means average, not bad.\n"
    "7+ means good, 9+ means excellent, below 4 means needs improvement.\n\n"
    "Return ONLY this JSON, no other text:\n"
    "{{\n"
    '  "greeting_score": <int 0-10>,\n'
    '  "product_knowledge_score": <int 0-10>,\n'
    '  "objection_handling_score": <int 0-10>,\n'
    '  "missed_oppurtuinity": <int 0-10>,\n'
    '  "upsell_score": <int 0-10>,\n'
    '  "closing_score": <int 0-10>,\n'
    '  "customer_satisfaction": "<Positive|Neutral|Negative>",\n'
    '  "score_reasoning": "<max 50 words>"\n'
    "}}\n\n"
    "If the transcript is too short to evaluate a dimension, score it 5 (neutral)."
)

SCORE_KEYS = (
    "greeting_score",
    "product_knowledge_score",
    "objection_handling_score",
    "missed_oppurtuinity",
    "upsell_score",
    "closing_score",
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
    text = text.strip()
    if text.startswith("{") and not text.endswith("}"):
        text += "}"

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise TriageError(f"Invalid JSON from Qwen3: {raw_text[:200]}") from error


def _validate_triage_result(result: dict[str, Any]) -> dict:
    try:
        return validate_event(result)
    except ValueError as error:
        raise TriageError(str(error)) from error


def _clamp_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 5
    return max(0, min(score, 10))


def _validate_score_result(result: dict[str, Any]) -> dict[str, Any]:
    scores = {key: _clamp_score(result.get(key, 5)) for key in SCORE_KEYS}
    satisfaction = str(result.get("customer_satisfaction", "Neutral")).strip().lower()
    if satisfaction == "positive":
        customer_satisfaction = "Positive"
    elif satisfaction == "negative":
        customer_satisfaction = "Negative"
    else:
        customer_satisfaction = "Neutral"

    reasoning_words = str(result.get("score_reasoning", "")).strip().split()
    return {
        **scores,
        "customer_satisfaction": customer_satisfaction,
        "score_reasoning": " ".join(reasoning_words[:50]),
    }


def _empty_event() -> dict:
    return _validate_triage_result(
        {
            "transcript": "",
            "raw_transcript": "",
            "display_transcript": "",
            "triage_status": "skipped",
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


def _fallback_event(transcript: str) -> dict:
    return _validate_triage_result(
        {
            "transcript": transcript,
            "raw_transcript": transcript,
            "display_transcript": transcript,
            "triage_status": "unavailable",
            "objection_detected": False,
            "price_concern": False,
            "certification_question": False,
            "upsell_miss": False,
            "knowledge_gap": False,
            "intent_signal": False,
            "alert_priority": "none",
            "reasoning": "triage unavailable",
            "knowledge_base_followed": True,
        }
    )


def triage(transcript: str, salesperson_name: str) -> dict:
    """Classify an English-language transcript with Qwen3 via Ollama."""
    transcript_text = transcript.strip()
    if not transcript_text:
        logger.info("Skipping Qwen3 triage for empty transcript.")
        return _empty_event()

    full_prompt = f"Classify this conversation:\n{transcript_text}"

    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "think": False,
        "options": {
            "num_predict": 150,
            "temperature": 0,
            "stop": ["}"],
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": full_prompt,
            },
        ],
    }

    logger.info(f"Triage input transcript length: {len(transcript)} chars")
    logger.info(f"Triage prompt total length: {len(full_prompt)} chars")
    logger.info(f"Sending to Ollama at {Config.OLLAMA_HOST}")
    logger.info(
        "Qwen3 triage request transcript for %s: %r",
        salesperson_name,
        transcript,
    )

    raw_response_text = ""
    raw_text = ""
    response_json = None
    for attempt in range(3):
        try:
            response = requests.post(
                f"{Config.OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=(5, 90),
            )
            raw_response_text = response.text
            logger.info(f"Ollama response status: {response.status_code}")
            logger.info(
                f"Ollama raw response (first 500 chars): {response.text[:500]}"
            )
            if response.status_code == 200:
                response_json = response.json()
                raw_text = response_json.get("message", {}).get("content", "")
                if response_json.get("done") and raw_text:
                    break
            logger.warning(f"Triage attempt {attempt + 1} got empty/bad response")
        except requests.Timeout:
            logger.warning(f"Triage attempt {attempt + 1} timed out")
        except (requests.RequestException, ValueError):
            logger.warning(
                "Triage attempt %d failed while calling Ollama",
                attempt + 1,
                exc_info=True,
            )
        if attempt < 2:
            time.sleep(2**attempt)
    else:
        logger.error(
            "Qwen3 triage unavailable after retries. Raw transcript: %r; "
            "raw HTTP response: %r; raw content: %r",
            transcript,
            raw_response_text,
            raw_text,
        )
        return _fallback_event(transcript)

    try:
        logger.info("Raw Qwen3 triage HTTP response: %s", raw_response_text)
        logger.info("Raw Qwen3 triage response content: %s", raw_text)
        result = _parse_json_response(raw_text)
        result["raw_transcript"] = transcript
        result["display_transcript"] = result.get("display_transcript") or transcript
        result["transcript"] = result["display_transcript"]
        result["triage_status"] = "ok"
        return _validate_triage_result(result)
    except (ValueError, KeyError, TypeError, TriageError) as error:
        logger.error(
            "Qwen3 triage response handling failed. Raw transcript: %r; "
            "raw HTTP response: %r; raw content: %r",
            transcript,
            raw_response_text,
            raw_text,
            exc_info=True,
        )
        return _fallback_event(transcript)


def score_session(full_transcript: str, salesperson_name: str) -> dict[str, Any] | None:
    """Score a full completed session transcript with Qwen3 via Ollama."""
    transcript_text = full_transcript.strip()
    if not transcript_text:
        logger.info("Skipping Qwen3 session scoring for empty transcript.")
        return _validate_score_result({})

    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "think": False,
        "options": {
            "num_predict": 180,
            "temperature": 0,
            "stop": ["}"],
        },
        "messages": [
            {
                "role": "user",
                "content": SESSION_SCORE_PROMPT_TEMPLATE.format(
                    full_transcript=transcript_text,
                    salesperson_name=salesperson_name,
                ),
            },
        ],
    }

    raw_response_text = ""
    raw_text = ""
    for attempt in range(3):
        try:
            response = requests.post(
                f"{Config.OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=(5, 90),
            )
            raw_response_text = response.text
            logger.info("Ollama session scoring response status: %s", response.status_code)
            logger.info(
                "Ollama session scoring raw response (first 500 chars): %s",
                response.text[:500],
            )
            if response.status_code == 200:
                response_json = response.json()
                raw_text = response_json.get("message", {}).get("content", "")
                logger.info("Raw Qwen3 session score response: %s", raw_text)
                if response_json.get("done") and raw_text.strip():
                    return _validate_score_result(_parse_json_response(raw_text))
            logger.warning(
                "Session scoring attempt %d got empty/bad response",
                attempt + 1,
            )
        except requests.Timeout:
            logger.warning("Session scoring attempt %d timed out", attempt + 1)
        except (requests.RequestException, ValueError, KeyError, TypeError, TriageError):
            logger.warning(
                "Session scoring attempt %d failed while calling Ollama",
                attempt + 1,
                exc_info=True,
            )
        if attempt < 2:
            time.sleep(2**attempt)

    logger.warning(
        "Qwen3 session scoring unavailable after retries. Leaving session unscored. "
        "Raw HTTP response: %r; raw content: %r",
        raw_response_text,
        raw_text,
    )
    return None


if __name__ == "__main__":
    sample_transcript = "Customer boli yeh necklace bohot mehnga hai, discount milega?"
    triage_result = triage(sample_transcript, "Test Salesperson")
    logger.info(json.dumps(triage_result, indent=2, ensure_ascii=False))
