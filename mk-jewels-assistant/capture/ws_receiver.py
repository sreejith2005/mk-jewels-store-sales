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
from core.exceptions import PipelineError
from core.logger import get_logger
from pipeline.session import TRIAGE_FN, Session
from storage.db import Database
from transcription.gemini_stt import GeminiAPIError


logger = get_logger(__name__)


class _DirectAudioSession(Session):
    def __init__(
        self,
        salesperson_name: str,
        store_id: int | None = None,
        store_name: str = "MK Jewels",
    ):
        self.salesperson_name = salesperson_name
        self.store_id = store_id
        self.store_name = store_name
        self.device_index = None
        self.on_event = None
        self.db = Database()
        self.session_id = self.db.create_session(salesperson_name, store_id=store_id)
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
            TRIAGE_FN,
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
        except (GeminiAPIError, PipelineError) as error:
            logger.error("Pipeline error for %s: %s", self.salesperson_name, error)
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


class WebSocketAudioServer:
    def __init__(self, host: str = Config.WS_HOST, port: int = Config.WS_PORT):
        self.host = host
        self.port = port
        self.chunk_size_bytes = Config.SAMPLE_RATE * 2 * Config.CHUNK_DURATION_SECONDS

    async def start(self):
        async with serve(self._handle_connection, self.host, self.port):
            logger.info("WebSocket audio server listening on %s:%s", self.host, self.port)
            await asyncio.Future()

    async def _handle_connection(self, websocket):
        salesperson_name, store_id, store_name = self._session_context_from_path(
            websocket.request.path
        )
        if not salesperson_name:
            await websocket.close(code=1008, reason="Missing name query parameter")
            return

        session = _DirectAudioSession(
            salesperson_name,
            store_id=store_id,
            store_name=store_name,
        )
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

    def _session_context_from_path(self, path: str) -> tuple[Optional[str], int | None, str]:
        query = parse_qs(urlparse(path).query)
        names = query.get("name", [])
        if not names:
            return None, None, "MK Jewels"

        name = names[0].strip()
        if not name:
            return None, None, "MK Jewels"

        store_id = self._store_id_from_query(query)
        store_name = self._store_name_from_query(query, store_id)

        return name[:100], store_id, store_name

    def _store_id_from_query(self, query: dict[str, list[str]]) -> int | None:
        store_ids = query.get("store_id", [])
        if not store_ids:
            return None

        try:
            store_id = int(store_ids[0])
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid store_id from recorder connection.")
            return None

        return store_id if store_id > 0 else None

    def _store_name_from_query(
        self,
        query: dict[str, list[str]],
        store_id: int | None,
    ) -> str:
        store_names = query.get("store_name", [])
        if store_names and store_names[0].strip():
            return store_names[0].strip()[:100]

        if store_id is None:
            return "MK Jewels"

        db = Database()
        try:
            return db.get_store_name(store_id) or "MK Jewels"
        except Exception as error:
            logger.warning("Failed to resolve store name for store_id=%s: %s", store_id, error)
            return "MK Jewels"
        finally:
            db.close()



def start_server():
    server = WebSocketAudioServer()
    asyncio.run(server.start())
