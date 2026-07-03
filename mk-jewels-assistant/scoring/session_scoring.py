from __future__ import annotations

from typing import Any

from core.exceptions import TriageError
from core.logger import get_logger
from storage.db import Database
from triage.qwen3_triage import score_session


logger = get_logger(__name__)


def generate_and_save_session_score(
    session_id: str,
    db: Database | None = None,
) -> dict[str, Any] | None:
    owns_db = db is None
    database = db or Database()

    try:
        events = database.get_session_events(session_id)
        if not events:
            logger.info("Skipping score generation for %s: no events.", session_id)
            return None

        transcripts = [
            str(event.get("transcript", "")).strip()
            for event in events
            if str(event.get("transcript", "")).strip()
        ]
        if not transcripts:
            logger.info("Skipping score generation for %s: no transcript text.", session_id)
            return None

        salesperson_name = str(events[0].get("salesperson_name") or "Unknown")
        store_name = _store_name_for_session(database, session_id) or "MK Jewels"
        scores = score_session("\n".join(transcripts), salesperson_name)
        database.save_session_score(
            session_id=session_id,
            salesperson_name=salesperson_name,
            store_name=store_name,
            scores_dict=scores,
        )
        return database.get_session_score(session_id)
    except TriageError:
        raise
    except Exception:
        logger.exception("Failed to generate session score for %s.", session_id)
        raise
    finally:
        if owns_db:
            database.close()


def _store_name_for_session(database: Database, session_id: str) -> str | None:
    sessions = database.get_recent_sessions(limit=500)
    for session in sessions:
        if session.get("session_id") == session_id:
            return database.get_store_name(session.get("store_id"))
    return None
