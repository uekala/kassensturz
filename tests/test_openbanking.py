import time
from datetime import date

import pytest

import eb_mock


@pytest.fixture()
def bank(db, monkeypatch):
    from kassensturz import openbanking

    pem, pub = eb_mock.make_key()
    b = eb_mock.Bank(pub)
    srv = eb_mock.start(b)
    monkeypatch.setattr(openbanking, "API", f"http://127.0.0.1:{srv.server_port}")
    openbanking._token_cache.clear()
    openbanking._aspsp_cache.clear()
    openbanking._pending.clear()
    b.pem = pem
    yield b
    srv.shutdown()


def _wait(job):
    for _ in range(200):
        if job.state not in ("running", "waiting"):
            return job
        time.sleep(0.02)
    raise AssertionError("Abruf hängt")


def test_config_validates_key(client, bank):
    bad = client.put("/api/eb/config", json={"app_id": "nope", "private_key": bank.pem})
    assert bad.status_code == 400 and "UUID" in bad.json()["detail"]
    other_pem, _ = eb_mock.make_key()
    wrong = client.put("/api/eb/config", json={"app_id": eb_mock.APP_ID, "private_key": other_pem})
    assert wrong.status_code == 400 and "App-ID" in wrong.json()["detail"]
    ok = client.put("/api/eb/config", json={"app_id": eb_mock.APP_ID, "private_key": bank.pem})
    assert ok.status_code == 200
    st = client.get("/api/eb").json()
    assert st["configured"] and st["redirect_url"] == "https://enablebanking.com/"


def test_full_flow_connect_sync_renew_expire(client, db, bank):
    client.put("/api/eb/config", json={"app_id": eb_mock.APP_ID, "private_key": bank.pem})
    # vorhandenes N26-Konto aus einem früheren CSV-Import wird über die IBAN wiedererkannt
    existing = client.post("/api/accounts", json={"name": "N26", "kind": "giro", "iban": eb_mock.IBAN}).json()
    banks = client.get("/api/eb/aspsps?country=DE").json()
    assert [b["name"] for b in banks] == ["N26", "PayPal"]
    auth = client.post("/api/eb/auth", json={"aspsp": "N26", "country": "DE"}, headers={"x-forwarded-for": "192.0.2.7"}).json()
    sent = next(r for r in bank.requests if r[1] == "/auth")
    assert sent[2]["psu_type"] == "personal" and sent[2]["redirect_url"] == "https://enablebanking.com/"
    assert sent[3].get("Psu-Ip-Address") == "192.0.2.7"
    assert auth["days"] == 180

    bad = client.post("/api/eb/complete", json={"text": f"https://enablebanking.com/?state={auth['state']}&error=access_denied"})
    assert bad.status_code == 400 and "nicht erteilt" in bad.json()["detail"]
    auth = client.post("/api/eb/auth", json={"aspsp": "N26", "country": "DE"}).json()
    r = client.post("/api/eb/complete", json={"text": f"https://enablebanking.com/?state={auth['state']}&code=good-1"}).json()
    assert r["accounts"] == [{"id": existing["id"], "name": "N26", "new": False}]
    job = _wait(__import__("kassensturz.fints_sync", fromlist=["JOBS"]).JOBS[r["job"]["id"]])
    assert job.state == "done", job.error
    # 8 REWE + Gehalt + Kartenzahlung; vorgemerkt und USD werden ausgelassen
    assert job.result["added"] == 10
    acc = next(a for a in client.get("/api/accounts").json() if a["id"] == existing["id"])
    assert acc["balance_now"] == 123456 and acc["balance_date"] == date.today().isoformat()
    card = client.get("/api/transactions?q=Starbucks").json()["items"][0]
    assert card["counterparty"] == "Starbucks Berlin" and card["purpose"] == "Kartenzahlung" and card["amount_cents"] == -480

    # zweiter Abruf: nur 7 Tage zurück, keine Duplikate
    job2 = _wait(__import__("kassensturz.openbanking", fromlist=["start_sync"]).start_sync(r["id"]))
    assert job2.state == "done" and job2.result["added"] == 0
    last = [q for q in bank.requests if q[1] == "/accounts/acc-1/transactions"][-1]
    assert (date.today() - date.fromisoformat(last[2]["date_from"])).days <= 7

    # Freigabe abgelaufen
    bank.expired = True
    job3 = _wait(__import__("kassensturz.openbanking", fromlist=["start_sync"]).start_sync(r["id"]))
    assert job3.state == "error" and "abgelaufen" in job3.error
    sess = client.get("/api/eb").json()["sessions"][0]
    assert sess["status"] == "expired"
    assert any(a["title"].startswith("Freigabe für N26 abgelaufen") for a in client.get("/api/overview").json()["alerts"])

    # Erneuern: gleiche Verbindung, neue Sitzung, Konten bleiben verknüpft, alte Sitzung wird gelöscht
    auth = client.post("/api/eb/auth", json={"aspsp": "N26", "country": "DE", "renew_id": r["id"]}).json()
    r2 = client.post("/api/eb/complete", json={"text": f"code=good-2&state={auth['state']}"}).json()
    assert r2["id"] == r["id"] and r2["accounts"][0]["id"] == existing["id"]
    assert ("DELETE", "/sessions/sess-1") in [(q[0], q[1]) for q in bank.requests]
    _wait(__import__("kassensturz.fints_sync", fromlist=["JOBS"]).JOBS[r2["job"]["id"]])
    assert client.get("/api/eb").json()["sessions"][0]["status"] == "active"
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 10


