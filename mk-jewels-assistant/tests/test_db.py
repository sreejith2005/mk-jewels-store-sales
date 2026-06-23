import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from storage.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "sessions.db"))
    try:
        yield database
    finally:
        database.close()


def event_dict():
    return {
        "transcript": "Customer compared prices.",
        "objection_detected": True,
        "price_concern": True,
        "certification_question": False,
        "upsell_miss": False,
        "knowledge_gap": False,
        "intent_signal": True,
        "alert_priority": "high",
        "reasoning": "Customer asked for a discount.",
    }


def test_create_session_returns_non_empty_uuid(db):
    session_id = db.create_session("Maya")

    assert session_id
    assert str(uuid.UUID(session_id)) == session_id


def test_log_event_then_get_session_events_returns_salesperson_name(db):
    session_id = db.create_session("Maya")

    db.log_event(session_id, "Maya", event_dict())
    events = db.get_session_events(session_id)

    assert len(events) == 1
    assert events[0]["salesperson_name"] == "Maya"


def test_get_today_events_excludes_yesterday(db):
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)

    with db._lock:
        db._connection.executemany(
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
            [
                (
                    "today-session",
                    "Maya",
                    today.isoformat(),
                    "Today event",
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    "none",
                    "Today",
                ),
                (
                    "yesterday-session",
                    "Maya",
                    yesterday.isoformat(),
                    "Yesterday event",
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    "none",
                    "Yesterday",
                ),
            ],
        )
        db._connection.commit()

    events = db.get_today_events("Maya")

    assert len(events) == 1
    assert events[0]["transcript"] == "Today event"


def test_delete_events_older_than_deletes_only_expired_rows(db):
    now = datetime.now(timezone.utc)
    old_timestamp = now - timedelta(days=8)
    recent_timestamp = now - timedelta(days=2)

    with db._lock:
        db._connection.executemany(
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
            [
                (
                    "old-session",
                    "Maya",
                    old_timestamp.isoformat(),
                    "Old event",
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    "none",
                    "Old",
                ),
                (
                    "recent-session",
                    "Maya",
                    recent_timestamp.isoformat(),
                    "Recent event",
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    "none",
                    "Recent",
                ),
            ],
        )
        db._connection.commit()

    deleted_count = db.delete_events_older_than(7)
    remaining_events = db.get_session_events("recent-session")

    assert deleted_count == 1
    assert len(remaining_events) == 1
    assert remaining_events[0]["transcript"] == "Recent event"


def test_save_feedback_updates_manager_feedback(db):
    session_id = db.create_session("Maya")
    db.log_event(session_id, "Maya", event_dict())
    event_id = db.get_session_events(session_id)[0]["id"]

    db.save_feedback(event_id, "useful")
    updated_event = db.get_session_events(session_id)[0]

    assert updated_event["manager_feedback"] == "useful"


def test_close_session_sets_end_time(db):
    session_id = db.create_session("Maya")

    db.close_session(session_id)

    with sqlite3.connect(db.db_path) as connection:
        end_time = connection.execute(
            "SELECT end_time FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()[0]

    assert end_time is not None
