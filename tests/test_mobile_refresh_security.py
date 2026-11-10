"""Sicherheitstests für die Erneuerung der Geräteanmeldung.

Regeln, die hier festgeschrieben sind:

* Ein ersetztes Refresh-Token darf genau einmal erneut vorgelegt werden, höchstens
  zehn Minuten nach der ersten Ersetzung und nur, solange der Nachfolger unbenutzt ist.
* Jede weitere Wiederverwendung sperrt das Gerät und entwertet alle seine Tokens.
* Wird ein durch eine Wiederholung entwertetes Token vorgelegt, halten zwei Parteien
  Tokens desselben Geräts: Das Gerät wird gesperrt.

Alle Tokens entstehen in einer leeren Testdatenbank.
"""
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from kassensturz import main, mobile_auth
from kassensturz.mobile_auth import (
    ACCESS_TTL,
    EXPIRED_TOKEN_RETENTION,
    REFRESH_RETRY_GRACE,
    REFRESH_TTL,
    InvalidCredential,
    MobileAuthService,
    RefreshReplayDetected,
)
from kassensturz.mobile_security import InMemoryRateLimiter


class Clock:
    def __init__(self):
        self.current = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.current

    def advance(self, **kwargs):
        self.current += timedelta(**kwargs)


@pytest.fixture
def env(db):
    clock = Clock()
    service = MobileAuthService(db, clock=clock)
    initial = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Prüfgerät")
    return service, clock, initial, db


def device_revoked(service):
    return service.list_devices()[0]["revoked_at"] is not None


def works(service, access_token):
    try:
        service.authenticate_access_token(access_token)
        return True
    except InvalidCredential:
        return False


# --- A: normale Erneuerung -------------------------------------------------------------

def test_A1_normal_rotation_issues_new_pair(env):
    service, clock, initial, _ = env
    clock.advance(minutes=9)
    rotated = service.rotate_refresh_token(initial["refresh_token"])
    assert rotated["access_token"] != initial["access_token"]
    assert rotated["refresh_token"] != initial["refresh_token"]
    assert rotated["access_expires_in"] == 600 and rotated["refresh_expires_in"] == 30 * 86400
    assert works(service, rotated["access_token"])


def test_A2_chain_of_rotations_over_weeks_keeps_device(env):
    service, clock, initial, _ = env
    token = initial["refresh_token"]
    for _ in range(40):
        clock.advance(days=20)
        token = service.rotate_refresh_token(token)["refresh_token"]
    assert not device_revoked(service)


def test_A3_tokens_are_stored_only_as_hashes(env):
    service, _, initial, db = env
    rotated = service.rotate_refresh_token(initial["refresh_token"])
    dump = repr(db.query("SELECT * FROM mobile_tokens")) + repr(db.query("SELECT * FROM mobile_devices"))
    for secret in (initial["access_token"], initial["refresh_token"], rotated["access_token"], rotated["refresh_token"]):
        assert secret not in dump


# --- B: verlorene Antwort ----------------------------------------------------------------

@pytest.mark.parametrize("seconds", [0, 1, 59, 300, 599, 600])
def test_B1_retry_inside_window_succeeds(env, seconds):
    service, clock, initial, _ = env
    lost = service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=seconds)
    retried = service.rotate_refresh_token(initial["refresh_token"])
    assert works(service, retried["access_token"])
    assert not works(service, lost["access_token"])
    assert not device_revoked(service)


def test_B2_retry_one_second_after_window_is_replay(env):
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=601)
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])
    assert device_revoked(service)


def test_B3_retried_pair_continues_normally(env):
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=30)
    retried = service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(minutes=11)
    following = service.rotate_refresh_token(retried["refresh_token"])
    assert works(service, following["access_token"]) and not device_revoked(service)


def test_B4_retry_is_allowed_only_once(env):
    """Zugesagt ist EINE Wiederholung. Das alte Token darf nicht beliebig oft neue Paare liefern."""
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=30)
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=30)
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])
    assert device_revoked(service)


def test_B5_window_cannot_be_extended_by_repeating(env):
    """Das Fenster muss ab der ERSTEN Ersetzung zählen, nicht ab der jeweils letzten."""
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    with pytest.raises(InvalidCredential):
        for _ in range(12):  # 12 x 9 Minuten = 108 Minuten
            clock.advance(minutes=9)
            service.rotate_refresh_token(initial["refresh_token"])
    assert device_revoked(service)