def test_history_fallback_and_new_account(client, bank):
    client.put("/api/eb/config", json={"app_id": eb_mock.APP_ID, "private_key": bank.pem})
    auth = client.post("/api/eb/auth", json={"aspsp": "N26", "country": "DE"}).json()
    bank.always_limit = True  # Bank liefert nie mehr als 90 Tage
    r = client.post("/api/eb/complete", json={"text": f"https://enablebanking.com/?code=good-3&state={auth['state']}"}).json()
    assert r["accounts"][0]["new"] is True and r["accounts"][0]["name"] == "N26 Hauptkonto"
    from kassensturz.fints_sync import JOBS
    job = _wait(JOBS[r["job"]["id"]])
    assert job.state == "done", job.error
    assert job.result["added"] == 7  # nur die letzten 89 Tage
    acc = client.get("/api/accounts").json()[0]
    assert acc["settlement_pattern"] == "n26"


def test_delete_session_keeps_bookings(client, db, bank):
    client.put("/api/eb/config", json={"app_id": eb_mock.APP_ID, "private_key": bank.pem})
    auth = client.post("/api/eb/auth", json={"aspsp": "N26", "country": "DE"}).json()
    r = client.post("/api/eb/complete", json={"text": f"https://enablebanking.com/?code=good-4&state={auth['state']}"}).json()
    from kassensturz.fints_sync import JOBS
    _wait(JOBS[r["job"]["id"]])
    client.delete(f"/api/eb/sessions/{r['id']}")
    assert client.get("/api/eb").json()["sessions"] == []
    assert db.scalar("SELECT COUNT(*) FROM transactions") > 0
    assert db.scalar("SELECT eb_uid FROM accounts") is None


def test_open_banking_callback_requires_exact_state(db, monkeypatch):
    from kassensturz import openbanking

    state = "expected-state"
    openbanking._pending[state] = {
        "aspsp": "N26", "country": "DE", "renew": None, "created": time.time(), "days": 180,
    }
    calls = []
    monkeypatch.setattr(openbanking, "call", lambda *args, **kwargs: calls.append((args, kwargs)))

    with pytest.raises(openbanking.EBError, match="state"):
        openbanking.complete_auth(db, "https://enablebanking.com/?code=unexpected-code")

    with pytest.raises(openbanking.EBError, match="offenen Vorgang"):
        openbanking.complete_auth(db, "https://enablebanking.com/?code=unexpected-code&state=attacker-state")

    assert calls == []
    assert state in openbanking._pending

