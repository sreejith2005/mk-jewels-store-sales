from __future__ import annotations

import os
import re
import secrets
import sys
import threading
import time
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
from core.readiness import is_ready, set_not_ready, set_ready  # noqa: E402
from scoring.session_scoring import generate_and_save_session_score  # noqa: E402
from storage.db import Database  # noqa: E402


app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app, origins=Config.CORS_ORIGINS.split(","))
db = Database()
logger = get_logger(__name__)
PIN_PATTERN = re.compile(r"^\d{4}$")
STARTED_AT = time.time()
_startup_thread_started = False


def _verify_models_for_serving() -> None:
    if Config.PIPELINE_MODE == "demo":
        set_ready()
        return

    try:
        from transcription.local_pipeline import load_models

        if load_models():
            set_ready()
            return

        set_not_ready()
        logger.critical(
            "Model startup verification failed; API requests will remain gated."
        )
    except Exception:
        set_not_ready()
        logger.critical(
            "Model startup verification crashed; API requests will remain gated.",
            exc_info=True,
        )


def _start_model_verification() -> None:
    global _startup_thread_started
    if _startup_thread_started or is_ready():
        return
    _startup_thread_started = True
    threading.Thread(target=_verify_models_for_serving, daemon=True).start()


_start_model_verification()


@app.before_request
def gate_api_until_models_ready() -> Any:
    if request.method == "OPTIONS":
        return None
    if request.path.startswith("/api/") and not is_ready():
        return jsonify({"error": "Server still starting up"}), 503

    return None


@app.before_request
def require_auth() -> Any:
    if request.method == "OPTIONS":
        return None
    public_paths = [
        "/recorder",
        "/static/",
        "/api/auth/manager",
        "/api/auth/",
        "/api/auth/salesperson",
        "/api/stores",
        "/api/health",
        "/favicon.ico",
    ]
    if any(request.path.startswith(path) for path in public_paths):
        return None

    logger.debug(
        "Auth check: path=%s token_present=%s",
        request.path,
        bool(request.headers.get("X-Manager-Token")),
    )

    token = request.headers.get("X-Manager-Token", "")
    if not token or not db.validate_manager_token(token):
        return jsonify({"error": "Unauthorized"}), 401

    return None


@app.get("/recorder")
def get_recorder():
    return send_file(DASHBOARD_ROOT / "recorder.html")


@app.get("/api/health")
def get_health():
    ready = Config.PIPELINE_MODE == "demo" or is_ready()
    return jsonify(
        {
            "status": "ready" if ready else "loading",
            "pipeline": Config.PIPELINE_MODE,
        }
    )


@app.get("/api/health/detail")
def get_health_detail():
    ready = Config.PIPELINE_MODE == "demo" or is_ready()
    return jsonify(
        {
            "status": "ready" if ready else "loading",
            "uptime_seconds": int(time.time() - STARTED_AT),
            "pipeline": Config.PIPELINE_MODE,
        }
    )


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


@app.post("/api/auth/manager")
def authenticate_manager():
    data = request.get_json(silent=True) or {}
    password = data.get("password")
    if password == Config.DASHBOARD_AUTH_PASS:
        token = secrets.token_hex(32)
        expires_at = time.time() + (8 * 3600)
        db.cleanup_expired_tokens()
        db.save_manager_token(token, expires_at)
        return jsonify({"success": True, "token": token})

    return jsonify({"success": False, "error": "Invalid password"}), 401


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


@app.get("/api/scores/session/<session_id>")
def get_session_score(session_id: str):
    score = db.get_session_score(session_id)
    if score is None:
        return jsonify({"error": "Session score not found"}), 404
    return jsonify(score)


@app.get("/api/scores/salesperson/<salesperson_name>")
def get_salesperson_scores(salesperson_name: str):
    days = request.args.get("days", default=30, type=int)
    return jsonify(db.get_salesperson_scores(salesperson_name, days=days))


@app.get("/api/scores/leaderboard/<int:store_id>")
def get_score_leaderboard(store_id: int):
    return jsonify(db.get_store_leaderboard(store_id))


@app.post("/api/scores/generate/<session_id>")
def generate_session_score(session_id: str):
    try:
        score = generate_and_save_session_score(session_id, db=db)
    except Exception as error:
        logger.exception("Manual score generation failed for %s.", session_id)
        return jsonify({"error": str(error)}), 500

    if score is None:
        return jsonify({"error": "Session has no transcript events to score"}), 404
    return jsonify(score)


def queue_session_score_generation(session_id: str) -> None:
    def worker():
        try:
            generate_and_save_session_score(session_id)
        except Exception as error:
            logger.warning("Background score generation failed for %s: %s", session_id, error)

    threading.Thread(target=worker, daemon=True).start()


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
