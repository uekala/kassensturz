from conftest import fixture_bytes


def test_import_flow_creates_account_and_dedups(client):
    r = client.post("/api/import/analyze", files={"file": ("ing.csv", fixture_bytes("ing.csv"), "text/csv")})
    assert r.status_code == 200
    a = r.json()
    assert a["format"] == "ING" and a["count"] == 3 and a["account_id"] is None
    r = client.post("/api/import/commit", json={"token": a["token"], "new_account": {"name": "ING", "kind": "giro"}})
    assert r.json()["added"] == 3 and r.json()["balance_known"] is True
    # Zweiter Import derselben Datei: Konto wird über IBAN erkannt, nichts doppelt
    a2 = client.post("/api/import/analyze", files={"file": ("ing.csv", fixture_bytes("ing.csv"), "text/csv")}).json()
    assert a2["account_id"] == r.json()["account_id"]
    r2 = client.post("/api/import/commit", json={"token": a2["token"], "account_id": a2["account_id"]})
    assert r2.json() == {"added": 0, "skipped": 3, "account_id": a2["account_id"], "balance_known": True}
    accs = client.get("/api/accounts").json()
    assert accs[0]["balance_now"] == 123456


def test_category_change_with_rule(client):
    a = client.post("/api/import/analyze", files={"file": ("n26.csv", fixture_bytes("n26.csv"), "text/csv")}).json()
    client.post("/api/import/commit", json={"token": a["token"]})
    tx = client.get("/api/transactions?q=Starbucks").json()["items"][0]
    cats = {c["builtin_key"]: c["id"] for c in client.get("/api/categories").json()}
    sug = client.get(f"/api/transactions/{tx['id']}/suggest-rule").json()
    assert sug["pattern"] == "starbucks"
    r = client.patch(f"/api/transactions/{tx['id']}", json={"category_id": cats["restaurant"], "rule": {"pattern": "starbucks", "sign": "out"}})
    assert r.status_code == 200
    assert client.get("/api/rules").json()[0]["pattern"] == "starbucks"


def test_splits_validation(client):
    a = client.post("/api/import/analyze", files={"file": ("amex.csv", fixture_bytes("amex.csv"), "text/csv")}).json()
    client.post("/api/import/commit", json={"token": a["token"]})
    tx = client.get("/api/transactions?q=TESLA").json()["items"][0]
    cats = {c["builtin_key"]: c["id"] for c in client.get("/api/categories").json()}
    bad = client.put(f"/api/transactions/{tx['id']}/splits", json={"splits": [{"amount_cents": -5000, "category_id": cats["laden"]}]})
    assert bad.status_code == 400
    ok = client.put(f"/api/transactions/{tx['id']}/splits", json={"splits": [{"amount_cents": -1000, "category_id": cats["restaurant"]}]})
    assert ok.status_code == 200
    st = client.get("/api/stats?month=2026-10").json()["month"]
    names = {b["name"]: b["cents"] for b in st["breakdown"]}
    assert names["Freizeit"] == 1000 and names["Mobilität"] == 2450


def test_demo_overview_and_letter(client):
    client.post("/api/demo")
    o = client.get("/api/overview").json()
    assert o["forecast"]["accounts"] and o["price_changes"] == 1
    assert any("teurer" in a["title"] for a in o["alerts"])
    c = next(c for c in client.get("/api/contracts").json()["items"] if c["name"] == "Telekom Deutschland GmbH")
    client.patch(f"/api/contracts/{c['key']}", json={"customer_no": "512345678", "provider_email": "kuendigung@example.org"})
    client.put("/api/settings", json={"profile": {"name": "Max Muster", "street": "Weg 1", "city": "12345 Musterstadt"}})
    letter = client.post("/api/letter", json={"key": c["key"], "mode": "ordentlich"}).json()
    assert "512345678" in letter["letter"] and "TK512345678" in letter["letter"] and letter["mailto"].startswith("mailto:")
    assert "Musterstadt, " in letter["letter"]
    client.delete("/api/demo")
    assert client.get("/api/state").json()["accounts"] == 0


def test_export_csv(client):
    client.post("/api/demo")
    r = client.get("/api/export.csv")
    assert r.status_code == 200 and r.text.lstrip("﻿").startswith("Buchungstag;")


def test_ingress_only(db):
    from fastapi.testclient import TestClient

    from kassensturz import main

    with TestClient(main.app, client=("203.0.113.25", 50123)) as c:
        assert c.get("/api/state").status_code == 403


def test_cancellation_contact_sources_and_event(client):
    client.post("/api/demo")
    contract = next(
        c for c in client.get("/api/contracts").json()["items"]
        if c["name"] == "Telekom Deutschland GmbH"
    )
    key = contract["key"]
    empty = client.get(f"/api/contracts/{key}/cancellation-contact").json()
    assert empty["contact"] is None and empty["sources"] == []

    saved = client.put(
        f"/api/contracts/{key}/cancellation-contact",
        json={
            "email": "kuendigung@telekom.example",
            "postal_address": "Telekom Kundenservice, 53171 Bonn",
            "cancellation_url": "https://www.telekom.de/kontakt",
            "status": "verified",
            "sources": [{
                "title": "Offizielle Kontaktseite",
                "url": "https://www.telekom.de/kontakt",
                "source_type": "official",
                "excerpt": "Kontaktmöglichkeiten für Kunden",
            }],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["contact"]["status"] == "verified"
    assert saved.json()["contact"]["email"] == "kuendigung@telekom.example"
    assert len(saved.json()["sources"]) == 1

    event = client.post(
        f"/api/contracts/{key}/cancellation-events",
        json={"mode": "ordinary"},
    )
    assert event.status_code == 200
    assert event.json()["status"] == "prepared"
    assert event.json()["user_confirmed_sent_at"] is None

    invalid = client.put(
        f"/api/contracts/{key}/cancellation-contact",
        json={"contact_url": "http://example.org"},
    )
    assert invalid.status_code == 400




def test_cancellation_source_preflight_api(client, monkeypatch):
    import socket

    from kassensturz import provider_research

    client.post("/api/demo")
    contract = next(
        c for c in client.get("/api/contracts").json()["items"]
        if c["name"] == "Telekom Deutschland GmbH"
    )
    monkeypatch.setattr(
        provider_research.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    result = client.post(
        f"/api/contracts/{contract['key']}/cancellation-source-check",
        json={"url": "https://www.telekom.de/kontakt"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "public_host_only"
    assert result.json()["verified"] is False

    rejected = client.post(
        f"/api/contracts/{contract['key']}/cancellation-source-check",
        json={"url": "http://127.0.0.1/"},
    )
    assert rejected.status_code == 400
