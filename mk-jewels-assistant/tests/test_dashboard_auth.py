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
    server._manager_tokens.clear()
    server._manager_token_set.clear()
    server._manager_failed_attempts.clear()
    server.MANAGER_TOKEN_PATH.unlink(missing_ok=True)

    try:
        yield server.app.test_client(), test_db
    finally:
        test_db.close()
        monkeypatch.setattr(server, "db", original_db)
        server.MANAGER_TOKEN_PATH.unlink(missing_ok=True)


def _seed_salesperson(db: Database) -> int:
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
        db._connection.commit()
        return cursor.lastrowid


def _manager_token_header(client) -> dict[str, str]:
    response = client.post("/api/auth/manager", json={"password": "secret"})
    token = response.get_json()["token"]
    return {"X-Manager-Token": token}


def test_salesperson_auth_route_skips_dashboard_basic_auth(dashboard_client):
    client, db = dashboard_client
    salesperson_id = _seed_salesperson(db)
    db.set_salesperson_pin(salesperson_id, "1234")

    response = client.post(
        "/api/auth/salesperson",
        json={"salesperson_id": salesperson_id, "pin": "1234"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "salesperson_id": salesperson_id,
        "name": "Maya",
        "store_id": 1,
        "designation": "Sales Executive",
    }


def test_salesperson_auth_rejects_invalid_pin(dashboard_client):
    client, db = dashboard_client
    salesperson_id = _seed_salesperson(db)
    db.set_salesperson_pin(salesperson_id, "1234")

    response = client.post(
        "/api/auth/salesperson",
        json={"salesperson_id": salesperson_id, "pin": "0000"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"success": False, "error": "Invalid PIN"}


def test_salesperson_auth_returns_no_pin_reason(dashboard_client):
    client, db = dashboard_client
    salesperson_id = _seed_salesperson(db)

    response = client.post(
        "/api/auth/salesperson",
        json={"salesperson_id": salesperson_id, "pin": "1234"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": False, "reason": "NO_PIN_SET"}


def test_first_pin_setup_succeeds_when_pin_hash_is_null(dashboard_client):
    client, db = dashboard_client
    salesperson_id = _seed_salesperson(db)

    response = client.post(
        "/api/auth/salesperson/set-first-pin",
        json={"salesperson_id": salesperson_id, "pin": "2468"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True}
    assert db.verify_salesperson_pin(salesperson_id, "2468") is True


def test_first_pin_setup_rejects_when_pin_already_exists(dashboard_client):
    client, db = dashboard_client
    salesperson_id = _seed_salesperson(db)
    db.set_salesperson_pin(salesperson_id, "1234")

    response = client.post(
        "/api/auth/salesperson/set-first-pin",
        json={"salesperson_id": salesperson_id, "pin": "2468"},
    )

    assert response.status_code == 403
    assert response.get_json() == {"success": False, "error": "PIN already set"}
    assert db.verify_salesperson_pin(salesperson_id, "1234") is True
    assert db.verify_salesperson_pin(salesperson_id, "2468") is False


def test_admin_set_pin_requires_manager_token(dashboard_client):
    client, db = dashboard_client
    salesperson_id = _seed_salesperson(db)

    unauthorized = client.post(
        "/api/admin/set_pin",
        json={"salesperson_id": salesperson_id, "pin": "4321"},
    )
    authorized = client.post(
        "/api/admin/set_pin",
        headers=_manager_token_header(client),
        json={"salesperson_id": salesperson_id, "pin": "4321"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.get_json() == {"success": True}
    assert db.verify_salesperson_pin(salesperson_id, "4321") is True


def test_manager_token_survives_empty_memory_set(dashboard_client):
    client, _db = dashboard_client
    headers = _manager_token_header(client)
    server._manager_tokens.clear()
    server._manager_token_set.clear()

    response = client.get("/api/stores", headers=headers)

    assert response.status_code == 200


def test_admin_set_pin_rejects_non_four_digit_pin(dashboard_client):
    client, db = dashboard_client
    salesperson_id = _seed_salesperson(db)

    response = client.post(
        "/api/admin/set_pin",
        headers=_manager_token_header(client),
        json={"salesperson_id": salesperson_id, "pin": "12345"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": "PIN must be exactly 4 digits",
    }