def test_B6_window_counts_from_first_replacement_not_from_the_retry(env):
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(minutes=9)
    retried = service.rotate_refresh_token(initial["refresh_token"])  # die eine Wiederholung
    clock.advance(seconds=1)  # weit innerhalb von zehn Minuten nach der Wiederholung
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])
    assert device_revoked(service) and not works(service, retried["access_token"])


def test_B7_retry_of_a_retried_token_is_again_limited_to_one(env):
    """Auch das per Wiederholung erhaltene Token darf nach einer verlorenen Antwort nur einmal wiederholt werden."""
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    retried = service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(minutes=11)
    service.rotate_refresh_token(retried["refresh_token"])  # Antwort geht verloren
    clock.advance(seconds=5)
    again = service.rotate_refresh_token(retried["refresh_token"])  # eine Wiederholung
    assert works(service, again["access_token"]) and not device_revoked(service)
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(retried["refresh_token"])
    assert device_revoked(service)


def test_B8_clock_running_backwards_never_opens_the_window(env):
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=-5)
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])
    assert device_revoked(service)


def test_B9_retired_access_token_is_rejected_without_locking_the_device(env):
    """Nur ein entwertetes Refresh-Token zeigt einen Konflikt an; ein altes Zugriffstoken ergibt nur 401."""
    service, clock, initial, _ = env
    lost = service.rotate_refresh_token(initial["refresh_token"])
    retried = service.rotate_refresh_token(initial["refresh_token"])
    assert not works(service, lost["access_token"])
    assert works(service, retried["access_token"]) and not device_revoked(service)


# --- C: abgelaufene Tokens -----------------------------------------------------------------

def test_C1_access_token_expires_exactly_at_ttl(env):
    service, clock, initial, _ = env
    clock.advance(seconds=599)
    assert works(service, initial["access_token"])
    clock.advance(seconds=1)
    assert not works(service, initial["access_token"])


def test_C2_expired_refresh_token_is_rejected_without_revoking_device(env):
    service, clock, initial, _ = env
    clock.current += REFRESH_TTL
    with pytest.raises(InvalidCredential) as error:
        service.rotate_refresh_token(initial["refresh_token"])
    assert not isinstance(error.value, RefreshReplayDetected)
    assert not device_revoked(service)


def test_C3_old_access_token_stays_valid_until_expiry_after_rotation(env):
    """Bestandsverhalten: Das alte Zugriffstoken wird bei der Erneuerung nicht entwertet."""
    service, clock, initial, _ = env
    clock.advance(minutes=1)
    service.rotate_refresh_token(initial["refresh_token"])
    assert works(service, initial["access_token"])


def test_C4_expired_token_rows_are_cleaned_up(env):
    """Abgelaufene Token-Zeilen werden beim Erneuern gelöscht."""
    service, clock, initial, db = env
    token = initial["refresh_token"]
    for _ in range(50):
        clock.advance(days=1)
        token = service.rotate_refresh_token(token)["refresh_token"]
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens") < 50


def test_C5_cleanup_keeps_every_token_that_is_still_valid(env):
    service, clock, initial, db = env
    other = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Zweitgerät")
    clock.advance(days=29)
    rotated = service.rotate_refresh_token(initial["refresh_token"])
    # Das Zweitgerät war 29 Tage still: sein Refresh-Token gilt noch und darf nicht gelöscht sein.
    assert works(service, rotated["access_token"])
    assert service.rotate_refresh_token(other["refresh_token"])
    assert not any(d["revoked_at"] for d in service.list_devices())


def test_C6_expired_rows_survive_the_retention_period_then_disappear(env):
    service, clock, initial, db = env
    other = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Zweitgerät")
    first = service.rotate_refresh_token(initial["refresh_token"])
    clock.current += ACCESS_TTL + EXPIRED_TOKEN_RETENTION - timedelta(seconds=1)
    second = service.rotate_refresh_token(first["refresh_token"])
    access_rows = db.scalar("SELECT COUNT(*) FROM mobile_tokens WHERE token_type = 'access'")
    assert access_rows == 4  # 2 Kopplungen + 2 Erneuerungen, noch nichts gelöscht
    clock.advance(seconds=2)
    service.rotate_refresh_token(second["refresh_token"])
    remaining = db.scalar("SELECT COUNT(*) FROM mobile_tokens WHERE token_type = 'access'")
    assert remaining == 2  # die drei um 12:00 ausgestellten sind gelöscht; es bleiben die zwei jüngeren
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens WHERE token_type = 'refresh'") == 5
    assert other["device"]["id"] in {d["id"] for d in service.list_devices()}


