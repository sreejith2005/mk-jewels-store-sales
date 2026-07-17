import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from core.exceptions import STTError
from core.logger import get_logger


logger = get_logger(__name__)

MODEL_ID = "ai4bharat/indic-conformer-600m-multilingual"
TARGET_SAMPLE_RATE = 16000
DEFAULT_DECODING = "ctc"

_model = None
_WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _load_model() -> object:
    """Load and cache the custom IndicConformer model."""
    global _model
    if _model is not None:
        return _model

    try:
        import torch
        from transformers import AutoModel

        if Config.DEVICE == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but unavailable; falling back to CPU")

        model_kwargs = {"trust_remote_code": True}
        token = Config.HUGGINGFACE_TOKEN.strip() or None
        if token:
            model_kwargs["token"] = token

        model = AutoModel.from_pretrained(MODEL_ID, **model_kwargs)
        model.eval()
        logger.info("IndicConformer model loaded on %s", Config.DEVICE)
        _model = model
        return _model
    except Exception as exc:
        raise STTError(f"Failed to load IndicConformer model: {exc}") from exc


model = _load_model()


def _pcm_bytes_to_float32(audio_bytes: bytes) -> np.ndarray:
    """Convert raw int16 PCM bytes to normalized mono float32 samples."""
    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    return (audio.astype(np.float32) / 32768.0).clip(-1.0, 1.0)


def _resample_if_needed(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Resample audio to the model's expected sample rate."""
    if sample_rate == TARGET_SAMPLE_RATE:
        return audio

    gcd = np.gcd(sample_rate, TARGET_SAMPLE_RATE)
    up = TARGET_SAMPLE_RATE // gcd
    down = sample_rate // gcd
    return resample_poly(audio, up, down).astype(np.float32)


def _repeated_word_run(transcript: str) -> tuple[str, int] | None:
    """Return a word and run length when it appears at least six times in a row."""
    previous_word = ""
    run_length = 0
    for word in _WORD_PATTERN.findall(transcript.casefold()):
        if word == previous_word:
            run_length += 1
        else:
            previous_word = word
            run_length = 1
        if run_length > 5:
            return word, run_length
    return None


def _save_repetition_waveform(waveform: np.ndarray, fingerprint: str) -> None:
    """Save the model input only when temporary repetition diagnostics are enabled."""
    if not Config.DEBUG_SAVE_REPETITION_AUDIO:
        return

    try:
        debug_dir = Path(Config.DEBUG_REPETITION_AUDIO_DIR)
        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        debug_path = debug_dir / f"repetition_{timestamp}_{fingerprint}.wav"
        pcm = (np.clip(waveform, -1.0, 1.0) * 32767).astype(np.int16)
        wavfile.write(debug_path, TARGET_SAMPLE_RATE, pcm)
        logger.warning("Saved repetition diagnostic audio to %s", debug_path)
    except Exception:
        logger.exception("Failed to save repetition diagnostic audio")


def transcribe(audio_bytes: bytes, sample_rate: int) -> str:
    """
    Transcribe raw int16 PCM mono audio bytes using IndicConformer CTC decoding.
    """
    if not audio_bytes:
        return ""

    try:
        import torch

        audio = _pcm_bytes_to_float32(audio_bytes)
        if audio.size == 0 or not np.any(audio):
            return ""

        audio = _resample_if_needed(audio, sample_rate)
        if audio.size == 0 or not np.any(audio):
            return ""

        waveform = torch.from_numpy(audio).float().unsqueeze(0)
        waveform_bytes = waveform.numpy().tobytes()
        waveform_fingerprint = hashlib.sha256(waveform_bytes).hexdigest()[:16]
        waveform_sample_count = int(audio.size)
        waveform_duration_seconds = waveform_sample_count / TARGET_SAMPLE_RATE
        stt_model = _load_model()

        with torch.no_grad():
            transcript = stt_model(
                waveform,
                Config.INDIC_CONFORMER_LANGUAGE,
                DEFAULT_DECODING,
            )

        if isinstance(transcript, (list, tuple)):
            transcript = " ".join(str(item) for item in transcript)
        raw_transcript = str(transcript)
        logger.info(
            "IndicConformer chunk output: fingerprint=%s samples=%d duration_seconds=%.3f "
            "raw_chars=%d raw_preview=%r",
            waveform_fingerprint,
            waveform_sample_count,
            waveform_duration_seconds,
            len(raw_transcript),
            raw_transcript[:200],
        )

        repetition = _repeated_word_run(raw_transcript)
        if repetition:
            repeated_word, run_length = repetition
            logger.warning(
                "IndicConformer repeated-word output: word=%r run_length=%d "
                "fingerprint=%s raw_output=%r",
                repeated_word,
                run_length,
                waveform_fingerprint,
                raw_transcript,
            )
            _save_repetition_waveform(audio, waveform_fingerprint)

        return raw_transcript.strip()
    except STTError:
        raise
    except Exception as exc:
        raise STTError(f"IndicConformer transcription failed: {exc}") from exc


def _wav_data_to_pcm_bytes(data: np.ndarray) -> bytes:
    """Convert WAV data from scipy into raw int16 mono PCM bytes for testing."""
    if data.ndim > 1:
        data = data.mean(axis=1)

    if data.dtype == np.int16:
        pcm = data
    elif np.issubdtype(data.dtype, np.floating):
        pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
    else:
        max_value = np.iinfo(data.dtype).max
        pcm = (data.astype(np.float32) / max_value * 32767).astype(np.int16)

    return pcm.tobytes()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        try:
            _load_model()
            logger.info("IndicConformer load smoke test passed")
            sys.stdout.write("IndicConformer load smoke test passed\n")
            sys.exit(0)
        except Exception as exc:
            logger.error("IndicConformer load smoke test failed: %s", exc)
            sys.exit(1)

    audio_file_path = sys.argv[1]
    try:
        wav_sample_rate, wav_data = wavfile.read(audio_file_path)
        raw_audio_bytes = _wav_data_to_pcm_bytes(wav_data)
        result = transcribe(raw_audio_bytes, wav_sample_rate)
        sys.stdout.write(result + "\n")
    except Exception as exc:
        logger.error("IndicConformer standalone test failed: %s", exc)
        sys.exit(1)
