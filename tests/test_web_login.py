"""Eigenständiger Betrieb: Anmeldung an der Weboberfläche über einen vertrauenswürdigen HTTPS-Proxy."""
import base64

import pytest
from fastapi.testclient import TestClient

from kassensturz import ha, main
from kassensturz.mobile_security import InMemoryRateLimiter, parse_trusted_proxy_networks

PROXY = "127.0.0.1"  # der Proxy läuft auf demselben Rechner und kommt über Loopback an
VIA_PROXY = {"X-Forwarded-Proto": "https", "X-Forwarded-For": "100.101.102.103",
             "X-Forwarded-Host": "kassensturz.example.ts.net"}


def basic(user, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


LOGIN = {**VIA_PROXY, **basic("kassensturz", "geheim-und-lang")}


@pytest.fixture()
def web_login(db, monkeypatch):
    """Anmeldung eingerichtet, der Proxy auf Loopback ist als vertrauenswürdig eingetragen."""
    monkeypatch.setattr(main, "WEB_USER", "kassensturz")
    monkeypatch.setattr(main, "WEB_PASSWORD", "geheim-und-lang")
    monkeypatch.setattr(main, "WEB_LOGIN_FAILURES", {})
    monkeypatch.setattr(main, "MOBILE_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", parse_trusted_proxy_networks(f"{PROXY}/32"))
    monkeypatch.setattr(main, "MOBILE_CLIENT_NETWORKS", ())
    return db


def client_from(address):
    return TestClient(main.app, client=(address, 50123))


def test_without_password_loopback_and_ingress_stay_local(db, monkeypatch):
    monkeypatch.setattr(main, "WEB_PASSWORD", "")
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", parse_trusted_proxy_networks(f"{PROXY}/32"))
    for address in ("127.0.0.1", main.INGRESS_IP):
        with client_from(address) as client:
            assert client.get("/api/state").status_code == 200, address
    with client_from("203.0.113.25") as client:
        assert client.get("/api/state", headers=LOGIN).status_code == 403


def test_supervisor_token_switches_the_login_off():
    assert main._web_password_from_env({"KASSENSTURZ_WEB_PASSWORD": "geheim"}) == "geheim"
    assert main._web_password_from_env({"KASSENSTURZ_WEB_PASSWORD": "geheim", "SUPERVISOR_TOKEN": "x"}) == ""
    assert main._web_password_from_env({}) == ""


def test_proxy_requests_need_user_and_password(web_login):
    with client_from(PROXY) as client:
        refused = client.get("/", headers=VIA_PROXY)
        assert refused.status_code == 401
        assert refused.headers["www-authenticate"].startswith("Basic")
        assert refused.headers["cache-control"] == "no-store"
        assert client.get("/api/state", headers=VIA_PROXY).status_code == 401
        assert client.get("/api/state", headers={**VIA_PROXY, **basic("kassensturz", "falsch")}).status_code == 401
        assert client.get("/api/state", headers={**VIA_PROXY, **basic("anders", "geheim-und-lang")}).status_code == 401
        assert client.get("/api/state", headers={**VIA_PROXY, "Authorization": "Basic %%%"}).status_code == 401
        assert client.get("/api/state", headers=LOGIN).status_code == 200
        assert client.get("/", headers=LOGIN).status_code == 200
        assert client.get("/static/js/einstellungen.js", headers=VIA_PROXY).status_code == 401
        assert client.get("/static/js/einstellungen.js", headers=LOGIN).status_code == 200


def test_login_only_over_https(web_login):
    with client_from(PROXY) as client:
        plain = {**LOGIN, "X-Forwarded-Proto": "http"}
        assert client.get("/api/state", headers=plain).status_code == 426
        # Ohne Proxy-Kopfzeilen ist es dieselbe Gegenstelle, also weiter der Proxy und kein lokaler Zugriff.
        assert client.get("/api/state").status_code == 426
        assert client.get("/api/state", headers=basic("kassensturz", "geheim-und-lang")).status_code == 426


def test_only_the_trusted_proxy_may_present_a_login(web_login):
    for address in ("203.0.113.25", "192.168.50.20", main.INGRESS_IP):
        with client_from(address) as client:
            assert client.get("/api/state", headers=LOGIN).status_code == 403, address
            assert client.get("/", headers=LOGIN).status_code == 403, address


def test_unlisted_proxy_on_loopback_is_refused_instead_of_trusted(web_login, monkeypatch):
    # Passwort gesetzt, aber der Proxy fehlt in KASSENSTURZ_TRUSTED_PROXIES: nicht offen, sondern zu.
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", ())
    with client_from("127.0.0.1") as client:
        assert client.get("/api/state", headers=LOGIN).status_code == 403
        assert client.get("/api/state", headers={"X-Forwarded-For": "100.101.102.103"}).status_code == 403
        assert client.get("/api/state").status_code == 200   # wirklich lokal, ohne Weiterleitung


def test_loopback_stays_local_when_the_proxy_is_elsewhere(web_login, monkeypatch):
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", parse_trusted_proxy_networks("172.17.0.1/32"))
    with client_from("127.0.0.1") as client:
        assert client.get("/api/state").status_code == 200
    with client_from("172.17.0.1") as client:
        assert client.get("/api/state", headers=VIA_PROXY).status_code == 401
        assert client.get("/api/state", headers=LOGIN).status_code == 200


def test_wrong_passwords_are_rate_limited_per_client(web_login):
    with client_from(PROXY) as client:
        for _ in range(8):  # Anfragen ohne Anmeldedaten zählen nicht, so beginnt jeder Browser
            assert client.get("/api/state", headers=VIA_PROXY).status_code == 401
        wrong = {**VIA_PROXY, **basic("kassensturz", "geraten")}
        for _ in range(main.WEB_LOGIN_LIMIT):
            assert client.get("/api/state", headers=wrong).status_code == 401
        blocked = client.get("/api/state", headers=LOGIN)
        assert blocked.status_code == 429
        assert blocked.headers["retry-after"] == "300"
        # Gesperrt ist die Adresse hinter dem Proxy, nicht der Proxy selbst.
        other = {**LOGIN, "X-Forwarded-For": "100.99.98.97"}
        assert client.get("/api/state", headers=other).status_code == 200


def test_foreign_sites_cannot_write(web_login):
    body = {"name": "Testkonto", "kind": "giro"}
    with client_from(PROXY) as client:
        before = len(client.get("/api/accounts", headers=LOGIN).json())
        foreign = {**LOGIN, "Origin": "https://fremd.example"}
        assert client.post("/api/accounts", json=body, headers=foreign).status_code == 403
        cross = {**LOGIN, "Sec-Fetch-Site": "cross-site"}
        assert client.post("/api/accounts", json=body, headers=cross).status_code == 403
        assert len(client.get("/api/accounts", headers=LOGIN).json()) == before
        own = {**LOGIN, "Origin": "https://kassensturz.example.ts.net", "Sec-Fetch-Site": "same-origin"}
        assert client.post("/api/accounts", json=body, headers=own).status_code < 300
        assert len(client.get("/api/accounts", headers=LOGIN).json()) == before + 1


def test_changes_are_logged_under_the_web_user(web_login):
    with client_from(PROXY) as client:
        own = {**LOGIN, "Origin": "https://kassensturz.example.ts.net"}
        assert client.post("/api/accounts", json={"name": "Testkonto", "kind": "giro"}, headers=own).status_code < 300
        rows = web_login.query("SELECT actor, actor_kind FROM audit_log ORDER BY id")
        assert [(row["actor"], row["actor_kind"]) for row in rows] == [("kassensturz", "web")]


def test_logged_in_user_can_pair_and_list_phones(web_login):
    with client_from(PROXY) as client:
        assert client.post("/api/mobile/pairings", headers=VIA_PROXY).status_code == 401
        assert client.get("/api/mobile/devices", headers=VIA_PROXY).status_code == 401
        own = {**LOGIN, "Origin": "https://kassensturz.example.ts.net"}
        pairing = client.post("/api/mobile/pairings", headers=own)
        assert pairing.status_code == 201
        assert client.get("/api/mobile/devices", headers=LOGIN).status_code == 200
        # Die Handy-API selbst bleibt bei ihren Geräte-Tokens und kennt keine Anmeldung mit Passwort.
        paired = client.post("/api/v1/pair", headers=VIA_PROXY,
                             json={"pairing_secret": pairing.json()["pairing_secret"], "device_name": "Testhandy"})
        assert paired.status_code == 201
        assert client.get("/api/v1/me", headers=LOGIN).status_code == 401


def test_phone_api_needs_no_web_login(web_login):
    with client_from(PROXY) as client:
        assert client.get("/api/v1/health", headers=VIA_PROXY).status_code == 200


def test_container_health_check_needs_no_login(web_login):
    with client_from(PROXY) as client:
        assert client.get("/healthz").status_code in (200, 503)   # direkt über Loopback, ohne Proxy-Kopfzeilen
        assert client.get("/healthz", headers=VIA_PROXY).status_code == 401
        assert client.post("/healthz").status_code == 426


def test_home_assistant_token_for_standalone_use(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("KASSENSTURZ_HA_TOKEN", raising=False)
    assert ha._token() is None and not ha.available()
    monkeypatch.setenv("KASSENSTURZ_HA_TOKEN", "lang-lebig")
    assert ha._token() == "lang-lebig" and ha.available()
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor")
    assert ha._token() == "supervisor"
