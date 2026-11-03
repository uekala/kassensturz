from fastapi.testclient import TestClient

from kassensturz import main


def _client_with_address(address: str) -> TestClient:
    # Starlette lets tests provide the peer address so that the ingress
    # middleware can be exercised without opening a network listener.
    return TestClient(main.app, client=(address, 50123))


def test_non_ingress_remote_client_is_blocked_even_in_development_mode(monkeypatch, db):
    monkeypatch.setenv("KASSENSTURZ_DEV", "1")

    with _client_with_address("203.0.113.25") as client:
        api_response = client.get("/api/state")
        page_response = client.get("/")

    assert api_response.status_code == 403
    assert page_response.status_code == 403


def test_loopback_client_can_reach_local_service(db):
    with _client_with_address("127.0.0.1") as client:
        response = client.get("/api/state")

    assert response.status_code == 200


def test_ipv6_loopback_client_can_reach_local_service(db):
    with _client_with_address("::1") as client:
        response = client.get("/api/state")

    assert response.status_code == 200


def test_home_assistant_ingress_client_can_reach_service(db):
    with _client_with_address(main.INGRESS_IP) as client:
        response = client.get("/api/state")

    assert response.status_code == 200



def test_forwarded_header_cannot_spoof_ingress_address(db):
    with _client_with_address("203.0.113.25") as client:
        response = client.get(
            "/api/state",
            headers={"X-Forwarded-For": main.INGRESS_IP},
        )

    assert response.status_code == 403

def test_mobile_namespace_rejects_cleartext_http_even_on_loopback(db):
    with _client_with_address("127.0.0.1") as client:
        response = client.get("/api/v1/not-enabled")

    assert response.status_code == 426
    assert response.json()["error"]["code"] == "https_required"
    assert response.headers["cache-control"] == "no-store"


def test_mobile_namespace_does_not_trust_forwarded_proto_from_untrusted_peer(db):
    with _client_with_address("203.0.113.25") as client:
        response = client.get(
            "/api/v1/not-enabled",
            headers={"X-Forwarded-Proto": "https"},
        )

    assert response.status_code == 426


def test_mobile_namespace_accepts_direct_https_but_does_not_register_routes(db):
    with TestClient(
        main.app,
        base_url="https://testserver",
        client=("127.0.0.1", 50123),
    ) as client:
        response = client.get("/api/v1/not-enabled")

    assert response.status_code == 404


def test_mobile_namespace_accepts_https_asserted_by_explicitly_trusted_proxy(
    monkeypatch, db
):
    from kassensturz.mobile_security import parse_trusted_proxy_networks

    monkeypatch.setattr(
        main,
        "TRUSTED_PROXY_NETWORKS",
        parse_trusted_proxy_networks(main.INGRESS_IP),
    )
    with _client_with_address(main.INGRESS_IP) as client:
        response = client.get(
            "/api/v1/not-enabled",
            headers={"X-Forwarded-Proto": "https"},
        )

    # Transport is accepted, but no mobile HTTP route is registered yet.
    assert response.status_code == 404


def test_mobile_namespace_rejects_http_asserted_by_trusted_proxy(monkeypatch, db):
    from kassensturz.mobile_security import parse_trusted_proxy_networks

    monkeypatch.setattr(
        main,
        "TRUSTED_PROXY_NETWORKS",
        parse_trusted_proxy_networks(main.INGRESS_IP),
    )
    with _client_with_address(main.INGRESS_IP) as client:
        response = client.get(
            "/api/v1/not-enabled",
            headers={"X-Forwarded-Proto": "http"},
        )

    assert response.status_code == 426

def test_mobile_pairing_rate_limit_is_enforced_before_route_dispatch(monkeypatch, db):
    from kassensturz.mobile_security import InMemoryRateLimiter

    monkeypatch.setattr(main, "MOBILE_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(
        main,
        "MOBILE_RATE_LIMITS",
        {("POST", "/api/v1/pair"): ("pair-test", 2, 60)},
    )

    with TestClient(
        main.app,
        base_url="https://testserver",
        client=("127.0.0.1", 50123),
    ) as client:
        first = client.post("/api/v1/pair", json={"pairing_secret": "not-real"})
        second = client.post("/api/v1/pair", json={"pairing_secret": "not-real"})
        third = client.post("/api/v1/pair", json={"pairing_secret": "not-real"})

    # The registered route validates the intentionally malformed body,
    # while the third attempt is stopped by the network limiter first.
    assert first.status_code == 400
    assert second.status_code == 400
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limited"
    assert third.headers["retry-after"] == "60"
    assert third.headers["cache-control"] == "no-store"

def test_mobile_client_network_allowlist_is_empty_by_default(monkeypatch, db):
    from kassensturz.mobile_security import parse_trusted_proxy_networks

    monkeypatch.setattr(main, "MOBILE_CLIENT_NETWORKS", ())
    with TestClient(
        main.app,
        base_url="https://testserver",
        client=("100.64.0.25", 50123),
    ) as client:
        response = client.get("/api/v1/not-enabled")

    assert response.status_code == 403


def test_mobile_client_from_explicit_private_network_is_allowed_only_on_mobile_paths(
    monkeypatch, db
):
    from kassensturz.mobile_security import parse_trusted_proxy_networks

    monkeypatch.setattr(
        main,
        "MOBILE_CLIENT_NETWORKS",
        parse_trusted_proxy_networks("100.64.0.0/10"),
    )
    with TestClient(
        main.app,
        base_url="https://testserver",
        client=("100.64.0.25", 50123),
    ) as client:
        mobile_response = client.get("/api/v1/not-enabled")
        browser_response = client.get("/")

    assert mobile_response.status_code == 404
    assert browser_response.status_code == 403


def test_trusted_reverse_proxy_can_forward_an_allowlisted_vpn_client(
    monkeypatch, db
):
    from kassensturz.mobile_security import parse_trusted_proxy_networks

    monkeypatch.setattr(
        main,
        "TRUSTED_PROXY_NETWORKS",
        parse_trusted_proxy_networks("127.0.0.2"),
    )
    monkeypatch.setattr(
        main,
        "MOBILE_CLIENT_NETWORKS",
        parse_trusted_proxy_networks("100.64.0.0/10"),
    )
    with TestClient(
        main.app,
        base_url="http://testserver",
        client=("127.0.0.2", 50123),
    ) as client:
        response = client.get(
            "/api/v1/not-enabled",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "100.64.0.25",
            },
        )

    assert response.status_code == 404


def test_untrusted_peer_cannot_spoof_membership_in_mobile_allowlist(db, monkeypatch):
    from kassensturz.mobile_security import parse_trusted_proxy_networks

    monkeypatch.setattr(
        main,
        "MOBILE_CLIENT_NETWORKS",
        parse_trusted_proxy_networks("100.64.0.0/10"),
    )
    with TestClient(
        main.app,
        base_url="https://testserver",
        client=("203.0.113.25", 50123),
    ) as client:
        response = client.get(
            "/api/v1/not-enabled",
            headers={"X-Forwarded-For": "100.64.0.25"},
        )

    assert response.status_code == 403

