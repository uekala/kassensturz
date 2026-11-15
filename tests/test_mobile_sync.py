"""Stand des Bankabrufs und Abruf aus der App – ohne echte Bank, nur erfundene Daten."""
from datetime import datetime, timedelta, timezone

import pytest

from kassensturz import banksync, fints_sync, openbanking, secrets_store
from test_mobile_write import https_client, paired_headers, reset_mobile_guards


class FakeJob:
    def __init__(self, name, state="done", added=0, error=None):
        self.name, self.state, self.error = name, state, error
        self.result = {"added": added} if state == "done" else None


@pytest.fixture
def bank(db, monkeypatch):
    """Eine erfundene Freigabe mit einem Konto; Abrufe laufen gegen eine Attrappe."""
    banksync._jobs.clear()
    valid = (datetime.now(timezone.utc) + timedelta(days=100)).isoformat()
    eb = db.insert("eb_sessions", {"session_id": "geheim-erfunden", "aspsp_name": "Erfundene Bank", "aspsp_country": "DE",
                                   "valid_until": valid, "status": "active", "last_sync": "2026-11-14T06:30:05", "last_status": "ok"})
    db.insert("accounts", {"name": "Testgiro", "kind": "giro", "eb_session_id": eb})
    calls = []
    monkeypatch.setattr(openbanking, "is_configured", lambda _db: True)

    def start_sync(eb_id, psu=None, on_done=None, background=False):
        calls.append({"eb_id": eb_id, "psu": psu})
        return FakeJob("Erfundene Bank", added=3)

    monkeypatch.setattr(openbanking, "start_sync", start_sync)
    yield calls
    banksync._jobs.clear()


def test_status_names_banks_and_times_but_no_identifiers(db, bank, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        assert client.get("/api/v1/sync").status_code == 401
        data = client.get("/api/v1/sync", headers=paired_headers(client)).json()
    assert data["sources"] == [{"name": "Erfundene Bank", "last_sync": "2026-11-14T06:30:05", "state": "ok",
                                "days_left": 99, "accounts": 1}]
    assert data["last_sync"] == data["newest_sync"] == "2026-11-14T06:30:05"
    assert data["next_sync"][11:16] == "06:30"
    assert data["run"] == {"state": "idle", "added": 0, "errors": []}
    assert data["can_start"] is True and data["wait_minutes"] == 0
    assert "geheim" not in str(data)


def test_start_fetches_once_and_then_asks_to_wait(db, bank, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        headers = paired_headers(client)
        assert client.post("/api/v1/sync").status_code == 401
        started = client.post("/api/v1/sync", headers={**headers, "User-Agent": "Kassensturz-Test"})
        assert started.status_code == 202
        assert started.json()["run"] == {"state": "done", "added": 3, "errors": []}
        assert started.json()["can_start"] is False
        assert started.json()["wait_minutes"] == banksync.COOLDOWN_MINUTES
        assert [c["eb_id"] for c in bank] == [1]
        assert bank[0]["psu"]["ua"] == "Kassensturz-Test" and bank[0]["psu"]["ip"]

        again = client.post("/api/v1/sync", headers=headers)
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "too_soon"
        assert "Minuten" in again.json()["error"]["message"]
        assert len(bank) == 1


def test_cooldown_ends_and_running_jobs_are_not_doubled(db, bank, monkeypatch):
    now = datetime(2026, 11, 15, 10, 0)
    banksync.start(db, now=now)
    assert banksync.status(db, now + timedelta(minutes=29))["wait_minutes"] == 1
    later = now + timedelta(minutes=31)
    assert banksync.status(db, later)["can_start"] is True

    monkeypatch.setattr(openbanking, "start_sync", lambda *a, **k: bank.append("neu") or FakeJob("Erfundene Bank", state="running"))
    assert banksync.start(db, now=later)["run"]["state"] == "running"
    assert banksync.start(db, now=later + timedelta(hours=1))["run"]["state"] == "running"
    assert bank.count("neu") == 1


def test_errors_are_reported_per_bank(db, bank, monkeypatch):
    monkeypatch.setattr(openbanking, "start_sync",
                        lambda *a, **k: FakeJob("Erfundene Bank", state="error", error="Die Freigabe ist abgelaufen."))
    run = banksync.start(db)["run"]
    assert run == {"state": "error", "added": 0, "errors": [{"name": "Erfundene Bank", "message": "Die Freigabe ist abgelaufen."}]}


def test_fints_without_pin_is_listed_but_never_started(db, monkeypatch):
    banksync._jobs.clear()
    monkeypatch.setattr(openbanking, "is_configured", lambda _db: False)
    started = []
    monkeypatch.setattr(fints_sync, "start", lambda *a, **k: started.append((a, k)) or FakeJob("Testbank"))
    db.insert("connections", {"name": "Testbank", "blz": "00000000", "login": "erfunden", "server": "https://example.invalid"})
    monkeypatch.setattr(secrets_store, "has_pin", lambda _cid: False)

    state = banksync.status(db)
    assert state["sources"][0]["state"] == "needs_pin"
    assert state["can_start"] is False and state["next_sync"] is None and state["last_sync"] is None
    with pytest.raises(banksync.SyncRefused) as refused:
        banksync.start(db)
    assert refused.value.code == "nothing_to_sync"
    assert started == []

    monkeypatch.setattr(secrets_store, "has_pin", lambda _cid: True)
    assert banksync.start(db)["run"]["state"] == "done"
    assert started[0][0][:2] == (1, None) and started[0][1]["background"] is True


def test_expired_and_empty_grants_are_named(db, bank):
    db.update("eb_sessions", "id", 1, {"status": "expired"})
    other = db.insert("eb_sessions", {"session_id": "x", "aspsp_name": "Erfundene Sparkasse", "aspsp_country": "DE", "status": "active"})
    states = {s["name"]: s["state"] for s in banksync.status(db)["sources"]}
    assert states == {"Erfundene Bank": "expired", "Erfundene Sparkasse": "no_accounts"}
    assert other and banksync.status(db)["can_start"] is False


def test_start_is_rate_limited(db, bank, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        headers = paired_headers(client)
        codes = [client.post("/api/v1/sync", headers=headers).status_code for _ in range(7)]
    assert codes == [202, 409, 409, 409, 409, 409, 429]
