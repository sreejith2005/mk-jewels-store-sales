import json
import os
import sys
import time

import numpy as np
import requests
from scipy.io import wavfile


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exceptions import STTError, TriageError
from core.logger import get_logger
from core.schemas import EventDict, validate_event
from config import Config
from transcription import diarizer, indic_conformer_stt
from triage import qwen3_triage


logger = get_logger(__name__)
logger.info(
    f"Pipeline mode: {Config.PIPELINE_MODE} — using "
    f"{'Gemini' if Config.PIPELINE_MODE == 'demo' else 'local models'}"
)
_MODELS_WARMED_UP = False


def _contains_devanagari(text: str) -> bool:
    return any("\u0900" <= char <= "\u097f" for char in text)


def romanize_hindi(transcript: str) -> str:
    """Convert Devanagari transcript text to readable Roman-script Hinglish."""
    logger.info(f"ROMANIZE_HINDI config: {Config.ROMANIZE_HINDI}")
    logger.info(f"GEMINI_API_KEY present: {bool(Config.GEMINI_API_KEY)}")
    logger.info(f"Transcript before romanization: {transcript[:50]}")

    if not Config.ROMANIZE_HINDI or not transcript or not _contains_devanagari(transcript):
        logger.info(f"Transcript after romanization: {transcript[:50]}")
        return transcript

    if not Config.GEMINI_API_KEY:
        logger.warning(
            "ROMANIZE_HINDI is enabled but GEMINI_API_KEY is missing; using original transcript"
        )
        logger.info(f"Transcript after romanization: {transcript[:50]}")
        return transcript

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=Config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                "Convert this transcript to natural Roman-script Hinglish/English. "
                "Preserve English jewelry terms like diamond, hallmark, BIS, HUID, "
                "carat, solitaire, kundan, polki, making charges, IGI, and GIA. "
                "Return only the converted transcript, with no explanation.\n\n"
                f"{transcript}"
            ),
            config=types.GenerateContentConfig(
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        result = (response.text or "").strip() or transcript
        logger.info(f"Transcript after romanization: {result[:50]}")
        return result
    except Exception:
        logger.error("Gemini romanization failed; using original transcript", exc_info=True)
        logger.info(f"Transcript after romanization: {transcript[:50]}")
        return transcript


def load_models() -> bool:
    """Load and verify startup models before accepting production audio."""
    global _MODELS_WARMED_UP
    if Config.PIPELINE_MODE == "demo":
        logger.info("Demo mode active - skipping local model startup checks")
        _MODELS_WARMED_UP = True
        return True

    if _MODELS_WARMED_UP:
        return True

    warmup_start = time.perf_counter()
    sample_rate = 16000

    try:
        stt_start = time.perf_counter()
        stt_model = indic_conformer_stt._load_model()

        import torch

        silent_waveform = torch.from_numpy(
            np.zeros(int(sample_rate * 0.5), dtype=np.float32)
        ).float().unsqueeze(0)
        with torch.no_grad():
            indic_conformer_stt._infer_transcript(stt_model, silent_waveform)
        logger.info("IndicConformer warmup completed in %.2fs", time.perf_counter() - stt_start)
    except Exception:
        logger.critical("IndicConformer warmup failed.", exc_info=True)
        return False

    qwen_ready = False
    qwen_payload = {
        "model": qwen3_triage.MODEL_NAME,
        "prompt": "reply ok",
        "stream": False,
        "options": {
            "num_predict": 3,
            "temperature": 0,
        },
    }
    for attempt in range(1, 3):
        try:
            qwen_start = time.perf_counter()
            response = requests.post(
                f"{Config.OLLAMA_HOST.rstrip('/')}/api/generate",
                json=qwen_payload,
                timeout=300,
            )
            response.raise_for_status()
            response_data = response.json()
            if response_data.get("done") is not True:
                raise RuntimeError(
                    f"Ollama returned unexpected status: {response.status_code}"
                )
            qwen_ready = True
            logger.info("Qwen3 warmup OK in %.2fs", time.perf_counter() - qwen_start)
            break
        except (requests.RequestException, RuntimeError, ValueError):
            logger.error("Qwen3 warmup attempt %d failed.", attempt, exc_info=True)
            if attempt == 1:
                logger.info("Retrying Qwen3 warmup in 5 seconds")
                time.sleep(5)

    if not qwen_ready:
        logger.critical("Qwen3 warmup failed after all attempts.")
        return False

    _MODELS_WARMED_UP = True
    logger.info("Models ready in %.2f seconds", time.perf_counter() - warmup_start)
    return True


def warmup_models() -> None:
    """Backward-compatible wrapper for startup model verification."""
    if not load_models():
        raise RuntimeError("Model warmup failed")


def _empty_event(transcript: str, reasoning: str) -> EventDict:
    """Create a schema-valid no-signal event for recoverable pipeline failures."""
    return validate_event(
        {
            "transcript": transcript,
            "raw_transcript": transcript,
            "display_transcript": transcript,
            "triage_status": "failed" if reasoning == "triage failed" else "skipped",
            "objection_detected": False,
            "price_concern": False,
            "certification_question": False,
            "upsell_miss": False,
            "knowledge_gap": False,
            "intent_signal": False,
            "alert_priority": "none",
            "reasoning": reasoning,
        }
    )


def _wav_data_to_pcm_bytes(data: np.ndarray) -> bytes:
    """Convert WAV data from scipy into raw int16 mono PCM bytes for testing."""
    if data.ndim > 1:
        data = data.mean(axis=1)

    if data.dtype == np.int16:
        pcm = data
    elif np.issubdtype(data.dtype, np.floating):
        pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
    else:
        max_abs = max(abs(np.iinfo(data.dtype).min), np.iinfo(data.dtype).max)
        pcm = (data.astype(np.float32) / max_abs * 32767).astype(np.int16)

    return pcm.tobytes()


def transcribe_and_triage(
    audio_bytes: bytes,
    sample_rate: int,
    salesperson_name: str,
    openrouter_fallback: bool = True,
) -> dict:
    """
    Transcribe audio with IndicConformer, then triage the transcript with Qwen3.

    openrouter_fallback is accepted only for API compatibility with gemini_stt.
    Production local pipeline errors are converted into no-signal EventDicts so
    the session loop can continue processing future audio chunks.
    """
    del openrouter_fallback

    start_time = time.perf_counter()
    transcript = ""
    raw_transcript = ""

    try:
        if Config.DIARIZATION_ENABLED:
            try:
                segments = diarizer.diarize(audio_bytes, sample_rate)
                if segments:
                    salesperson_speaker = diarizer.dominant_speaker(segments)
                    salesperson_audio = diarizer.extract_speaker_audio(
                        audio_bytes,
                        sample_rate,
                        segments,
                        salesperson_speaker,
                    )
                    if salesperson_audio:
                        audio_bytes = salesperson_audio
                        logger.info(
                            "Diarization: using speaker %s (%d segments)",
                            salesperson_speaker,
                            len(segments),
                        )
                    else:
                        logger.warning(
                            "Diarization: no audio for dominant speaker, using full audio"
                        )
                else:
                    logger.warning("Diarization: no segments returned, using full audio")
            except STTError as error:
                logger.error("Diarization failed, using full audio: %s", error)

        try:
            raw_transcript = indic_conformer_stt.transcribe(audio_bytes, sample_rate)
        except STTError as error:
            logger.error("STT failed for %s: %s", salesperson_name, error)
            return _empty_event("", "STT failed")

        if not raw_transcript:
            logger.warning("Empty transcript from STT, skipping triage")
            return _empty_event("", "STT failed")

        transcript = romanize_hindi(raw_transcript)

        logger.info(
            "STT completed: %s chars, salesperson=%s",
            len(raw_transcript),
            salesperson_name,
        )

        try:
            event = validate_event(qwen3_triage.triage(transcript, salesperson_name))
            event["raw_transcript"] = raw_transcript
            event["display_transcript"] = event.get("display_transcript") or transcript
            event["transcript"] = event["display_transcript"]
        except TriageError:
            logger.error(
                "Triage failed for %s. Raw transcript passed to triage: %r",
                salesperson_name,
                transcript,
                exc_info=True,
            )
            return _empty_event(transcript, "triage unavailable")

        logger.info(
            "Triage completed: priority=%s, salesperson=%s",
            event["alert_priority"],
            salesperson_name,
        )
        return event
    finally:
        elapsed = time.perf_counter() - start_time
        logger.debug(
            "Pipeline latency: %.2fs for %s bytes",
            elapsed,
            len(audio_bytes),
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python transcription/local_pipeline.py <audio_file.wav>")
        sys.exit(1)

    audio_file_path = sys.argv[1]
    if not os.path.exists(audio_file_path):
        logger.error("Could not find audio file '%s'", audio_file_path)
        sys.exit(1)

    logger.info(
        "Testing local pipeline with %s. Requires Ollama running and the "
        "IndicConformer model available.",
        audio_file_path,
    )

    try:
        wav_sample_rate, wav_data = wavfile.read(audio_file_path)
        raw_audio_bytes = _wav_data_to_pcm_bytes(wav_data)
        standalone_start = time.perf_counter()
        result = transcribe_and_triage(
            raw_audio_bytes,
            wav_sample_rate,
            "Test Salesperson",
        )
        result_with_latency = {
            **result,
            "latency_seconds": round(time.perf_counter() - standalone_start, 2),
        }

        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(result_with_latency, indent=2, ensure_ascii=False))
    except Exception as error:
        logger.error("Local pipeline standalone test failed: %s", error)
        sys.exit(1)
