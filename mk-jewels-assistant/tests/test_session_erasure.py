import base64

import pytest

from dashboard import server
from storage.db import Database


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    test_db = Database(str(tmp_path / "sessions.db"))
    original_db = server.db
    monkeypatch.setattr(server, "db", test_db)
    monkeypatch.setattr(server.Config, "DASHBOARD_AUTH_USER", "admin")
    monkeypatch.setattr(server.Config, "DASHBOARD_AUTH_PASS", "secret")

    try:
        yield server.app.test_client(), test_db
    finally:
        test_db.close()
        monkeypatch.setattr(server, "db", original_db)


def _basic_auth_header() -> dict[str, str]:
    token = base64.b64encode(b"admin:secret").decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_delete_session_with_valid_auth_returns_success(dashboard_client):
    client, db = dashboard_client
    session_id = db.create_session("Maya")
    db.log_event(session_id, "Maya", _event_dict())

    response = client.delete(
        f"/api/sessions/{session_id}",
        headers=_basic_auth_header(),
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
        headers=_basic_auth_header(),
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