def test_C7_rejected_requests_do_not_delete_anything(env):
    service, clock, initial, db = env
    clock.advance(days=3)
    before = db.scalar("SELECT COUNT(*) FROM mobile_tokens")
    with pytest.raises(InvalidCredential):
        service.rotate_refresh_token("u" * 43)
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens") == before


def test_C8_replaced_token_that_has_expired_is_not_retried(env):
    service, clock, initial, db = env
    db.execute(
        "UPDATE mobile_tokens SET expires_at = ? WHERE token_type = 'refresh'",
        ((clock.current + timedelta(minutes=2)).isoformat(timespec="seconds"),),
    )
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(minutes=3)  # im Fenster, aber das alte Token ist abgelaufen
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])
    assert device_revoked(service)


# --- D: Replay-Angriffe ----------------------------------------------------------------------

def test_D1_replay_after_successor_was_used_revokes_device(env):
    service, clock, initial, _ = env
    second = service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=5)
    third = service.rotate_refresh_token(second["refresh_token"])
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])
    assert device_revoked(service) and not works(service, third["access_token"])


def test_D2_thief_inside_window_must_not_end_with_a_working_session(env):
    """Dieb hat das alte Refresh-Token. Das echte Handy hat regulär erneuert und sein Paar erhalten.

    Legt der Dieb das alte Token im Fenster vor, bekommt er ein Paar. Spätestens wenn das echte
    Handy sein (nun entwertetes) Token nutzt, sind zwei Parteien sichtbar: Gerät muss gesperrt sein.
    """
    service, clock, initial, _ = env
    legit = service.rotate_refresh_token(initial["refresh_token"])  # Antwort kam beim Handy an
    clock.advance(minutes=3)
    thief = service.rotate_refresh_token(initial["refresh_token"])  # Dieb nutzt das Fenster
    clock.advance(minutes=8)
    with pytest.raises(InvalidCredential):
        service.rotate_refresh_token(legit["refresh_token"])  # echtes Handy erneuert
    assert device_revoked(service), "Konflikt wurde nicht erkannt"
    assert not works(service, thief["access_token"]), "Dieb hat weiter Zugriff"


def test_D3_thief_cannot_keep_session_alive_indefinitely(env):
    service, clock, initial, _ = env
    legit = service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(minutes=3)
    thief = service.rotate_refresh_token(initial["refresh_token"])
    with pytest.raises(InvalidCredential):
        service.rotate_refresh_token(legit["refresh_token"])
    token = thief["refresh_token"]
    with pytest.raises(InvalidCredential):
        for _ in range(5):
            clock.advance(days=5)
            token = service.rotate_refresh_token(token)["refresh_token"]


def test_D3b_thief_first_then_real_phone_retry_locks_the_device(env):
    """Umgekehrte Reihenfolge: Der Dieb erneuert zuerst, das echte Handy legt danach sein altes Token vor."""
    service, clock, initial, _ = env
    thief = service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(minutes=2)
    phone = service.rotate_refresh_token(initial["refresh_token"])  # gilt als Wiederholung
    clock.advance(minutes=11)
    # Der Dieb will sein Token weiterverwenden: Es wurde durch die Wiederholung entwertet.
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(thief["refresh_token"])
    assert device_revoked(service)
    assert not works(service, phone["access_token"]) and not works(service, thief["access_token"])


def test_D3c_after_lockout_no_token_of_the_device_works_and_pairing_again_is_possible(env):
    service, clock, initial, db = env
    second = service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(minutes=11)
    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])
    for token in (initial["refresh_token"], second["refresh_token"]):
        with pytest.raises(InvalidCredential):
            service.rotate_refresh_token(token)
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens WHERE revoked_at IS NULL") == 0
    fresh = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Neu gekoppelt")
    assert works(service, fresh["access_token"])


