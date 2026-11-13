from fastapi.testclient import TestClient

from datetime import timedelta

from kassensturz import main, mobile_auth, options
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
        assert me.json()["capabilities"] == [
            "overview",
            "transactions",
            "accounts",
            "categories",
            "contracts",
            "transactions.write",
            "transactions.search",
            "stats",
            "budgets.write",
            "contracts.write",
            "categories.learn",
            "afford",
            "review",
            "goals",
            "tax",
            "receipts",
        ]

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

        monkeypatch.setattr(mobile_auth, "REFRESH_RETRY_GRACE", timedelta(seconds=-1))
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

def test_local_admin_can_create_pairing_through_ingress_tls_termination(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    # The HA Ingress terminates external HTTPS and talks to the add-on over
    # the trusted internal network. Native pairing redemption still requires TLS.
    with TestClient(main.app, client=("127.0.0.1", 50123)) as client:
        pairing = client.post("/api/mobile/pairings")
        assert pairing.status_code == 201

        cleartext_pair = client.post(
            "/api/v1/pair",
            json={
                "pairing_secret": pairing.json()["pairing_secret"],
                "device_name": "iPhone",
            },
        )
        assert cleartext_pair.status_code == 426

def test_trusted_tailscale_proxy_can_reach_mobile_api_without_client_cidr(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    trusted_peer = "172.30.32.1"
    monkeypatch.setattr(
        main,
        "TRUSTED_PROXY_NETWORKS",
        parse_trusted_proxy_networks(f"{trusted_peer}/32"),
    )
    with TestClient(
        main.app,
        client=(trusted_peer, 50123),
    ) as client:
        response = client.post(
            "/api/v1/pair",
            content=b"not-json",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "100.101.102.103",
            },
        )

    # The request passed the transport and peer allowlists and was rejected
    # only by the pairing handler's JSON validation.
    assert response.status_code == 400


def test_trusted_loopback_proxy_cannot_use_local_device_admin_routes(
    db, monkeypatch
):
    from kassensturz import mobile_api

    reset_mobile_guards(monkeypatch)
    monkeypatch.setattr(
        main,
        "TRUSTED_PROXY_NETWORKS",
        parse_trusted_proxy_networks("127.0.0.1/32"),
    )
    monkeypatch.setattr(
        mobile_api,
        "TRUSTED_PROXY_NETWORKS",
        parse_trusted_proxy_networks("127.0.0.1/32"),
    )
    with https_client("127.0.0.1") as client:
        response = client.post("/api/mobile/pairings")

    assert response.status_code == 403

def test_ingress_pairing_requires_supervisor_authenticated_user_identity(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    with TestClient(main.app, client=(main.INGRESS_IP, 50123)) as client:
        no_identity = client.post("/api/mobile/pairings")
        with_identity = client.post(
            "/api/mobile/pairings",
            headers={"X-Remote-User-Id": "ha-user-123"},
        )

    assert no_identity.status_code == 403
    assert with_identity.status_code == 201


def test_untrusted_remote_client_cannot_spoof_ingress_user_identity(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client("203.0.113.25") as client:
        response = client.post(
            "/api/mobile/pairings",
            headers={"X-Remote-User-Id": "ha-admin"},
        )

    assert response.status_code == 403


def test_addon_ingress_is_explicitly_admin_only():
    from pathlib import Path

    config_path = (
        Path(__file__).resolve().parent.parent / "kassensturz" / "config.yaml"
    )
    config_text = config_path.read_text("utf-8")
    assert "\npanel_admin: true\n" in config_text

def test_mobile_health_is_available_before_pairing_without_sensitive_data(
    db, monkeypatch
):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "api_version": 1,
        "server": {"name": "Kassensturz", "version": options.VERSION},
    }
    assert "authorization" not in response.text.lower()
    assert "database" not in response.text.lower()

def test_mobile_health_has_a_separate_network_rate_limit(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    monkeypatch.setattr(
        main,
        "MOBILE_RATE_LIMITS",
        {("GET", "/api/v1/health"): ("health-test", 2, 60)},
    )
    with https_client() as client:
        first = client.get("/api/v1/health")
        second = client.get("/api/v1/health")
        third = client.get("/api/v1/health")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers["retry-after"] == "60"

def test_mobile_pairing_returns_svg_qr_for_configured_https_origin(
    db, monkeypatch
):
    import base64
    import json

    from kassensturz import mobile_api

    reset_mobile_guards(monkeypatch)
    monkeypatch.setattr(
        mobile_api.options,
        "load",
        lambda: {"mobile_server_url": "https://green.example.ts.net"},
    )
    captured = {}
    original_generator = mobile_api._pairing_qr_svg_base64

    def capture_payload(payload):
        captured["payload"] = payload
        return original_generator(payload)

    monkeypatch.setattr(mobile_api, "_pairing_qr_svg_base64", capture_payload)
    with https_client() as client:
        response = client.post("/api/mobile/pairings")

    assert response.status_code == 201
    result = response.json()
    assert result["server_url"] == "https://green.example.ts.net"
    assert result["expires_at"]
    svg = base64.b64decode(result["qr_svg_base64"], validate=True).decode("utf-8")
    assert "<svg" in svg
    assert "<path" in svg

    qr_payload = json.loads(captured["payload"])
    assert qr_payload == {
        "type": "kassensturz-pairing",
        "version": 1,
        "server_url": "https://green.example.ts.net",
        "pairing_secret": result["pairing_secret"],
    }
    assert result["pairing_secret"] not in result["server_url"]


def test_pairing_qr_is_omitted_when_mobile_server_url_is_unconfigured(
    db, monkeypatch
):
    from kassensturz import mobile_api

    reset_mobile_guards(monkeypatch)
    monkeypatch.setattr(
        mobile_api.options,
        "load",
        lambda: {"mobile_server_url": ""},
    )
    with https_client() as client:
        response = client.post("/api/mobile/pairings")

    assert response.status_code == 201
    assert response.json()["server_url"] is None
    assert "qr_svg_base64" not in response.json()
    assert len(response.json()["pairing_secret"]) >= 43


def test_pairing_qr_rejects_non_https_or_path_server_url_before_creating_secret(
    db, monkeypatch
):
    from kassensturz import mobile_api

    reset_mobile_guards(monkeypatch)
    monkeypatch.setattr(
        mobile_api.options,
        "load",
        lambda: {"mobile_server_url": "http://green.local/api"},
    )
    with https_client() as client:
        response = client.post("/api/mobile/pairings")
        # Checked while the app runs: shutting the app down closes the database.
        pairings = db.scalar("SELECT COUNT(*) FROM mobile_pairings")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "mobile_server_url_invalid"
    assert pairings == 0



def test_refresh_retry_after_lost_response_keeps_the_device_paired(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        _, credentials = create_device(client)
        first = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": credentials["refresh_token"]},
        )
        assert first.status_code == 200
        retry = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": credentials["refresh_token"]},
        )
        assert retry.status_code == 200
        me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {retry.json()['access_token']}"},
        )
        assert me.status_code == 200


def test_blocked_network_gets_mobile_error_format_on_mobile_paths_only(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client(peer="192.168.50.77") as client:
        mobile = client.get("/api/v1/health")
        web = client.get("/api/state")
    assert mobile.status_code == 403
    assert mobile.json()["error"]["code"] == "network_not_allowed"
    assert mobile.json()["detail"] == mobile.json()["error"]["message"]
    assert web.status_code == 403
    assert "error" not in web.json() and web.json()["detail"]
