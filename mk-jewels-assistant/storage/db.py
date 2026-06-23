import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from config import Config
from core.exceptions import DatabaseError
from core.logger import get_logger


logger = get_logger(__name__)


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or Config.DB_PATH
        self._lock = threading.Lock()
        self._backend = "postgres" if Config.POSTGRES_URL.strip() else "sqlite"
        self._pool = None
        logger.info("Database backend: %s", self._backend)

        if self._backend == "postgres":
            self._connection = None
            self._pool = self._create_postgres_pool()
        else:
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row

        self._create_tables()

    def _create_postgres_pool(self):
        try:
            from psycopg2 import pool
        except ImportError as exc:
            raise DatabaseError(
                "psycopg2-binary is required when POSTGRES_URL is configured."
            ) from exc

        try:
            return pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=Config.POSTGRES_URL,
            )
        except Exception as exc:
            raise DatabaseError("Failed to create Postgres connection pool.") from exc

    def _create_tables(self):
        if self._backend == "postgres":
            with self._lock:
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS sessions (
                                id TEXT PRIMARY KEY,
                                salesperson_name TEXT,
                                start_time TEXT,
                                end_time TEXT
                            )
                            """
                        )
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS events (
                                id SERIAL PRIMARY KEY,
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
                                reasoning TEXT,
                                manager_feedback TEXT DEFAULT NULL
                            )
                            """
                        )
                        cursor.execute(
                            """
                            DO $$
                            BEGIN
                                ALTER TABLE events
                                ADD COLUMN manager_feedback TEXT DEFAULT NULL;
                            EXCEPTION WHEN duplicate_column THEN
                                NULL;
                            END $$;
                            """
                        )
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS reports (
                                id SERIAL PRIMARY KEY,
                                salesperson_name TEXT,
                                date TEXT,
                                report_text TEXT,
                                created_at TEXT
                            )
                            """
                        )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to create database tables.") from exc
                finally:
                    self._pool.putconn(connection)
            return

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
                    reasoning TEXT,
                    manager_feedback TEXT DEFAULT NULL
                )
                """
            )
            try:
                self._connection.execute(
                    "ALTER TABLE events ADD COLUMN manager_feedback TEXT DEFAULT NULL"
                )
            except sqlite3.OperationalError:
                pass
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
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO sessions (id, salesperson_name, start_time, end_time)
                            VALUES (%s, %s, %s, NULL)
                            """,
                            (session_id, salesperson_name, start_time),
                        )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to create session.") from exc
                finally:
                    self._pool.putconn(connection)
                return session_id

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
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
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
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            values,
                        )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to log event.") from exc
                finally:
                    self._pool.putconn(connection)
                return

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
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE sessions
                            SET end_time = %s
                            WHERE id = %s
                            """,
                            (self._utc_now(), session_id),
                        )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to close session.") from exc
                finally:
                    self._pool.putconn(connection)
                return

            self._connection.execute(
                """
                UPDATE sessions
                SET end_time = ?
                WHERE id = ?
                """,
                (self._utc_now(), session_id),
            )
            self._connection.commit()

    def save_feedback(self, event_id: int, feedback: str):
        if feedback not in {"useful", "false_alarm", "noted"}:
            raise ValueError("Invalid feedback value")

        with self._lock:
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE events
                            SET manager_feedback = %s
                            WHERE id = %s
                            """,
                            (feedback, event_id),
                        )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to save manager feedback.") from exc
                finally:
                    self._pool.putconn(connection)
                return

            self._connection.execute(
                """
                UPDATE events
                SET manager_feedback = ?
                WHERE id = ?
                """,
                (feedback, event_id),
            )
            self._connection.commit()

    def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT *
                            FROM events
                            WHERE session_id = %s
                            ORDER BY timestamp ASC, id ASC
                            """,
                            (session_id,),
                        )
                        return self._rows_to_dicts(cursor.description, cursor.fetchall())
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to fetch session events.") from exc
                finally:
                    self._pool.putconn(connection)

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

    def get_recent_sessions(self, limit: int = 50) -> list[dict]:
        with self._lock:
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT DISTINCT salesperson_name, id as session_id, start_time
                            FROM sessions
                            ORDER BY start_time DESC
                            LIMIT %s
                            """,
                            (limit,),
                        )
                        return self._rows_to_dicts(cursor.description, cursor.fetchall())
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to fetch recent sessions.") from exc
                finally:
                    self._pool.putconn(connection)

            rows = self._connection.execute(
                """
                SELECT DISTINCT salesperson_name, id as session_id, start_time
                FROM sessions
                ORDER BY start_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_today_events(self, salesperson_name: str | None = None) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        with self._lock:
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        if salesperson_name:
                            cursor.execute(
                                """
                                SELECT *
                                FROM events
                                WHERE salesperson_name = %s
                                    AND timestamp >= %s
                                    AND timestamp < %s
                                ORDER BY timestamp ASC, id ASC
                                """,
                                (salesperson_name, start.isoformat(), end.isoformat()),
                            )
                        else:
                            cursor.execute(
                                """
                                SELECT *
                                FROM events
                                WHERE timestamp >= %s
                                    AND timestamp < %s
                                ORDER BY salesperson_name ASC, timestamp ASC, id ASC
                                """,
                                (start.isoformat(), end.isoformat()),
                            )
                        return self._rows_to_dicts(cursor.description, cursor.fetchall())
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to fetch today's events.") from exc
                finally:
                    self._pool.putconn(connection)

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

    def delete_events_older_than(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        with self._lock:
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM events WHERE timestamp < %s",
                            (cutoff,),
                        )
                        deleted_count = cursor.rowcount
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to delete old events.") from exc
                finally:
                    self._pool.putconn(connection)

                logger.info("Deleted %s events older than %s days.", deleted_count, days)
                return deleted_count

            cursor = self._connection.execute(
                "DELETE FROM events WHERE timestamp < ?",
                (cutoff,),
            )
            self._connection.commit()

        deleted_count = cursor.rowcount
        logger.info("Deleted %s events older than %s days.", deleted_count, days)
        return deleted_count

    def save_report(self, salesperson_name: str, report_text: str):
        created_at = self._utc_now()
        date = created_at[:10]

        with self._lock:
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO reports (salesperson_name, date, report_text, created_at)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (salesperson_name, date, report_text, created_at),
                        )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to save report.") from exc
                finally:
                    self._pool.putconn(connection)
                return

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
            if self._backend == "postgres":
                connection = self._pool.getconn()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT id, salesperson_name, date, report_text, created_at
                            FROM reports
                            WHERE salesperson_name = %s
                                AND date >= %s
                            ORDER BY date DESC, created_at DESC, id DESC
                            """,
                            (salesperson_name, start_date),
                        )
                        return self._rows_to_dicts(cursor.description, cursor.fetchall())
                except Exception as exc:
                    connection.rollback()
                    raise DatabaseError("Failed to fetch recent reports.") from exc
                finally:
                    self._pool.putconn(connection)

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
            if self._backend == "postgres":
                if self._pool:
                    self._pool.closeall()
                return

            self._connection.close()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _as_int(value: Any) -> int:
        return int(bool(value))

    @staticmethod
    def _rows_to_dicts(description: Iterable[Any], rows: Iterable[tuple[Any, ...]]):
        columns = [column[0] for column in description]
        return [dict(zip(columns, row)) for row in rows]
