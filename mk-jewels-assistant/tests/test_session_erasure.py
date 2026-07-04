import pytest

from dashboard import server
from storage.db import Database


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    test_db = Database(str(tmp_path / "sessions.db"))
    original_db = server.db
    monkeypatch.setattr(server, "db", test_db)
    monkeypatch.setattr(server.Config, "DASHBOARD_AUTH_PASS", "secret")
    server.ACTIVE_TOKENS.clear()

    try:
        yield server.app.test_client(), test_db
    finally:
        test_db.close()
        monkeypatch.setattr(server, "db", original_db)
        server.ACTIVE_TOKENS.clear()


def _manager_token_header(client) -> dict[str, str]:
    response = client.post("/api/auth/manager", json={"password": "secret"})
    token = response.get_json()["token"]
    return {"X-Manager-Token": token}


def test_delete_session_with_valid_auth_returns_success(dashboard_client):
    client, db = dashboard_client
    session_id = db.create_session("Maya")
    db.log_event(session_id, "Maya", _event_dict())

    response = client.delete(
        f"/api/sessions/{session_id}",
        headers=_manager_token_header(client),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "message": "Session deleted",
    }
    assert db.get_session_events(session_id) == []


def test_delete_missing_session_with_valid_auth_returns_404(dashboard_client):
    client, _db = dashboard_client

    response = client.delete(
        "/api/sessions/missing-session",
        headers=_manager_token_header(client),
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": "Session not found",
    }


def test_delete_session_without_auth_returns_401(dashboard_client):
    client, db = dashboard_client
    session_id = db.create_session("Maya")

    response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 401


def test_events_api_returns_raw_display_and_compatible_transcript(dashboard_client):
    client, db = dashboard_client
    session_id = db.create_session("Maya")
    event = _event_dict()
    event["transcript"] = "Mujhe aapki service bilkul pasand nahi hai"
    event["raw_transcript"] = "मुझे आपकी सर्विस बिल्कुल पसंद नहीं है"
    event["display_transcript"] = "Mujhe aapki service bilkul pasand nahi hai"

    db.log_event(session_id, "Maya", event)

    response = client.get(
        f"/api/events/{session_id}",
        headers=_manager_token_header(client),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload[0]["raw_transcript"] == "मुझे आपकी सर्विस बिल्कुल पसंद नहीं है"
    assert payload[0]["display_transcript"] == "Mujhe aapki service bilkul pasand nahi hai"
    assert payload[0]["transcript"] == "Mujhe aapki service bilkul pasand nahi hai"


def _event_dict():
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
