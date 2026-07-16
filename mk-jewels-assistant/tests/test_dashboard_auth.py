import pytest

from dashboard import server
from storage.db import Database


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    db_path = tmp_path / "sessions.db"
    test_db = Database(str(db_path))
    original_db = server.db
    monkeypatch.setattr(server, "db", test_db)
    monkeypatch.setattr(server.Config, "DASHBOARD_AUTH_PASS", "secret")

    try:
        yield server.app.test_client(), test_db, db_path
    finally:
        test_db.close()
        monkeypatch.setattr(server, "db", original_db)


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


def test_manager_auth_accepts_correct_password(dashboard_client):
    client, db, _db_path = dashboard_client

    response = client.post("/api/auth/manager", json={"password": "secret"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert isinstance(payload["token"], str)
    assert db.validate_manager_token(payload["token"]) is True


def test_manager_auth_rejects_wrong_password(dashboard_client):
    client, _db, _db_path = dashboard_client

    response = client.post("/api/auth/manager", json={"password": "wrong"})

    assert response.status_code == 401
    assert response.get_json() == {"success": False, "error": "Invalid password"}


def test_protected_route_without_token_returns_401(dashboard_client):
    client, _db, _db_path = dashboard_client

    response = client.get("/api/sessions")

    assert response.status_code == 401
    assert response.get_json() == {"error": "Unauthorized"}


def test_recorder_store_routes_skip_dashboard_auth(dashboard_client):
    client, db, _db_path = dashboard_client
    salesperson_id = _seed_salesperson(db)

    stores_response = client.get("/api/stores")
    salespersons_response = client.get("/api/stores/1/salespersons")

    assert stores_response.status_code == 200
    assert salespersons_response.status_code == 200
    assert salespersons_response.get_json()[0]["id"] == salesperson_id


def test_apk_download_route_skips_dashboard_auth_and_sets_download_headers(
    dashboard_client, tmp_path, monkeypatch
):
    client, _db, _db_path = dashboard_client
    apk_path = tmp_path / "app-release.apk"
    apk_path.write_bytes(b"fake apk")
    monkeypatch.setattr(server, "ANDROID_RELEASE_APK", apk_path)

    response = client.get("/download/mkjewels-app.apk")

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.android.package-archive"
    assert response.headers["Content-Disposition"] == (
        "attachment; filename=mkjewels-app.apk"
    )
    assert response.data == b"fake apk"


def test_protected_route_with_valid_token_returns_200(dashboard_client):
    client, _db, _db_path = dashboard_client

    response = client.get("/api/sessions", headers=_manager_token_header(client))

    assert response.status_code == 200


def test_manager_token_survives_database_reopen(dashboard_client, monkeypatch):
    client, db, db_path = dashboard_client
    token_response = client.post("/api/auth/manager", json={"password": "secret"})
    token = token_response.get_json()["token"]
    db.close()

    reopened_db = Database(str(db_path))
    monkeypatch.setattr(server, "db", reopened_db)

    try:
        response = client.get("/api/sessions", headers={"X-Manager-Token": token})

        assert response.status_code == 200
        assert reopened_db.validate_manager_token(token) is True
    finally:
        reopened_db.close()


def test_salesperson_auth_route_skips_dashboard_basic_auth(dashboard_client):
    client, db, _db_path = dashboard_client
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
    client, db, _db_path = dashboard_client
    salesperson_id = _seed_salesperson(db)
    db.set_salesperson_pin(salesperson_id, "1234")

    response = client.post(
        "/api/auth/salesperson",
        json={"salesperson_id": salesperson_id, "pin": "0000"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"success": False, "error": "Invalid PIN"}


def test_salesperson_auth_returns_no_pin_reason(dashboard_client):
    client, db, _db_path = dashboard_client
    salesperson_id = _seed_salesperson(db)

    response = client.post(
        "/api/auth/salesperson",
        json={"salesperson_id": salesperson_id, "pin": "1234"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": False, "reason": "NO_PIN_SET"}


def test_first_pin_setup_succeeds_when_pin_hash_is_null(dashboard_client):
    client, db, _db_path = dashboard_client
    salesperson_id = _seed_salesperson(db)

    response = client.post(
        "/api/auth/salesperson/set-first-pin",
        json={"salesperson_id": salesperson_id, "pin": "2468"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True}
    assert db.verify_salesperson_pin(salesperson_id, "2468") is True


def test_first_pin_setup_rejects_when_pin_already_exists(dashboard_client):
    client, db, _db_path = dashboard_client
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
    client, db, _db_path = dashboard_client
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


def test_admin_set_pin_rejects_non_four_digit_pin(dashboard_client):
    client, db, _db_path = dashboard_client
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
