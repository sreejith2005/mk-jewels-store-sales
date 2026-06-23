from __future__ import annotations

import hmac
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
DASHBOARD_ROOT = Path(__file__).resolve().parent

from config import Config  # noqa: E402
from storage.db import Database  # noqa: E402


app = Flask(__name__, static_folder=None)
CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000"])
db = Database()


@app.before_request
def require_dashboard_auth() -> Any:
    if request.method == "GET" and request.path == "/recorder":
        return None

    if not Config.DASHBOARD_AUTH_PASS:
        return None

    auth = request.authorization
    if (
        auth
        and hmac.compare_digest(auth.username or "", Config.DASHBOARD_AUTH_USER)
        and hmac.compare_digest(auth.password or "", Config.DASHBOARD_AUTH_PASS)
    ):
        return None

    return (
        jsonify({"error": "Authentication required"}),
        401,
        {"WWW-Authenticate": 'Basic realm="MK Jewels Dashboard"'},
    )


@app.get("/recorder")
def get_recorder():
    return send_file(DASHBOARD_ROOT / "recorder.html")


@app.get("/api/sessions")
def get_today_sessions():
    with db._lock:
        rows = db._connection.execute(
            """
            SELECT DISTINCT salesperson_name, id as session_id, start_time
            FROM sessions
            ORDER BY start_time DESC
            LIMIT 50
            """
        ).fetchall()

    return jsonify(
        [
            {
                "salesperson_name": row["salesperson_name"],
                "session_id": row["session_id"],
                "start_time": row["start_time"],
            }
            for row in rows
        ]
    )


@app.get("/api/debug")
def get_debug_counts():
    with db._lock:
        session_count = db._connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        event_count = db._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    return jsonify({"sessions": session_count, "events": event_count})


@app.get("/api/events/<session_id>")
def get_events(session_id: str):
    events = db.get_session_events(session_id)
    events.sort(key=lambda event: (event.get("timestamp", ""), event.get("id", 0)), reverse=True)
    return jsonify(events)


@app.post("/api/feedback/<int:event_id>")
def save_feedback(event_id: int):
    data = request.get_json(silent=True) or {}
    feedback = data.get("feedback")
    if feedback not in {"useful", "false_alarm", "noted"}:
        return jsonify({"error": "Invalid feedback"}), 400

    db.save_feedback(event_id, feedback)
    return jsonify({"status": "ok"})


@app.get("/api/stats/<session_id>")
def get_stats(session_id: str):
    events = db.get_session_events(session_id)

    summary: dict[str, Any] = {
        "total_events": len(events),
        "alerts_fired": sum(1 for event in events if event.get("alert_priority") in {"medium", "high"}),
        "objections": _count_flag(events, "objection_detected"),
        "price_concerns": _count_flag(events, "price_concern"),
        "certification_questions": _count_flag(events, "certification_question"),
        "upsell_misses": _count_flag(events, "upsell_miss"),
        "high_intent_signals": _count_flag(events, "intent_signal"),
    }

    return jsonify(summary)


@app.get("/api/reports/<salesperson_name>")
def get_reports(salesperson_name: str):
    return jsonify(db.get_recent_reports(salesperson_name, days=7))


def _count_flag(events: list[dict[str, Any]], key: str) -> int:
    return sum(1 for event in events if bool(event.get(key)))


# DEVELOPMENT ONLY — do not use for production
# Production: gunicorn -c dashboard/gunicorn_config.py dashboard.server:app
# Or set PIPELINE_MODE=production in .env — main.py handles the switch
if __name__ == "__main__":
    app.run(port=5000)
