import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

from config import Config


class MicCapture:
    def __init__(
        self,
        device_index: Optional[int] = None,
        sample_rate: Optional[int] = None,
        chunk_duration_seconds: Optional[int] = None,
        salesperson_name: str = "",
    ):
        self.device_index = device_index
        self.sample_rate = sample_rate or Config.SAMPLE_RATE
        self.chunk_duration_seconds = (
            chunk_duration_seconds or Config.CHUNK_DURATION_SECONDS
        )
        self.salesperson_name = salesperson_name
        self.silence_threshold = Config.SILENCE_THRESHOLD

        self._chunk_queue = queue.Queue()
        self._buffer = bytearray()
        self._buffer_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._bytes_per_sample = np.dtype(np.int16).itemsize
        self._chunk_size_bytes = (
            self.sample_rate
            * self.chunk_duration_seconds
            * self._bytes_per_sample
        )

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def get_chunk(self):
        try:
            return self._chunk_queue.get(timeout=1)
        except queue.Empty:
            return None

    @staticmethod
    def list_devices():
        devices = sd.query_devices()
        for index, device in enumerate(devices):
            if device.get("max_input_channels", 0) > 0:
                print(
                    f"{index}: {device['name']} "
                    f"({device['max_input_channels']} input channels)"
                )

    def _capture_loop(self):
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device_index,
            callback=self._audio_callback,
        ):
            while not self._stop_event.is_set():
                sd.sleep(100)

    def _audio_callback(self, indata, frames, time, status):
        del frames, time

        if status:
            print(status)

        with self._buffer_lock:
            self._buffer.extend(indata.tobytes())

            while len(self._buffer) >= self._chunk_size_bytes:
                chunk = bytes(self._buffer[: self._chunk_size_bytes])
                del self._buffer[: self._chunk_size_bytes]

                if self._is_speech(chunk):
                    self._chunk_queue.put(chunk)

    def _is_speech(self, chunk: bytes) -> bool:
        audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if audio.size == 0:
            return False

        rms = np.sqrt(np.mean(np.square(audio)))
        return rms > self.silence_threshold
