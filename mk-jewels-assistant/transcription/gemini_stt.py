import io
import json
import sys
import os
import numpy as np
import scipy.io.wavfile as wavfile
from google import genai
from google.genai import types

# Add parent directory to sys.path to allow importing config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.exceptions import TriageError
from core.logger import get_logger
from core.schemas import validate_event
from triage.qwen3_triage import (
    CRITICAL_ALERT_CALIBRATION_RULES,
    build_kb_context,
)

try:
    from config import Config
except ImportError:
    pass


logger = get_logger(__name__)
logger.info(
    f"Pipeline mode: {Config.PIPELINE_MODE} — using "
    f"{'Gemini' if Config.PIPELINE_MODE == 'demo' else 'local models'}"
)


class GeminiAPIError(Exception):
    """Custom exception for Gemini API errors."""
    pass


def parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def _validate_triage_result(result: dict) -> dict:
    try:
        return validate_event(result)
    except ValueError as e:
        raise TriageError(str(e)) from e


def _gemini_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


SYSTEM_PROMPT = (
    "You are an AI assistant monitoring sales conversations at a jewelry store in India. "
    "The salesperson may speak in English, Hindi, Marathi, or a mix of all three. "
    "Your job is to transcribe the conversation accurately and then analyze it for signals "
    "that a sales manager should know about. Jewelry-specific terms you will encounter include: "
    "hallmark, BIS, HUID, carat, VVS, solitaire, kundan, polki, making charges, exchange scheme, "
    "IGI, GIA, solitaire, rhodium. Preserve these terms exactly as spoken. "
    "If the transcript contains Hindi or other Indian language text in Devanagari script, "
    "transliterate it to Roman script (Hinglish) before returning. Return only Roman script "
    "text in the transcript field."
)

USER_PROMPT = (
    "Transcribe this audio exactly as spoken, preserving all languages. "
    "After transcription, apply this knowledge-base context while classifying:\n"
    "--- MK JEWELS KNOWLEDGE BASE (relevant to this conversation) ---\n"
    "{kb_context}\n"
    "--- END KNOWLEDGE BASE ---\n\n"
    "{calibration_rules}\n\n"
    "Then respond with ONLY the JSON object. No explanation, no preamble, no "
    "markdown code fences. Maximum response length: 150 tokens. Return these "
    "fields: "
    "transcript (string), objection_detected (bool), price_concern (bool), "
    "certification_question (bool), upsell_miss (bool), knowledge_gap (bool), "
    "intent_signal (bool), alert_priority (string, one of: none / low / medium / high), "
    "reasoning (string, max 20 words explaining the highest-priority signal detected or 'no signals detected')."
)


def _build_gemini_user_prompt(transcript_text: str = "") -> str:
    return USER_PROMPT.format(
        kb_context=build_kb_context(transcript_text),
        calibration_rules=CRITICAL_ALERT_CALIBRATION_RULES,
    )


def _triage_openrouter(transcript_text: str, salesperson_name: str) -> dict:
    from openai import OpenAI

    client = OpenAI(
        api_key=Config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )

    prompt = (
        f"Salesperson: {salesperson_name}\n"
        f"Transcript:\n{transcript_text}\n\n"
        "--- MK JEWELS KNOWLEDGE BASE (relevant to this conversation) ---\n"
        f"{build_kb_context(transcript_text)}\n"
        "--- END KNOWLEDGE BASE ---\n\n"
        f"{CRITICAL_ALERT_CALIBRATION_RULES}\n\n"
        "Classify this jewelry sales conversation. Respond with ONLY the JSON object. "
        "No explanation, no preamble, no markdown code fences. Maximum response "
        "length: 150 tokens. Return these fields: objection_detected (bool), "
        "price_concern (bool), certification_question (bool), upsell_miss (bool), "
        "knowledge_gap (bool), intent_signal (bool), alert_priority (string, one of: "
        "none / low / medium / high), reasoning (string, max 20 words explaining the "
        "highest-priority signal detected or 'no signals detected')."
    )

    response = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct:free",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    result = parse_json_response(response.choices[0].message.content)
    result["transcript"] = transcript_text
    return _validate_triage_result(result)


