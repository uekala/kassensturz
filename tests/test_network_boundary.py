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
