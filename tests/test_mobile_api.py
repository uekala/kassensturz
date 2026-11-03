from fastapi.testclient import TestClient

from kassensturz import main
from kassensturz.mobile_security import InMemoryRateLimiter, parse_trusted_proxy_networks


def https_client(peer="127.0.0.1"):
    return TestClient(
        main.app,
        base_url="https://testserver",
        client=(peer, 50123),
    )


def reset_mobile_guards(monkeypatch):
    monkeypatch.setattr(main, "MOBILE_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", ())
    monkeypatch.setattr(main, "MOBILE_CLIENT_NETWORKS", ())


def create_device(client, name="Test iPhone"):
    pairing_response = client.post("/api/mobile/pairings")
    assert pairing_response.status_code == 201
    pairing_secret = pairing_response.json()["pairing_secret"]
    paired = client.post(
        "/api/v1/pair",
        json={"pairing_secret": pairing_secret, "device_name": name},
    )
    assert paired.status_code == 201
    return pairing_response.json(), paired.json()


def test_mobile_routes_require_access_token(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        paths = (
            "/api/v1/me",
            "/api/v1/overview",
            "/api/v1/transactions",
        )
        for path in paths:
            response = client.get(path)
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "unauthorized"


def test_pairing_returns_secret_once_and_me_endpoint_authenticates_device(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        pairing, credentials = create_device(client, "Mein iPhone")

        stored = db.one("SELECT secret_hash FROM mobile_pairings")
        assert stored["secret_hash"] != pairing["pairing_secret"]

        me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {credentials['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["device"] == credentials["device"]
        assert me.json()["server"]["name"] == "Kassensturz"
        assert me.json()["capabilities"] == ["overview", "transactions"]

        replay = client.post(
            "/api/v1/pair",
            json={
                "pairing_secret": pairing["pairing_secret"],
                "device_name": "Second device",
            },
        )
        assert replay.status_code == 409


def test_authenticated_overview_and_transactions_use_mobile_dtos(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = db.insert(
        "accounts",
        {"name": "Privatkonto", "kind": "giro", "iban": "DE89370400440532013000"},
    )
    category_id = db.insert(
        "categories",
        {"name": "Lebensmittel", "kind": "expense"},
    )
    db.insert(
        "transactions",
        {
            "account_id": account_id,
            "category_id": category_id,
            "booking_date": "2026-11-03",
            "value_date": "2026-11-03",
            "amount_cents": -1234,
            "currency": "EUR",
            "counterparty": "Supermarkt",
            "counterparty_iban": "DE89370400440532013000",
            "purpose": "Kartenzahlung",
            "hash": "private-import-hash",
            "source": "private-import-source",
        },
    )

    with https_client() as client:
        _, credentials = create_device(client)
        headers = {"Authorization": f"Bearer {credentials['access_token']}"}

        overview = client.get("/api/v1/overview", headers=headers)
        assert overview.status_code == 200
        assert overview.json()["currency"] == "EUR"
        assert overview.json()["accounts"][0]["name"] == "Privatkonto"

        transactions = client.get(
            "/api/v1/transactions?limit=10&offset=0&month=2026-11",
            headers=headers,
        )
        assert transactions.status_code == 200
        payload = transactions.json()
        assert payload["total"] == 1
        item = payload["items"][0]
        assert item["counterparty"] == "Supermarkt"
        assert item["category"] == {"id": category_id, "name": "Lebensmittel"}
        serialized = repr(payload)
        assert "DE89370400440532013000" not in serialized
        assert "private-import-hash" not in serialized
        assert "private-import-source" not in serialized


def test_refresh_rotates_credentials_and_old_refresh_cannot_be_reused(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        _, credentials = create_device(client)
        old_access = credentials["access_token"]
        old_refresh = credentials["refresh_token"]

        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert refreshed.status_code == 200
        rotated = refreshed.json()
        assert rotated["access_token"] != old_access
        assert rotated["refresh_token"] != old_refresh

        new_me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {rotated['access_token']}"},
        )
        assert new_me.status_code == 200

        replay = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert replay.status_code == 401

        revoked = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {rotated['access_token']}"},
        )
        assert revoked.status_code == 401


def test_logout_revokes_all_credentials_for_the_current_device(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        _, credentials = create_device(client)
        headers = {"Authorization": f"Bearer {credentials['access_token']}"}

        logout = client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 200
        assert logout.json() == {"ok": True}

        after_logout = client.get("/api/v1/me", headers=headers)
        assert after_logout.status_code == 401
        refresh = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": credentials["refresh_token"]},
        )
        assert refresh.status_code == 401


def test_local_device_administration_lists_and_revokes_one_device(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        _, first = create_device(client, "iPhone")
        _, second = create_device(client, "Android")

        devices = client.get("/api/mobile/devices")
        assert devices.status_code == 200
        assert {item["name"] for item in devices.json()["items"]} == {
            "iPhone",
            "Android",
        }
        assert "token_hash" not in repr(devices.json())
        assert first["access_token"] not in repr(devices.json())

        revoked = client.delete(
            f"/api/mobile/devices/{first['device']['id']}"
        )
        assert revoked.status_code == 200

        first_me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {first['access_token']}"},
        )
        second_me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {second['access_token']}"},
        )
        assert first_me.status_code == 401
        assert second_me.status_code == 200


def test_allowlisted_vpn_client_cannot_manage_devices_or_create_pairings(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    monkeypatch.setattr(
        main,
        "MOBILE_CLIENT_NETWORKS",
        parse_trusted_proxy_networks("100.64.0.0/10"),
    )
    with https_client("100.64.0.25") as client:
        create = client.post("/api/mobile/pairings")
        listing = client.get("/api/mobile/devices")
        assert create.status_code == 403
        assert listing.status_code == 403

        no_token = client.get("/api/v1/me")
        assert no_token.status_code == 401


def test_mobile_pairing_rejects_malformed_request_without_echoing_secrets(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        missing = client.post(
            "/api/v1/pair",
            json={"pairing_secret": "sensitive-user-input"},
        )
        malformed = client.post("/api/v1/pair", content=b"not-json")

    assert missing.status_code == 400
    assert malformed.status_code == 400
    assert "sensitive-user-input" not in missing.text
