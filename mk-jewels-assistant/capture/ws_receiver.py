import asyncio
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Optional
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alerting.console_alert import AlertManager
from config import Config
from pipeline.session import Session
from storage.db import Database
from transcription.gemini_stt import GeminiAPIError, transcribe_and_triage


class _DirectAudioSession(Session):
    def __init__(self, salesperson_name: str):
        self.salesperson_name = salesperson_name
        self.device_index = None
        self.on_event = None
        self.db = Database()
        self.session_id = self.db.create_session(salesperson_name)
        self.alert_manager = AlertManager()

        self.events = []
        self.transcript_log = []

        self._stop_event = threading.Event()
        self._thread = None
        self._pending = set()
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._closed = False

    def start(self):
        self._stop_event.clear()

    def stop(self):
        if self._closed:
            return

        self._closed = True
        self._stop_event.set()
        self._collect_completed(self._pending)

        for future in self._pending:
            future.cancel()

        self._executor.shutdown(wait=False, cancel_futures=True)
        self.db.close_session(self.session_id)
        self.db.close()

    def submit_audio_chunk(self, audio_bytes: bytes):
        if self._stop_event.is_set():
            return

        self._collect_completed(self._pending)
        future = self._executor.submit(
            transcribe_and_triage,
            audio_bytes=audio_bytes,
            sample_rate=Config.SAMPLE_RATE,
            salesperson_name=self.salesperson_name,
        )
        self._pending.add(future)

    def has_backpressure(self) -> bool:
        self._collect_completed(self._pending)
        return len(self._pending) >= 3

    def has_pending(self) -> bool:
        self._collect_completed(self._pending)
        return bool(self._pending)

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
            print(f"Gemini API error for {self.salesperson_name}: {error}")
            return

        self.events.append(event)
        self.transcript_log.append(event.get("transcript", ""))
        self.db.log_event(self.session_id, self.salesperson_name, event)

        if self.alert_manager.should_alert(event):
            self.alert_manager.send_alert(self.salesperson_name, event)


class WebSocketAudioServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.chunk_size_bytes = Config.SAMPLE_RATE * 2 * Config.CHUNK_DURATION_SECONDS

    async def start(self):
        async with serve(self._handle_connection, self.host, self.port):
            print(f"WebSocket audio server listening on {self.host}:{self.port}")
            await asyncio.Future()

    async def _handle_connection(self, websocket):
        salesperson_name = self._salesperson_name_from_path(websocket.request.path)
        if not salesperson_name:
            await websocket.close(code=1008, reason="Missing name query parameter")
            return

        session = _DirectAudioSession(salesperson_name)
        session.start()
        buffer = bytearray()

        try:
            async for message in websocket:
                if isinstance(message, str):
                    await websocket.close(code=1003, reason="Expected raw PCM audio bytes")
                    break

                buffer.extend(message)

                while len(buffer) >= self.chunk_size_bytes:
                    while session.has_backpressure():
                        await asyncio.sleep(0.1)

                    chunk = bytes(buffer[: self.chunk_size_bytes])
                    del buffer[: self.chunk_size_bytes]
                    session.submit_audio_chunk(chunk)

        except ConnectionClosed:
            pass
        finally:
            while session.has_pending():
                await asyncio.sleep(0.1)
            session.stop()

    def _salesperson_name_from_path(self, path: str) -> Optional[str]:
        query = parse_qs(urlparse(path).query)
        names = query.get("name", [])
        if not names:
            return None

        name = names[0].strip()
        if not name:
            return None

        return name[:100]


def start_server():
    server = WebSocketAudioServer()
    asyncio.run(server.start())