def test_D4_revoked_device_cannot_refresh_even_inside_window(env):
    service, clock, initial, _ = env
    service.rotate_refresh_token(initial["refresh_token"])
    service.revoke_device(initial["device"]["id"])
    with pytest.raises(InvalidCredential):
        service.rotate_refresh_token(initial["refresh_token"])


def test_D5_access_token_is_not_accepted_as_refresh_token_and_vice_versa(env):
    service, _, initial, _ = env
    with pytest.raises(InvalidCredential):
        service.rotate_refresh_token(initial["access_token"])
    assert not works(service, initial["refresh_token"])
    assert not device_revoked(service)


@pytest.mark.parametrize("bad", ["", "x", "a" * 43, None, 123, "ä" * 50])
def test_D6_unknown_or_malformed_tokens_are_rejected(env, bad):
    service, _, _, db = env
    before = db.scalar("SELECT COUNT(*) FROM mobile_tokens")
    with pytest.raises(InvalidCredential):
        service.rotate_refresh_token(bad)
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens") == before


def test_D7_retry_of_one_device_does_not_touch_another_device(env):
    service, clock, initial, _ = env
    other = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Zweitgerät")
    service.rotate_refresh_token(initial["refresh_token"])
    clock.advance(seconds=10)
    service.rotate_refresh_token(initial["refresh_token"])
    assert works(service, other["access_token"])
    assert service.rotate_refresh_token(other["refresh_token"])


# --- P: parallele Anfragen ----------------------------------------------------------------

def run_parallel(db, token, count):
    """Legt dasselbe Refresh-Token aus mehreren Threads gleichzeitig vor (echte Uhr)."""
    service = MobileAuthService(db)
    barrier = threading.Barrier(count)
    results, lock = [], threading.Lock()

    def worker():
        barrier.wait()
        try:
            outcome = ("ok", service.rotate_refresh_token(token))
        except RefreshReplayDetected:
            outcome = ("replay", None)
        except InvalidCredential:
            outcome = ("invalid", None)
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len(results) == count
    return service, results


def test_P1_two_parallel_refreshes_leave_exactly_one_valid_pair(db):
    service = MobileAuthService(db)
    initial = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Prüfgerät")
    service, results = run_parallel(db, initial["refresh_token"], 2)
    pairs = [pair for kind, pair in results if kind == "ok"]
    assert len(pairs) == 2  # eine reguläre Erneuerung, eine Wiederholung
    assert sum(works(service, pair["access_token"]) for pair in pairs) == 1
    assert db.scalar(
        "SELECT COUNT(*) FROM mobile_tokens WHERE token_type = 'refresh' "
        "AND revoked_at IS NULL AND replaced_by_hash IS NULL"
    ) == 1
    assert not device_revoked(service)


@pytest.mark.parametrize("count", [3, 8, 16])
def test_P2_more_than_two_parallel_refreshes_lock_the_device(db, count):
    service = MobileAuthService(db)
    initial = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Prüfgerät")
    service, results = run_parallel(db, initial["refresh_token"], count)
    kinds = [kind for kind, _ in results]
    assert kinds.count("ok") == 2 and kinds.count("replay") == 1
    assert kinds.count("invalid") == count - 3
    assert device_revoked(service)
    assert not any(works(service, pair["access_token"]) for kind, pair in results if kind == "ok")
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens WHERE revoked_at IS NULL") == 0


