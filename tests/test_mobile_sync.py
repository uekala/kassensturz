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
                                "days_left": 99, "accounts": 1, "renew": None}]
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


def _expiring(db, days):
    until = (datetime.now(timezone.utc) + timedelta(days=days, hours=1)).isoformat()
    db.execute("UPDATE eb_sessions SET valid_until = ?", (until,))


def test_renewing_an_expiring_consent_from_the_phone(db, bank, monkeypatch):
    from kassensturz import household
    reset_mobile_guards(monkeypatch)
    calls = []

    def fake(method, path, **kwargs):
        calls.append((method, path))
        if (method, path) == ("POST", "/auth"):
            return {"url": "https://bank.example.invalid/freigabe?state=" + kwargs["body"]["state"]}
        if (method, path) == ("POST", "/sessions"):
            return {"session_id": "geheim-neu-erfunden", "aspsp": {"name": "Erfundene Bank"},
                    "accounts": [{"uid": "ks-test-uid", "account_id": {"iban": "DE00KSTEST0000000000"}, "name": "Testgiro"}]}
        return {}
    monkeypatch.setattr(openbanking, "call", fake)
    monkeypatch.setattr(openbanking, "aspsps", lambda _db, _country="DE": [])
    with https_client() as client:
        headers = paired_headers(client)
        assert "banks.renew" in client.get("/api/v1/me", headers=headers).json()["capabilities"]
        # Läuft die Freigabe noch lange, gibt es nichts zu erneuern.
        assert client.get("/api/v1/sync", headers=headers).json()["sources"][0]["renew"] is None
        assert client.post("/api/v1/banks/renew", json={"id": 1}, headers=headers).status_code == 409
        _expiring(db, 5)
        assert client.get("/api/v1/sync", headers=headers).json()["sources"][0]["renew"] == 1
        assert client.post("/api/v1/banks/renew", json={"id": 1}).status_code == 401
        for bad in ({}, {"id": "1"}, {"id": True}):
            assert client.post("/api/v1/banks/renew", json=bad, headers=headers).status_code == 400
        assert client.post("/api/v1/banks/renew", json={"id": 99}, headers=headers).status_code == 409

        started = client.post("/api/v1/banks/renew", json={"id": 1}, headers=headers)
        assert started.status_code == 200, started.text
        assert ("POST", "/auth") in calls
        assert set(started.json()) == {"name", "url", "days"} and started.json()["name"] == "Erfundene Bank"
        state = started.json()["url"].split("state=")[1]

        # Fremde oder unvollständige Rückgaben ändern nichts.
        for text in ("", "https://enablebanking.com/?code=ks", "https://enablebanking.com/?code=ks&state=fremd"):
            got = client.post("/api/v1/banks/renew/complete", json={"text": text}, headers=headers)
            assert got.status_code in (400, 409), text
        assert db.scalar("SELECT session_id FROM eb_sessions WHERE id = 1") == "geheim-erfunden"
        # Eine neue Bank lässt sich über diesen Weg nicht verbinden.
        new_bank = openbanking.start_auth(db, "Andere erfundene Bank", "DE")
        got = client.post("/api/v1/banks/renew/complete", headers=headers,
                          json={"text": f"https://enablebanking.com/?code=ks&state={new_bank['state']}"})
        assert got.status_code == 409 and db.scalar("SELECT COUNT(*) FROM eb_sessions") == 1

        done = client.post("/api/v1/banks/renew/complete", headers=headers,
                           json={"text": f"https://enablebanking.com/?code=ks-test-code&state={state}"})
        assert done.status_code == 200, done.text
        assert done.json()["name"] == "Erfundene Bank" and done.json()["accounts"] == 1
        assert "geheim" not in done.text and "geheim" not in started.text
        assert db.scalar("SELECT session_id FROM eb_sessions WHERE id = 1") == "geheim-neu-erfunden"
        assert ("DELETE", "/sessions/geheim-erfunden") in calls
        assert client.get("/api/v1/sync", headers=headers).json()["sources"][0]["renew"] is None
        # Das Erneuern ruft keine Umsätze ab.
        assert bank == []
        assert db.scalar("SELECT text FROM audit_log ORDER BY id DESC LIMIT 1").startswith("Bankfreigabe erneuert")

        # Ein Kinderhandy sieht und darf das nicht.
        child = household.create_person(db, {"name": "Kim", "is_child": True})["id"]
        _expiring(db, 2)
        secret = client.post("/api/mobile/pairings", json={"person_id": child}).json()["pairing_secret"]
        token = client.post("/api/v1/pair", json={"pairing_secret": secret, "device_name": "Kims Handy"}).json()["access_token"]
        kid = {"Authorization": f"Bearer {token}"}
        assert "banks.renew" not in client.get("/api/v1/me", headers=kid).json()["capabilities"]
        assert client.get("/api/v1/sync", headers=kid).json()["sources"][0]["renew"] is None
        assert client.post("/api/v1/banks/renew", json={"id": 1}, headers=kid).status_code == 403


def _asking_job(kind, payload):
    """Ein FinTS-Auftrag, der wie bei einer echten Bank auf eine Antwort wartet; ohne Verbindung."""
    import threading
    job = fints_sync.Job(1, "Erfundene Bank")
    got = {}

    def run():
        try:
            got["answer"] = job.ask(kind, payload, timeout=5)
            job.state = "done"
            job.result = {"added": 2}
        except fints_sync.JobCancelled:
            job.state = "cancelled"

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    for _ in range(200):
        if job.state == "waiting" and job.question:
            break
        threading.Event().wait(0.01)
    return job, got, thread


