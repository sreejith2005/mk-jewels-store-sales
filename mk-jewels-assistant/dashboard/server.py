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
from dotenv import set_key

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
DASHBOARD_ROOT = Path(__file__).resolve().parent

from alerting.console_alert import AlertManager  # noqa: E402
from config import Config  # noqa: E402
from core.logger import get_logger  # noqa: E402
from core.readiness import is_ready  # noqa: E402
from scoring.session_scoring import generate_and_save_session_score  # noqa: E402
from storage.db import Database  # noqa: E402


app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app, origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","))
db = Database()
logger = get_logger(__name__)
PIN_PATTERN = re.compile(r"^\d{4}$")
ENV_PATH = APP_ROOT / ".env"
MAX_MANAGER_TOKENS = 10
MAX_FAILED_MANAGER_LOGINS = 5
MANAGER_LOGIN_BLOCK_SECONDS = 5 * 60
_manager_tokens: list[str] = []
_manager_token_set: set[str] = set()
_manager_auth_lock = threading.Lock()
_manager_failed_attempts: dict[str, dict[str, float | int]] = {}


@app.before_request
def require_manager_token() -> Any:
    if request.method == "GET" and request.path == "/api/health":
        return None
    if request.method == "GET" and request.path == "/recorder":
        return None
    if request.method == "GET" and request.path.startswith("/static/"):
        return None
    if request.method == "POST" and request.path in {
        "/api/auth/salesperson",
        "/api/auth/salesperson/set-first-pin",
        "/api/auth/manager",
    }:
        return None

    if not Config.DASHBOARD_AUTH_PASS:
        return None

    if _has_valid_manager_auth():
        return None

    return jsonify({"error": "Unauthorized"}), 401


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
    client_ip = _client_ip()
    blocked_for = _manager_login_block_remaining(client_ip)
    if blocked_for > 0:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Too many attempts, try again in 5 minutes",
                }
            ),
            429,
        )

    data = request.get_json(silent=True) or {}
    password = data.get("password")
    if not isinstance(password, str) or not secrets.compare_digest(
        password,
        Config.DASHBOARD_AUTH_PASS,
    ):
        _record_failed_manager_login(client_ip)
        return jsonify({"success": False, "error": "Invalid password"}), 401

    _clear_failed_manager_login(client_ip)
    token = _add_manager_token()
    return jsonify({"success": True, "token": token})


@app.post("/api/auth/manager/change-password")
def change_manager_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not isinstance(current_password, str) or not secrets.compare_digest(
        current_password,
        Config.DASHBOARD_AUTH_PASS,
    ):
        return jsonify({"success": False, "error": "Invalid password"}), 401

    if not isinstance(new_password, str) or not new_password.strip():
        return jsonify({"success": False, "error": "New password is required"}), 400

    ENV_PATH.touch(exist_ok=True)
    set_key(str(ENV_PATH), "DASHBOARD_AUTH_PASS", new_password)
    Config.DASHBOARD_AUTH_PASS = new_password

    with _manager_auth_lock:
        _manager_tokens.clear()
        _manager_token_set.clear()

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


def _extract_manager_token() -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    header_token = request.headers.get("X-Manager-Token", "")
    return header_token.strip() or None


def _has_valid_manager_auth() -> bool:
    token = _extract_manager_token()
    return bool(token and token in _manager_token_set)


def _add_manager_token() -> str:
    token = secrets.token_hex(32)
    with _manager_auth_lock:
        _manager_tokens.append(token)
        _manager_token_set.add(token)
        while len(_manager_tokens) > MAX_MANAGER_TOKENS:
            expired_token = _manager_tokens.pop(0)
            _manager_token_set.discard(expired_token)
    return token


def _client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _manager_login_block_remaining(client_ip: str) -> float:
    with _manager_auth_lock:
        attempt = _manager_failed_attempts.get(client_ip)
        if not attempt:
            return 0

        blocked_until = float(attempt.get("blocked_until", 0))
        remaining = blocked_until - time.time()
        if remaining <= 0 and blocked_until:
            _manager_failed_attempts.pop(client_ip, None)
            return 0

        return max(0, remaining)


def _record_failed_manager_login(client_ip: str) -> None:
    now = time.time()
    with _manager_auth_lock:
        attempt = _manager_failed_attempts.get(client_ip, {"count": 0, "blocked_until": 0})
        count = int(attempt.get("count", 0)) + 1
        _manager_failed_attempts[client_ip] = {
            "count": count,
            "blocked_until": now + MANAGER_LOGIN_BLOCK_SECONDS
            if count >= MAX_FAILED_MANAGER_LOGINS
            else 0,
        }


def _clear_failed_manager_login(client_ip: str) -> None:
    with _manager_auth_lock:
        _manager_failed_attempts.pop(client_ip, None)


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
