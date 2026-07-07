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
DEFAULT_DECODING = "ctc"

_model = None
_model_debug_logged = False


def _language_preferences() -> list[str]:
    preferred = (Config.TRANSCRIPT_LANGUAGE or Config.INDIC_CONFORMER_LANGUAGE).lower()
    if preferred == "en":
        return ["en", "auto", "hi"]
    if preferred == "hi":
        return ["hi", "auto", "en"]
    return ["auto", "en", "hi"]


def _load_model() -> object:
    """Load and cache the custom IndicConformer model."""
    global _model, _model_debug_logged
    if _model is not None:
        return _model

    try:
        import torch
        from transformers import AutoModel

        if Config.DEVICE == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but unavailable; falling back to CPU")
            device = "cpu"
        else:
            device = Config.DEVICE

        token = Config.HUGGINGFACE_TOKEN.strip() or None
        model_kwargs = {"trust_remote_code": True}
        if token:
            model_kwargs["token"] = token

        model = AutoModel.from_pretrained(MODEL_ID, **model_kwargs)
        model.eval()
        _model = model
        logger.info("IndicConformer model loaded on %s", device)
        if not _model_debug_logged:
            logger.debug("IndicConformer model type: %s", type(model))
            logger.debug("IndicConformer model dir: %s", dir(model))
            _model_debug_logged = True
        return _model
    except Exception as exc:
        raise STTError(f"Failed to load IndicConformer model: {exc}") from exc


def _infer_transcript(stt_model: object, waveform: object) -> str:
    """Call IndicConformer with explicit language preference and safe fallbacks."""
    last_error = None
    for language in _language_preferences():
        try:
            logger.info("IndicConformer transcription language preference: %s", language)
            if hasattr(stt_model, "transcribe"):
                try:
                    return stt_model.transcribe(
                        waveform,
                        language=language,
                        decoding=DEFAULT_DECODING,
                    )
                except TypeError:
                    return stt_model.transcribe(waveform, language, DEFAULT_DECODING)
            return stt_model(waveform, language, DEFAULT_DECODING)
        except TypeError as exc:
            last_error = exc
            logger.warning(
                "IndicConformer rejected language=%s; trying next preference: %s",
                language,
                exc,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "IndicConformer transcription failed with language=%s; trying next preference: %s",
                language,
                exc,
            )

    raise STTError(f"IndicConformer transcription failed for all languages: {last_error}")


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
    Transcribe raw int16 PCM mono audio bytes using IndicConformer.
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
        stt_model = _load_model()

        with torch.no_grad():
            transcript = _infer_transcript(stt_model, waveform)

        if isinstance(transcript, (list, tuple)):
            transcript = " ".join(str(item) for item in transcript)
        return str(transcript).strip()
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