def test_bank_question_is_answered_from_the_phone(db, bank, monkeypatch):
    from kassensturz import household
    reset_mobile_guards(monkeypatch)
    started = []
    monkeypatch.setattr(fints_sync, "start", lambda *a, **k: started.append(k) or FakeJob("Testbank"))
    monkeypatch.setattr(secrets_store, "has_pin", lambda _cid: True)
    db.insert("connections", {"name": "Testbank", "blz": "00000000", "login": "erfunden", "server": "https://example.invalid"})
    with https_client() as client:
        headers = paired_headers(client)
        assert "sync.tan" in client.get("/api/v1/me", headers=headers).json()["capabilities"]
        # Nur wer es ausdrücklich verlangt, startet FinTS mit Rückfragen; ältere Apps bleiben beim Hintergrundlauf.
        assert client.post("/api/v1/sync", headers=headers).status_code == 202
        assert started[-1]["background"] is True
        db.set_setting(banksync.LAST_START_KEY, None)
        assert client.post("/api/v1/sync", json={"interactive": True}, headers=headers).status_code == 202
        assert started[-1]["background"] is False
        assert client.get("/api/v1/sync", headers=headers).json()["question"] is None

        job, got, thread = _asking_job("tan", {"text": "Bitte TAN aus der erfundenen App eingeben.",
                                               "html": "<b>nicht fürs Handy</b>", "image": "data:text/html;base64,AAAA",
                                               "flicker": ["10101", "01010"]})
        banksync._jobs[:] = [job]
        status = client.get("/api/v1/sync", headers=headers).json()
        q = status["question"]
        assert status["run"]["state"] == "running"
        assert q == {"qid": job.question["qid"], "kind": "tan", "bank": "Erfundene Bank",
                     "text": "Bitte TAN aus der erfundenen App eingeben.", "flicker": ["10101", "01010"]}
        assert job.id not in str(status)

        assert client.post("/api/v1/sync/answer", json={"qid": q["qid"], "value": "123456"}).status_code == 401
        for bad in ({}, {"qid": ""}, {"qid": q["qid"], "value": "1", "extra": 1}):
            assert client.post("/api/v1/sync/answer", json=bad, headers=headers).status_code == 400
        for refused in ({"qid": "fremd", "value": "123456"}, {"qid": q["qid"], "value": ""},
                        {"qid": q["qid"], "value": 123456}, {"qid": q["qid"], "value": "9" * 65}):
            assert client.post("/api/v1/sync/answer", json=refused, headers=headers).status_code == 409, refused
        assert job.state == "waiting"

        # Ein Kinderhandy sieht die Rückfrage nicht und kann nicht antworten.
        child = household.create_person(db, {"name": "Kim", "is_child": True})["id"]
        secret = client.post("/api/mobile/pairings", json={"person_id": child}).json()["pairing_secret"]
        token = client.post("/api/v1/pair", json={"pairing_secret": secret, "device_name": "Kims Handy"}).json()["access_token"]
        kid = {"Authorization": f"Bearer {token}"}
        assert "sync.tan" not in client.get("/api/v1/me", headers=kid).json()["capabilities"]
        assert client.get("/api/v1/sync", headers=kid).json()["question"] is None
        assert client.post("/api/v1/sync/answer", json={"qid": q["qid"], "value": "1"}, headers=kid).status_code == 403

        done = client.post("/api/v1/sync/answer", json={"qid": q["qid"], "value": " 123456 "}, headers=headers)
        assert done.status_code == 200
        thread.join(2)
        assert got["answer"] == "123456"
        after = client.get("/api/v1/sync", headers=headers).json()
        assert after["question"] is None and after["run"] == {"state": "done", "added": 2, "errors": []}
        # Dieselbe Antwort ein zweites Mal trifft keine offene Rückfrage mehr.
        assert client.post("/api/v1/sync/answer", json={"qid": q["qid"], "value": "123456"}, headers=headers).status_code == 409
        # Im Protokoll steht, dass geantwortet wurde, aber nie die TAN.
        logged = " ".join(r["text"] for r in db.query("SELECT text FROM audit_log"))
        assert "Rückfrage der Bank" in logged and "123456" not in logged


def test_choice_approval_and_cancel(db, bank, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        headers = paired_headers(client)

        job, got, thread = _asking_job("choice", {"title": "Welches TAN-Verfahren nutzt du?", "options": [
            {"value": "921", "label": "Erfundene pushTAN", "hint": "App-Freigabe"}, {"value": "910", "label": "Erfundene chipTAN", "hint": ""}]})
        banksync._jobs[:] = [job]
        q = client.get("/api/v1/sync", headers=headers).json()["question"]
        assert q["kind"] == "choice" and [o["value"] for o in q["options"]] == ["921", "910"]
        assert client.post("/api/v1/sync/answer", json={"qid": q["qid"], "value": "999"}, headers=headers).status_code == 409
        assert client.post("/api/v1/sync/answer", json={"qid": q["qid"], "value": "910"}, headers=headers).status_code == 200
        thread.join(2)
        assert got["answer"] == "910"

        job, got, thread = _asking_job("tan", {"text": "Erfundene Rückfrage"})
        banksync._jobs[:] = [job]
        q = client.get("/api/v1/sync", headers=headers).json()["question"]
        assert client.post("/api/v1/sync/answer", json={"qid": q["qid"], "cancel": True}, headers=headers).status_code == 200
        thread.join(2)
        assert "answer" not in got and job.state == "cancelled"
        assert client.get("/api/v1/sync", headers=headers).json()["question"] is None
