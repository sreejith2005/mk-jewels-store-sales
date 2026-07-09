import asyncio
import json
import os
import sys
import threading
import re
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
from core.readiness import is_ready
from pipeline.session import TRIAGE_FN, Session
from scoring.session_scoring import generate_and_save_session_score
from storage.db import Database
from transcription.gemini_stt import GeminiAPIError


logger = get_logger(__name__)


def _tokenize_transcript(text: str) -> list[str]:
    return re.findall(r"\S+", str(text or "").strip())


def strip_transcript_overlap(previous_text: str, current_text: str, max_words: int = 12) -> str:
    previous_words = _tokenize_transcript(previous_text)
    current_words = _tokenize_transcript(current_text)
    if not previous_words or not current_words:
        return str(current_text or "").strip()

    max_overlap = min(len(previous_words), len(current_words), max_words)
    previous_lower = [word.casefold() for word in previous_words]
    current_lower = [word.casefold() for word in current_words]

    for size in range(max_overlap, 0, -1):
        if previous_lower[-size:] == current_lower[:size]:
            return " ".join(current_words[size:])

    return " ".join(current_words)


def prepend_audio_overlap(previous_tail: bytes, chunk_body: bytes) -> bytes:
    return bytes(previous_tail) + bytes(chunk_body)


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
        self._future_sequences = {}
        self._completed_events = {}
        self._next_sequence = 0
        self._next_event_sequence = 0
        self._last_transcripts = {
            "transcript": "",
            "raw_transcript": "",
            "display_transcript": "",
        }
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
        self._queue_score_generation()
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
        self._future_sequences[future] = self._next_sequence
        self._next_sequence += 1

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
                self._collect_future_result(future)
        except TimeoutError:
            return

        self._drain_completed_events()

    def _collect_future_result(self, future):
        sequence = self._future_sequences.pop(future, None)
        if sequence is None:
            return

        try:
            event = future.result()
        except (GeminiAPIError, PipelineError) as error:
            logger.error("Pipeline error for %s: %s", self.salesperson_name, error)
            self._completed_events[sequence] = None
            return

        self._completed_events[sequence] = event

    def _drain_completed_events(self):
        while self._next_event_sequence in self._completed_events:
            event = self._completed_events.pop(self._next_event_sequence)
            self._next_event_sequence += 1
            if event is None:
                continue
            self._handle_event(event)

    def _handle_event(self, event):
        self._deduplicate_event_transcripts(event)
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

    def log_recorder_event(self, event_type: str, detail: str, metadata: dict | None = None):
        safe_type = re.sub(r"[^a-zA-Z0-9_:-]", "_", str(event_type or "recorder_event"))[:80]
        safe_detail = str(detail or "Recorder lifecycle event.")[:500]
        metadata = metadata if isinstance(metadata, dict) else {}
        event = {
            "transcript": safe_detail,
            "raw_transcript": safe_detail,
            "display_transcript": safe_detail,
            "triage_status": f"recorder:{safe_type}",
            "objection_detected": False,
            "price_concern": False,
            "certification_question": False,
            "upsell_miss": False,
            "knowledge_gap": False,
            "intent_signal": False,
            "alert_priority": "none",
            "reasoning": json.dumps(
                {
                    "event_type": safe_type,
                    "metadata": metadata,
                },
                ensure_ascii=True,
                default=str,
            )[:1000],
        }
        self.db.log_event(self.session_id, self.salesperson_name, event)
        logger.info(
            "Recorder event for session=%s salesperson=%s type=%s detail=%s metadata=%s",
            self.session_id,
            self.salesperson_name,
            safe_type,
            safe_detail,
            metadata,
        )

    def _deduplicate_event_transcripts(self, event: dict):
        for field in ("raw_transcript", "display_transcript", "transcript"):
            current = str(event.get(field) or "")
            if not current:
                continue

            cleaned = strip_transcript_overlap(self._last_transcripts.get(field, ""), current)
            event[field] = cleaned
            self._last_transcripts[field] = cleaned or current

    def _queue_score_generation(self):
        threading.Thread(
            target=self._generate_score_safely,
            daemon=True,
        ).start()

    def _generate_score_safely(self):
        try:
            generate_and_save_session_score(self.session_id)
        except Exception as error:
            logger.warning(
                "Background score generation failed for %s: %s",
                self.session_id,
                error,
            )


class WebSocketAudioServer:
    def __init__(self, host: str = Config.WS_HOST, port: int = Config.WS_PORT):
        self.host = host
        self.port = port
        self.chunk_size_bytes = Config.SAMPLE_RATE * 2 * Config.CHUNK_DURATION_SECONDS
        self.overlap_size_bytes = int(Config.SAMPLE_RATE * 2 * Config.OVERLAP_SECONDS)

    async def start(self):
        async with serve(self._handle_connection, self.host, self.port):
            logger.info("WebSocket audio server listening on %s:%s", self.host, self.port)
            await asyncio.Future()

    async def _handle_connection(self, websocket):
        if not is_ready():
            await websocket.send(
                json.dumps(
                    {
                        "type": "not_ready",
                        "message": (
                            "Server is loading models, please wait and reconnect "
                            "in 30 seconds"
                        ),
                    }
                )
            )
            await websocket.close()
            return

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
        previous_tail = b""

        try:
            async for message in websocket:
                if isinstance(message, str):
                    self._handle_text_message(message, session)
                    continue

                buffer.extend(message)

                while len(buffer) >= self.chunk_size_bytes:
                    while session.has_backpressure():
                        await asyncio.sleep(0.1)

                    chunk_body = bytes(buffer[: self.chunk_size_bytes])
                    chunk = prepend_audio_overlap(previous_tail, chunk_body)
                    previous_tail = chunk_body[-self.overlap_size_bytes :] if self.overlap_size_bytes > 0 else b""
                    del buffer[: self.chunk_size_bytes]
                    session.submit_audio_chunk(chunk)

        except ConnectionClosed:
            pass
        finally:
            while session.has_pending():
                await asyncio.sleep(0.1)
            session.stop()

    def _handle_text_message(self, message: str, session: _DirectAudioSession):
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("Ignoring non-JSON recorder text message for %s.", session.salesperson_name)
            return

        if payload.get("type") == "recorder_event":
            event_type = str(payload.get("event_type") or "recorder_event")
            detail = str(payload.get("detail") or "Recorder lifecycle event.")
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            metadata["client_timestamp"] = payload.get("timestamp")
            session.log_recorder_event(event_type, detail, metadata)
            return

        if payload.get("type") != "capture_settings":
            logger.warning("Ignoring unknown recorder message type: %s", payload.get("type"))
            return

        logger.info(
            "Recorder capture settings for %s: audioContext.sampleRate=%s, trackSettings=%s",
            session.salesperson_name,
            payload.get("audioContextSampleRate"),
            payload.get("trackSettings"),
        )

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
