import json
import os
import sys
import time

import numpy as np
from scipy.io import wavfile


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exceptions import STTError, TriageError
from core.logger import get_logger
from core.schemas import EventDict, validate_event
from config import Config
from transcription import diarizer, indic_conformer_stt
from triage import qwen3_triage


logger = get_logger(__name__)


def _empty_event(transcript: str, reasoning: str) -> EventDict:
    """Create a schema-valid no-signal event for recoverable pipeline failures."""
    return validate_event(
        {
            "transcript": transcript,
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
            transcript = indic_conformer_stt.transcribe(audio_bytes, sample_rate)
        except STTError as error:
            logger.error("STT failed for %s: %s", salesperson_name, error)
            return _empty_event("", "STT failed")

        if not transcript:
            logger.warning("Empty transcript from STT, skipping triage")
            return _empty_event("", "STT failed")

        logger.info(
            "STT completed: %s chars, salesperson=%s",
            len(transcript),
            salesperson_name,
        )

        try:
            event = validate_event(qwen3_triage.triage(transcript, salesperson_name))
        except TriageError as error:
            logger.error("Triage failed for %s: %s", salesperson_name, error)
            return _empty_event(transcript, "triage failed")

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
