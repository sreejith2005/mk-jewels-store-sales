import io
import os
import sys
from collections import defaultdict

import numpy as np
import scipy.io.wavfile as wavfile


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from core.exceptions import STTError
from core.logger import get_logger


logger = get_logger(__name__)

MODEL_ID = "pyannote/speaker-diarization-3.1"
_pipeline = None


def _get_pipeline() -> object:
    """Load and cache the pyannote diarization pipeline."""
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    if not Config.HUGGINGFACE_TOKEN:
        raise STTError("HUGGINGFACE_TOKEN is required when diarization is enabled")

    try:
        import torch
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(
            MODEL_ID,
            use_auth_token=Config.HUGGINGFACE_TOKEN,
        )
        if torch.cuda.is_available() and Config.DEVICE == "cuda":
            pipeline.to(torch.device("cuda"))
        _pipeline = pipeline
        logger.info("Diarization pipeline loaded: %s", MODEL_ID)
        return _pipeline
    except Exception as exc:
        raise STTError(f"Failed to load diarization pipeline: {exc}") from exc


def _pcm_bytes_to_float32(audio_bytes: bytes) -> np.ndarray:
    """Convert raw int16 PCM bytes to normalized mono float32 samples."""
    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    return (audio.astype(np.float32) / 32768.0).clip(-1.0, 1.0)


def diarize(audio_bytes: bytes, sample_rate: int) -> list[dict]:
    """
    Run speaker diarization on raw int16 PCM bytes.

    Returns sorted segments with speaker label and start/end seconds.
    """
    if not audio_bytes:
        return []

    try:
        audio = _pcm_bytes_to_float32(audio_bytes)
        if audio.size == 0 or not np.any(audio):
            return []

        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, sample_rate, audio)
        wav_buffer.seek(0)

        import torch

        pipeline = _get_pipeline()
        waveform = torch.from_numpy(audio).unsqueeze(0)
        diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate})

        min_seconds = Config.MIN_SPEAKER_SEGMENT_SECONDS
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            start = float(turn.start)
            end = float(turn.end)
            if end - start < min_seconds:
                continue
            segments.append({"speaker": speaker, "start": start, "end": end})

        return sorted(segments, key=lambda segment: segment["start"])
    except STTError:
        raise
    except Exception as exc:
        raise STTError(f"Diarization failed: {exc}") from exc


def extract_speaker_audio(
    audio_bytes: bytes,
    sample_rate: int,
    segments: list[dict],
    speaker_label: str,
) -> bytes:
    """
    Extract and concatenate raw int16 PCM frames for a diarized speaker label.
    """
    if not audio_bytes or not segments:
        return b""

    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    chunks = []

    for segment in segments:
        if segment.get("speaker") != speaker_label:
            continue

        start_frame = max(0, int(float(segment["start"]) * sample_rate))
        end_frame = min(audio.size, int(float(segment["end"]) * sample_rate))
        if end_frame > start_frame:
            chunks.append(audio[start_frame:end_frame])

    if not chunks:
        return b""

    return np.concatenate(chunks).astype(np.int16).tobytes()


def dominant_speaker(segments: list[dict]) -> str:
    """Return the speaker label with the most total speaking time."""
    if not segments:
        return ""

    durations: dict[str, float] = defaultdict(float)
    for segment in segments:
        speaker = str(segment["speaker"])
        durations[speaker] += float(segment["end"]) - float(segment["start"])

    return max(durations, key=durations.get)
