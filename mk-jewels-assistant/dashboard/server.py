from __future__ import annotations

import hmac
import os
import re
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
DASHBOARD_ROOT = Path(__file__).resolve().parent

from alerting.console_alert import AlertManager  # noqa: E402
from config import Config  # noqa: E402
from core.logger import get_logger  # noqa: E402
from storage.db import Database  # noqa: E402


app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app, origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","))
db = Database()
logger = get_logger(__name__)
PIN_PATTERN = re.compile(r"^\d{4}$")


@app.before_request
def require_dashboard_auth() -> Any:
    if request.method == "GET" and request.path == "/recorder":
        return None
    if request.method == "GET" and request.path.startswith("/static/"):
        return None
    if request.method == "POST" and request.path in {
        "/api/auth/salesperson",
        "/api/auth/salesperson/set-first-pin",
    }:
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


@app.get("/static/sw.js")
def get_service_worker():
    response = send_file(
        DASHBOARD_ROOT / "static" / "sw.js",
        mimetype="application/javascript",
    )
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.get("/api/sessions")
def get_today_sessions():
    store_id = request.args.get("store_id", type=int)
    sessions = db.get_recent_sessions(limit=500, store_id=store_id)
    for session in sessions:
        session["event_count"] = len(db.get_session_events(session["session_id"]))
    return jsonify(sessions)


@app.delete("/api/sessions/<session_id>")
def delete_session(session_id: str):
    deleted = db.delete_session(session_id)
    if not deleted:
        return jsonify({"success": False, "error": "Session not found"}), 404

    logger.info(
        "Deleted session %s at %s",
        session_id,
        db._utc_now(),
    )
    return jsonify({"success": True, "message": "Session deleted"})


@app.get("/api/stores")
def get_stores():
    return jsonify(db.get_stores())


@app.get("/api/stores/<int:store_id>/salespersons")
def get_store_salespersons(store_id: int):
    return jsonify(db.get_salespersons_with_pin_status(store_id))


@app.post("/api/auth/salesperson")
def authenticate_salesperson():
    data = request.get_json(silent=True) or {}
    salesperson_id = data.get("salesperson_id")
    pin = data.get("pin")

    if not isinstance(salesperson_id, int) or not isinstance(pin, str):
        return jsonify({"success": False, "error": "Invalid PIN"}), 401

    salesperson = db.get_salesperson(salesperson_id)
    if salesperson is None:
        return jsonify({"success": False, "error": "Invalid PIN"}), 401

    pin_set = db.salesperson_has_pin(salesperson_id)
    if pin_set is False:
        return jsonify({"success": False, "reason": "NO_PIN_SET"})

    if not db.verify_salesperson_pin(salesperson_id, pin):
        return jsonify({"success": False, "error": "Invalid PIN"}), 401

    return jsonify(
        {
            "success": True,
            "salesperson_id": salesperson["id"],
            "name": salesperson["name"],
            "store_id": salesperson["store_id"],
            "designation": salesperson["designation"],
        }
    )


@app.post("/api/auth/salesperson/set-first-pin")
def set_first_salesperson_pin():
    data = request.get_json(silent=True) or {}
    salesperson_id = data.get("salesperson_id")
    pin = data.get("pin")

    if not isinstance(salesperson_id, int):
        return jsonify({"success": False, "error": "Invalid salesperson_id"}), 400
    if not isinstance(pin, str) or not PIN_PATTERN.fullmatch(pin):
        return jsonify({"success": False, "error": "PIN must be exactly 4 digits"}), 400

    pin_set = db.salesperson_has_pin(salesperson_id)
    if pin_set is None:
        return jsonify({"success": False, "error": "Salesperson not found"}), 404
    if pin_set:
        return jsonify({"success": False, "error": "PIN already set"}), 403

    if not db.set_salesperson_pin(salesperson_id, pin):
        return jsonify({"success": False, "error": "Salesperson not found"}), 404

    return jsonify({"success": True})


@app.post("/api/admin/set_pin")
def set_salesperson_pin():
    data = request.get_json(silent=True) or {}
    salesperson_id = data.get("salesperson_id")
    pin = data.get("pin")

    if not isinstance(salesperson_id, int):
        return jsonify({"success": False, "error": "Invalid salesperson_id"}), 400
    if not isinstance(pin, str) or not PIN_PATTERN.fullmatch(pin):
        return jsonify({"success": False, "error": "PIN must be exactly 4 digits"}), 400

    if not db.set_salesperson_pin(salesperson_id, pin):
        return jsonify({"success": False, "error": "Salesperson not found"}), 404

    return jsonify({"success": True})


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


@app.post("/api/test_alert")
def send_test_alert():
    data = request.get_json(silent=True) or {}
    store_name = _clean_text(data.get("store_name"), "MK Jewels", max_length=100)
    salesperson_name = _clean_text(data.get("salesperson_name"), "Test", max_length=100)
    event = {
        "transcript": "This is a test alert from the MK Jewels dashboard.",
        "objection_detected": True,
        "price_concern": True,
        "certification_question": False,
        "upsell_miss": False,
        "knowledge_gap": False,
        "intent_signal": True,
        "alert_priority": "high",
        "reasoning": "Manual dashboard test alert.",
    }

    try:
        AlertManager().send_alert(
            salesperson_name=salesperson_name,
            event=event,
            store_name=store_name,
        )
    except Exception as error:
        return jsonify({"status": "error", "detail": str(error)}), 500

    return jsonify({"status": "sent"})


@app.get("/api/alerts/log")
def get_alert_log():
    limit = request.args.get("limit", default=20, type=int)
    return jsonify(db.get_alert_log(limit=limit))


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


def _clean_text(value: Any, default: str, max_length: int) -> str:
    if not isinstance(value, str):
        return default

    cleaned = value.strip()
    if not cleaned:
        return default

    return cleaned[:max_length]


def _count_flag(events: list[dict[str, Any]], key: str) -> int:
    return sum(1 for event in events if bool(event.get(key)))


# DEVELOPMENT ONLY - do not use for production.
# Production: gunicorn -c dashboard/gunicorn_config.py dashboard.server:app
if __name__ == "__main__":
    app.run(port=Config.FLASK_PORT)