def test_P3_parallel_refreshes_of_different_devices_do_not_interfere(db):
    service = MobileAuthService(db)
    devices = [
        service.redeem_pairing(service.create_pairing()["pairing_secret"], f"Gerät {index}")
        for index in range(6)
    ]
    barrier = threading.Barrier(len(devices))
    results = {}

    def worker(index, token):
        barrier.wait()
        results[index] = MobileAuthService(db).rotate_refresh_token(token)

    threads = [
        threading.Thread(target=worker, args=(index, device["refresh_token"]))
        for index, device in enumerate(devices)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len(results) == 6
    assert all(works(service, pair["access_token"]) for pair in results.values())
    assert not any(d["revoked_at"] for d in service.list_devices())
    assert len({pair["refresh_token"] for pair in results.values()}) == 6


def test_P4_parallel_refresh_and_access_checks_stay_consistent(db):
    service = MobileAuthService(db)
    initial = service.redeem_pairing(service.create_pairing()["pairing_secret"], "Prüfgerät")
    errors = []

    def reader():
        for _ in range(40):
            try:
                MobileAuthService(db).authenticate_access_token(initial["access_token"])
            except Exception as error:  # noqa: BLE001
                errors.append(error)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()
    token = initial["refresh_token"]
    for _ in range(10):
        token = service.rotate_refresh_token(token)["refresh_token"]
    for thread in threads:
        thread.join(timeout=20)
    assert errors == [] and not device_revoked(service)


# --- E: HTTP-Ebene -----------------------------------------------------------------------------

def http():
    return TestClient(main.app, base_url="https://testserver", client=("127.0.0.1", 50123))


def guards(monkeypatch):
    monkeypatch.setattr(main, "MOBILE_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", ())
    monkeypatch.setattr(main, "MOBILE_CLIENT_NETWORKS", ())


def pair(client):
    secret = client.post("/api/mobile/pairings").json()["pairing_secret"]
    return client.post("/api/v1/pair", json={"pairing_secret": secret, "device_name": "Prüfgerät"}).json()


def test_E1_refresh_responses_are_not_cacheable_and_leak_nothing(db, monkeypatch):
    guards(monkeypatch)
    with http() as client:
        credentials = pair(client)
        ok = client.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
        bad = client.post("/api/v1/auth/refresh", json={"refresh_token": "z" * 43})
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
    assert set(ok.json()) == {"access_token", "access_expires_in", "refresh_token", "refresh_expires_in", "token_type"}
    assert bad.status_code == 401 and bad.json() == {"error": {"code": "unauthorized", "message": "Anmeldung erforderlich."}}
    assert "z" * 43 not in bad.text


def test_E2_replay_and_plain_rejection_are_indistinguishable_for_the_caller(db, monkeypatch):
    guards(monkeypatch)
    monkeypatch.setattr(mobile_auth, "REFRESH_RETRY_GRACE", timedelta(seconds=-1))
    with http() as client:
        credentials = pair(client)
        client.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
        replay = client.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
        unknown = client.post("/api/v1/auth/refresh", json={"refresh_token": "q" * 43})
    assert replay.status_code == unknown.status_code == 401
    assert replay.json() == unknown.json()


def test_E3_refresh_is_rate_limited(db, monkeypatch):
    guards(monkeypatch)
    with http() as client:
        codes = [
            client.post("/api/v1/auth/refresh", json={"refresh_token": "q" * 43}).status_code
            for _ in range(32)
        ]
    assert codes.count(401) == 30 and codes[-1] == 429


def test_E4_refresh_requires_https(db, monkeypatch):
    guards(monkeypatch)
    with TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 50123)) as client:
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "q" * 43})
    assert response.status_code == 426


def test_E5_secrets_do_not_appear_in_logs(db, monkeypatch, caplog):
    guards(monkeypatch)
    caplog.set_level("DEBUG")
    with http() as client:
        credentials = pair(client)
        rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]}).json()
        client.get("/api/v1/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    for secret in (credentials["access_token"], credentials["refresh_token"], rotated["access_token"], rotated["refresh_token"]):
        assert secret not in caplog.text


def test_E6_lockout_over_http_looks_like_any_other_rejection_and_blocks_the_device(db, monkeypatch):
    guards(monkeypatch)
    with http() as client:
        credentials = pair(client)
        first = client.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
        retry = client.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
        third = client.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
        after = client.get("/api/v1/me", headers={"Authorization": f"Bearer {retry.json()['access_token']}"})
        devices = client.get("/api/mobile/devices").json()["items"]
    assert (first.status_code, retry.status_code, third.status_code, after.status_code) == (200, 200, 401, 401)
    assert third.json() == {"error": {"code": "unauthorized", "message": "Anmeldung erforderlich."}}
    assert devices[0]["revoked_at"] is not None


def test_E7_regular_login_refresh_logout_cycle_is_unchanged(db, monkeypatch):
    guards(monkeypatch)
    with http() as client:
        credentials = pair(client)
        token = credentials["refresh_token"]
        for _ in range(5):
            response = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
            assert response.status_code == 200
            token = response.json()["refresh_token"]
            access = response.json()["access_token"]
            assert client.get("/api/v1/overview", headers={"Authorization": f"Bearer {access}"}).status_code == 200
        assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}).status_code == 200
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401