def _fallback_or_raise(
    error: GeminiAPIError,
    transcript_text: str,
    salesperson_name: str,
    openrouter_fallback: bool,
) -> dict:
    if openrouter_fallback:
        try:
            logger.info(
                "OpenRouter fallback triage transcript for %s: %r",
                salesperson_name,
                transcript_text,
            )
            return _triage_openrouter(transcript_text, salesperson_name)
        except TriageError:
            logger.error(
                "OpenRouter fallback triage failed for %s. Raw transcript: %r",
                salesperson_name,
                transcript_text,
                exc_info=True,
            )
            raise
        except Exception:
            logger.error(
                "OpenRouter fallback triage crashed for %s. Raw transcript: %r",
                salesperson_name,
                transcript_text,
                exc_info=True,
            )
            pass
    raise error


def transcribe_and_triage(
    audio_bytes: bytes,
    sample_rate: int,
    salesperson_name: str,
    openrouter_fallback: bool = True,
) -> dict:
    """
    Transcribes audio and triages sales conversation using Gemini.
    """
    transcript_text = ""

    try:
        # Convert raw PCM audio bytes to WAV buffer in memory
        # Assuming 16-bit PCM which is standard for such audio captures
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, sample_rate, audio_data)
        wav_bytes = wav_buffer.getvalue()
    except Exception as e:
        error = GeminiAPIError(f"Failed to convert audio to WAV: {e}")
        return _fallback_or_raise(
            error, transcript_text, salesperson_name, openrouter_fallback
        )

    try:
        client = genai.Client(api_key=Config.GEMINI_API_KEY)
    except Exception as e:
        error = GeminiAPIError(f"Failed to initialize Gemini Client: {e}")
        return _fallback_or_raise(
            error, transcript_text, salesperson_name, openrouter_fallback
        )

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type='audio/wav'),
                _build_gemini_user_prompt()
            ],
            config=_gemini_config(),
        )
        response_text = response.text
    except Exception as e:
        error = GeminiAPIError(f"Gemini API request failed: {e}")
        return _fallback_or_raise(
            error, transcript_text, salesperson_name, openrouter_fallback
        )

    try:
        result = parse_json_response(response_text)
        transcript_text = result.get("transcript", "")
        return _validate_triage_result(result)
    except json.JSONDecodeError:
        # Retry once with a prompt asking Gemini to return only the JSON object again
        retry_prompt = "Please return ONLY the valid JSON object requested previously, and no other text."
        try:
            retry_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Part.from_bytes(data=wav_bytes, mime_type='audio/wav'),
                    _build_gemini_user_prompt(transcript_text) + "\n\n" + retry_prompt
                ],
                config=_gemini_config(),
            )
            result = parse_json_response(retry_response.text)
        except json.JSONDecodeError as e:
            error = GeminiAPIError(f"Gemini API retry request or JSON parsing failed: {e}")
            return _fallback_or_raise(
                error, transcript_text, salesperson_name, openrouter_fallback
            )
        except Exception as e:
            error = GeminiAPIError(f"Gemini API retry request or JSON parsing failed: {e}")
            return _fallback_or_raise(
                error, transcript_text, salesperson_name, openrouter_fallback
            )
        transcript_text = result.get("transcript", "")
        return _validate_triage_result(result)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.info("Usage: python gemini_stt.py <audio_file.wav>")
        sys.exit(1)

    audio_file_path = sys.argv[1]
    if not os.path.exists(audio_file_path):
        logger.error("Could not find audio file '%s'", audio_file_path)
        sys.exit(1)

    logger.info("Testing transcribe_and_triage with %s...", audio_file_path)
    try:
        # Read WAV file directly for testing, though in production it might be raw PCM
        # Since transcribe_and_triage expects raw PCM bytes, we extract them from the WAV file
        sample_rate, data = wavfile.read(audio_file_path)
        # Convert back to raw bytes for testing the function
        raw_audio_bytes = data.tobytes()
        
        result = transcribe_and_triage(
            audio_bytes=raw_audio_bytes,
            sample_rate=sample_rate,
            salesperson_name="Test Salesperson"
        )
        logger.info("--- Result ---")
        # Ensure stdout handles UTF-8 to prevent charmap errors on Windows
        import sys
        if sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
        logger.info(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        logger.error("Error: %s", e)
