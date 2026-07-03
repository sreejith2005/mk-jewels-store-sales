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


def score_dict(overall_base: int = 7):
    return {
        "greeting_score": overall_base,
        "product_knowledge_score": overall_base,
        "objection_handling_score": overall_base,
        "missed_oppurtuinity": overall_base,
        "upsell_score": overall_base,
        "closing_score": overall_base,
        "customer_satisfaction": "Positive",
        "score_reasoning": "Strong discovery and clear next steps.",
    }


def create_store(db, name="Bandra", slug="bandra"):
    with db._lock:
        db._connection.execute(
            """
            INSERT INTO stores (name, slug, created_at)
            VALUES (?, ?, ?)
            """,
            (name, slug, db._utc_now()),
        )
        store_id = db._connection.execute(
            "SELECT id FROM stores WHERE slug = ?",
            (slug,),
        ).fetchone()["id"]
        db._connection.commit()
    return store_id


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


def test_log_event_stores_raw_and_display_transcripts(db):
    session_id = db.create_session("Maya")
    event = event_dict()
    event["transcript"] = "Mujhe aapki service bilkul pasand nahi hai"
    event["raw_transcript"] = "मुझे आपकी सर्विस बिल्कुल पसंद नहीं है"
    event["display_transcript"] = "Mujhe aapki service bilkul pasand nahi hai"
    event["triage_status"] = "ok"

    db.log_event(session_id, "Maya", event)
    stored = db.get_session_events(session_id)[0]

    assert stored["raw_transcript"] == "मुझे आपकी सर्विस बिल्कुल पसंद नहीं है"
    assert stored["display_transcript"] == "Mujhe aapki service bilkul pasand nahi hai"
    assert stored["transcript"] == "Mujhe aapki service bilkul pasand nahi hai"
    assert stored["triage_status"] == "ok"


def test_get_session_events_falls_back_to_raw_transcript(db):
    with db._lock:
        db._connection.execute(
            """
            INSERT INTO events (
                session_id,
                salesperson_name,
                timestamp,
                transcript,
                raw_transcript,
                display_transcript,
                objection_detected,
                price_concern,
                certification_question,
                upsell_miss,
                knowledge_gap,
                intent_signal,
                alert_priority,
                reasoning
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "fallback-session",
                "Maya",
                db._utc_now(),
                "",
                "मुझे अच्छा लगा",
                "",
                0,
                0,
                0,
                0,
                0,
                0,
                "none",
                "legacy row",
            ),
        )
        db._connection.commit()

    stored = db.get_session_events("fallback-session")[0]

    assert stored["raw_transcript"] == "मुझे अच्छा लगा"
    assert stored["display_transcript"] == "मुझे अच्छा लगा"
    assert stored["transcript"] == "मुझे अच्छा लगा"


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


def test_salesperson_pin_is_hashed_and_verified(db):
    with db._lock:
        db._connection.execute(
            """
            INSERT INTO stores (name, slug, created_at)
            VALUES (?, ?, ?)
            """,
            ("Bandra", "bandra", db._utc_now()),
        )
        store_id = db._connection.execute(
            "SELECT id FROM stores WHERE slug = ?",
            ("bandra",),
        ).fetchone()["id"]
        cursor = db._connection.execute(
            """
            INSERT INTO salespersons (store_id, name, designation, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (store_id, "Maya", "Sales Executive", db._utc_now()),
        )
        salesperson_id = cursor.lastrowid
        db._connection.commit()

    assert db.verify_salesperson_pin(salesperson_id, "1234") is False
    assert db.set_salesperson_pin(salesperson_id, "1234") is True
    assert db.verify_salesperson_pin(salesperson_id, "1234") is True
    assert db.verify_salesperson_pin(salesperson_id, "0000") is False

    with db._lock:
        pin_hash = db._connection.execute(
            "SELECT pin_hash FROM salespersons WHERE id = ?",
            (salesperson_id,),
        ).fetchone()["pin_hash"]

    assert pin_hash != "1234"
    assert pin_hash.startswith("$2")


def test_close_session_sets_end_time(db):
    session_id = db.create_session("Maya")

    db.close_session(session_id)

    with sqlite3.connect(db.db_path) as connection:
        end_time = connection.execute(
            "SELECT end_time FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()[0]

    assert end_time is not None


def test_delete_session_removes_session_and_events(db):
    session_id = db.create_session("Maya")
    db.log_event(session_id, "Maya", event_dict())
    db.log_event(session_id, "Maya", event_dict())

    deleted = db.delete_session(session_id)

    assert deleted is True
    assert db.get_session_events(session_id) == []

    with sqlite3.connect(db.db_path) as connection:
        session_count = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()[0]
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]

    assert session_count == 0
    assert event_count == 0


def test_delete_session_returns_false_for_missing_session(db):
    assert db.delete_session("missing-session") is False


def test_get_session_events_returns_empty_after_delete_session(db):
    session_id = db.create_session("Maya")
    db.log_event(session_id, "Maya", event_dict())

    assert len(db.get_session_events(session_id)) == 1

    db.delete_session(session_id)

    assert db.get_session_events(session_id) == []


def test_save_session_score_and_get_session_score(db):
    session_id = db.create_session("Maya")

    saved = db.save_session_score(
        session_id=session_id,
        salesperson_name="Maya",
        store_name="Bandra",
        scores_dict=score_dict(8),
    )
    score = db.get_session_score(session_id)

    assert saved is True
    assert score is not None
    assert score["session_id"] == session_id
    assert score["salesperson_name"] == "Maya"
    assert score["greeting_score"] == 8
    assert score["overall_score"] == 8.0
    assert score["customer_satisfaction"] == "Positive"


def test_get_salesperson_scores_returns_correct_rows(db):
    maya_session = db.create_session("Maya")
    riya_session = db.create_session("Riya")
    db.save_session_score(maya_session, "Maya", "Bandra", score_dict(8))
    db.save_session_score(riya_session, "Riya", "Bandra", score_dict(6))

    scores = db.get_salesperson_scores("Maya", days=30)

    assert len(scores) == 1
    assert scores[0]["session_id"] == maya_session
    assert scores[0]["overall_score"] == 8.0


def test_get_store_leaderboard_returns_correct_ranking(db):
    store_id = create_store(db, name="Bandra", slug="bandra")
    maya_session = db.create_session("Maya", store_id=store_id)
    riya_session = db.create_session("Riya", store_id=store_id)
    db.save_session_score(maya_session, "Maya", "Bandra", score_dict(9))
    db.save_session_score(riya_session, "Riya", "Bandra", score_dict(6))

    leaderboard = db.get_store_leaderboard(store_id)

    assert [row["name"] for row in leaderboard] == ["Maya", "Riya"]
    assert leaderboard[0]["avg_overall"] == 9.0
    assert leaderboard[0]["session_count"] == 1
