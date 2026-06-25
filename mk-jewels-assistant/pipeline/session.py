import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Callable, Optional

import numpy as np
from scipy.io import wavfile


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alerting.console_alert import AlertManager
from capture.mic_capture import MicCapture
from config import Config
from core.logger import get_logger
from storage.db import Database
from transcription.gemini_stt import GeminiAPIError


logger = get_logger(__name__)


def _load_triage_fn():
    if Config.PIPELINE_MODE == "demo":
        from transcription.gemini_stt import transcribe_and_triage

        return transcribe_and_triage

    if Config.PIPELINE_MODE == "production":
        try:
            from transcription.local_pipeline import transcribe_and_triage
        except ImportError:
            logger.error("local_pipeline not found, falling back to gemini_stt")
            from transcription.gemini_stt import transcribe_and_triage

        return transcribe_and_triage

    from transcription.gemini_stt import transcribe_and_triage

    return transcribe_and_triage


TRIAGE_FN = _load_triage_fn()


class Session:
    def __init__(
        self,
        salesperson_name: str,
        device_index: int,
        on_event: Optional[Callable[[str, dict], None]] = None,
        store_name: str = "MK Jewels",
    ):
        self.salesperson_name = salesperson_name
        self.device_index = device_index
        self.on_event = on_event
        self.store_name = store_name
        self.db = Database()
        self.session_id = self.db.create_session(salesperson_name)
        self.alert_manager = AlertManager()

        self.mic_capture = MicCapture(
            device_index=device_index,
            salesperson_name=salesperson_name,
        )
        self.events = []
        self.transcript_log = []

        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self.mic_capture.start()
        self._thread = threading.Thread(target=self._transcription_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.mic_capture.stop()
        if self._thread:
            self._thread.join(timeout=2)
            if not self._thread.is_alive():
                self._thread = None
        self.db.close_session(self.session_id)

    def _transcription_loop(self):
        pending = set()
        executor = ThreadPoolExecutor(max_workers=3)

        try:
            while not self._stop_event.is_set():
                self._collect_completed(pending)

                if len(pending) >= 3:
                    self._collect_completed(pending, timeout=1)
                    continue

                chunk = self.mic_capture.get_chunk()
                if chunk is None:
                    continue

                future = executor.submit(
                    TRIAGE_FN,
                    audio_bytes=chunk,
                    sample_rate=self.mic_capture.sample_rate,
                    salesperson_name=self.salesperson_name,
                )
                pending.add(future)

            for future in pending:
                future.cancel()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _collect_completed(self, pending, timeout=0):
        if not pending:
            return

        try:
            completed = as_completed(list(pending), timeout=timeout)
            for future in completed:
                pending.remove(future)
                self._handle_future(future)
        except TimeoutError:
            return

    def _handle_future(self, future):
        try:
            event = future.result()
        except GeminiAPIError as error:
            logger.error("Gemini API error for %s: %s", self.salesperson_name, error)
            return

        self.events.append(event)
        self.transcript_log.append(event.get("transcript", ""))
        event_id = self.db.log_event(self.session_id, self.salesperson_name, event)

        if self.alert_manager.should_alert(event):
            self.alert_manager.send_alert(
                self.salesperson_name,
                event,
                store_name=self.store_name,
                event_id=event_id,
            )

        if self.on_event:
            self.on_event(self.salesperson_name, event)


class FileSession:
    def __init__(
        self,
        wav_file_path: str,
        salesperson_name: str,
        on_event: Optional[Callable[[str, dict], None]] = None,
        simulate_realtime: bool = False,
        store_name: str = "MK Jewels",
    ):
        self.wav_file_path = wav_file_path
        self.salesperson_name = salesperson_name
        self.on_event = on_event
        self.simulate_realtime = simulate_realtime
        self.store_name = store_name
        self.db = Database()
        self.session_id = self.db.create_session(salesperson_name)
        self.alert_manager = AlertManager()

        self.events = []
        self.transcript_log = []

        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._file_processing_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            if not self._thread.is_alive():
                self._thread = None
        self.db.close_session(self.session_id)

    def _file_processing_loop(self):
        try:
            sample_rate, audio_data = wavfile.read(self.wav_file_path)
        except Exception as error:
            logger.error("Failed to read WAV file '%s': %s", self.wav_file_path, error)
            return

        audio_data = self._prepare_audio(audio_data)
        chunk_size_samples = sample_rate * Config.CHUNK_DURATION_SECONDS
        pending = set()
        executor = ThreadPoolExecutor(max_workers=3)

        try:
            for start in range(0, len(audio_data), chunk_size_samples):
                if self._stop_event.is_set():
                    break

                self._collect_completed(pending)

                while len(pending) >= 3 and not self._stop_event.is_set():
                    self._collect_completed(pending, timeout=1)

                chunk = audio_data[start : start + chunk_size_samples]
                if chunk.size == 0:
                    continue

                future = executor.submit(
                    TRIAGE_FN,
                    audio_bytes=chunk.tobytes(),
                    sample_rate=sample_rate,
                    salesperson_name=self.salesperson_name,
                )
                pending.add(future)

                next_start = start + chunk_size_samples
                if self.simulate_realtime and next_start < len(audio_data):
                    time.sleep(Config.CHUNK_DURATION_SECONDS)

            while pending and not self._stop_event.is_set():
                self._collect_completed(pending, timeout=1)

            for future in pending:
                future.cancel()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _prepare_audio(self, audio_data):
        original_dtype = audio_data.dtype

        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        if original_dtype == np.int16:
            return np.clip(
                audio_data,
                np.iinfo(np.int16).min,
                np.iinfo(np.int16).max,
            ).astype(np.int16)

        if audio_data.dtype == np.int16:
            return audio_data

        if np.issubdtype(original_dtype, np.floating):
            audio_data = np.clip(audio_data, -1.0, 1.0)
            return (audio_data * np.iinfo(np.int16).max).astype(np.int16)

        if np.issubdtype(original_dtype, np.integer):
            max_abs = max(abs(np.iinfo(original_dtype).min), np.iinfo(original_dtype).max)
            audio_data = audio_data.astype(np.float32) / max_abs
            return (audio_data * np.iinfo(np.int16).max).astype(np.int16)

        return audio_data.astype(np.int16)

    def _collect_completed(self, pending, timeout=0):
        if not pending:
            return

        try:
            completed = as_completed(list(pending), timeout=timeout)
            for future in completed:
                pending.remove(future)
                self._handle_future(future)
        except TimeoutError:
            return

    def _handle_future(self, future):
        try:
            event = future.result()
        except GeminiAPIError as error:
            logger.error("Gemini API error for %s: %s", self.salesperson_name, error)
            return

        self.events.append(event)
        self.transcript_log.append(event.get("transcript", ""))
        event_id = self.db.log_event(self.session_id, self.salesperson_name, event)

        if self.alert_manager.should_alert(event):
            self.alert_manager.send_alert(
                self.salesperson_name,
                event,
                store_name=self.store_name,
                event_id=event_id,
            )

        if self.on_event:
            self.on_event(self.salesperson_name, event)
