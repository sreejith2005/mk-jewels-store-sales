import os
import sys

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


def _load_model() -> tuple[object, object]:
    """Load the IndicConformer processor and CTC model."""
    try:
        import torch
        from transformers import AutoModelForCTC, AutoProcessor

        processor = AutoProcessor.from_pretrained(MODEL_ID)
        model = AutoModelForCTC.from_pretrained(MODEL_ID)
        model.to(Config.DEVICE)
        model.eval()
        logger.info("IndicConformer model loaded on %s", Config.DEVICE)
        return processor, model
    except Exception as exc:
        raise STTError(f"Failed to load IndicConformer model: {exc}") from exc


processor, model = _load_model()


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

        inputs = processor(
            audio,
            sampling_rate=TARGET_SAMPLE_RATE,
            return_tensors="pt",
        )
        input_values = inputs.input_values.to(Config.DEVICE)

        with torch.no_grad():
            logits = model(input_values).logits

        predicted_ids = torch.argmax(logits, dim=-1)
        transcript = processor.batch_decode(predicted_ids)[0]
        return transcript.strip()
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
        logger.error("Usage: python transcription/indic_conformer_stt.py <audio_file.wav>")
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
