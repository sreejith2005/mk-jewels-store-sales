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
try:
    from config import Config
except ImportError:
    pass

class GeminiAPIError(Exception):
    """Custom exception for Gemini API errors."""
    pass

def transcribe_and_triage(audio_bytes: bytes, sample_rate: int, salesperson_name: str) -> dict:
    """
    Transcribes audio and triages sales conversation using Gemini.
    """
    try:
        # Convert raw PCM audio bytes to WAV buffer in memory
        # Assuming 16-bit PCM which is standard for such audio captures
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, sample_rate, audio_data)
        wav_bytes = wav_buffer.getvalue()
    except Exception as e:
        raise GeminiAPIError(f"Failed to convert audio to WAV: {e}")

    try:
        client = genai.Client(api_key=Config.GEMINI_API_KEY)
    except Exception as e:
        raise GeminiAPIError(f"Failed to initialize Gemini Client: {e}")

    system_prompt = (
        "You are an AI assistant monitoring sales conversations at a jewelry store in India. "
        "The salesperson may speak in English, Hindi, Marathi, or a mix of all three. "
        "Your job is to transcribe the conversation accurately and then analyze it for signals "
        "that a sales manager should know about. Jewelry-specific terms you will encounter include: "
        "hallmark, BIS, HUID, carat, VVS, solitaire, kundan, polki, making charges, exchange scheme, "
        "IGI, GIA, solitaire, rhodium. Preserve these terms exactly as spoken."
    )

    user_prompt = (
        "Transcribe this audio exactly as spoken, preserving all languages. "
        "Then output ONLY a valid JSON object with these fields and no other text: "
        "transcript (string), objection_detected (bool), price_concern (bool), "
        "certification_question (bool), upsell_miss (bool), knowledge_gap (bool), "
        "intent_signal (bool), alert_priority (string, one of: none / low / medium / high), "
        "reasoning (string, max 20 words explaining the highest-priority signal detected or 'no signals detected')."
    )

    def parse_json_response(text: str) -> dict:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type='audio/wav'),
                user_prompt
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json"
            )
        )
        response_text = response.text
    except Exception as e:
        raise GeminiAPIError(f"Gemini API request failed: {e}")

    try:
        return parse_json_response(response_text)
    except json.JSONDecodeError:
        # Retry once with a prompt asking Gemini to return only the JSON object again
        retry_prompt = "Please return ONLY the valid JSON object requested previously, and no other text."
        try:
            retry_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Part.from_bytes(data=wav_bytes, mime_type='audio/wav'),
                    user_prompt + "\n\n" + retry_prompt
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                )
            )
            return parse_json_response(retry_response.text)
        except Exception as e:
            raise GeminiAPIError(f"Gemini API retry request or JSON parsing failed: {e}")
