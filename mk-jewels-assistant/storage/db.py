import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from config import Config


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or Config.DB_PATH
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    salesperson_name TEXT,
                    start_time TEXT,
                    end_time TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    salesperson_name TEXT,
                    timestamp TEXT,
                    transcript TEXT,
                    objection_detected INTEGER,
                    price_concern INTEGER,
                    certification_question INTEGER,
                    upsell_miss INTEGER,
                    knowledge_gap INTEGER,
                    intent_signal INTEGER,
                    alert_priority TEXT,
                    reasoning TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    salesperson_name TEXT,
                    date TEXT,
                    report_text TEXT,
                    created_at TEXT
                )
                """
            )
            self._connection.commit()

    def create_session(self, salesperson_name: str) -> str:
        session_id = str(uuid.uuid4())
        start_time = self._utc_now()

        with self._lock:
            self._connection.execute(
                """
                INSERT INTO sessions (id, salesperson_name, start_time, end_time)
                VALUES (?, ?, ?, NULL)
                """,
                (session_id, salesperson_name, start_time),
            )
            self._connection.commit()

        return session_id

    def log_event(self, session_id: str, salesperson_name: str, event_dict: dict[str, Any]):
        values = (
            session_id,
            salesperson_name,
            self._utc_now(),
            event_dict.get("transcript", ""),
            self._as_int(event_dict.get("objection_detected")),
            self._as_int(event_dict.get("price_concern")),
            self._as_int(event_dict.get("certification_question")),
            self._as_int(event_dict.get("upsell_miss")),
            self._as_int(event_dict.get("knowledge_gap")),
            self._as_int(event_dict.get("intent_signal")),
            event_dict.get("alert_priority", "none"),
            event_dict.get("reasoning", ""),
        )

        with self._lock:
            self._connection.execute(
                """
                INSERT INTO events (
                    session_id,
                    salesperson_name,
                    timestamp,
                    transcript,
                    objection_detected,
                    price_concern,
                    certification_question,
                    upsell_miss,
                    knowledge_gap,
                    intent_signal,
                    alert_priority,
                    reasoning
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            self._connection.commit()

    def close_session(self, session_id: str):
        with self._lock:
            self._connection.execute(
                """
                UPDATE sessions
                SET end_time = ?
                WHERE id = ?
                """,
                (self._utc_now(), session_id),
            )
            self._connection.commit()

    def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT *
                FROM events
                WHERE session_id = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (session_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_today_events(self, salesperson_name: str | None = None) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        with self._lock:
            if salesperson_name:
                rows = self._connection.execute(
                    """
                    SELECT *
                    FROM events
                    WHERE salesperson_name = ?
                        AND timestamp >= ?
                        AND timestamp < ?
                    ORDER BY timestamp ASC, id ASC
                    """,
                    (salesperson_name, start.isoformat(), end.isoformat()),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT *
                    FROM events
                    WHERE timestamp >= ?
                        AND timestamp < ?
                    ORDER BY salesperson_name ASC, timestamp ASC, id ASC
                    """,
                    (start.isoformat(), end.isoformat()),
                ).fetchall()

        return [dict(row) for row in rows]

    def save_report(self, salesperson_name: str, report_text: str):
        created_at = self._utc_now()
        date = created_at[:10]

        with self._lock:
            self._connection.execute(
                """
                INSERT INTO reports (salesperson_name, date, report_text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (salesperson_name, date, report_text, created_at),
            )
            self._connection.commit()

    def get_recent_reports(self, salesperson_name: str, days: int = 7) -> list[dict[str, Any]]:
        start_date = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, salesperson_name, date, report_text, created_at
                FROM reports
                WHERE salesperson_name = ?
                    AND date >= ?
                ORDER BY date DESC, created_at DESC, id DESC
                """,
                (salesperson_name, start_date),
            ).fetchall()

        return [dict(row) for row in rows]

    def close(self):
        with self._lock:
            self._connection.close()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _as_int(value: Any) -> int:
        return int(bool(value))
