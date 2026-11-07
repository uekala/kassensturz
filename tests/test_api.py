from datetime import date, timedelta
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
            "status": "verified",  # ignored by the ordinary save endpoint
            "sources": [{
                "title": "Offizielle Kontaktseite",
                "url": "https://www.telekom.de/kontakt",
                "source_type": "official",
                "excerpt": "Kontaktmöglichkeiten für Kunden",
            }],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["contact"]["status"] == "unverified"
    assert saved.json()["contact"]["email"] == "kuendigung@telekom.example"
    assert len(saved.json()["sources"]) == 1

    event = client.post(
        f"/api/contracts/{key}/cancellation-events",
        json={"mode": "ordinary"},
    )
    assert event.status_code == 200
    assert event.json()["status"] == "prepared"
    assert event.json()["user_confirmed_sent_at"] is None
    history = client.get(f"/api/contracts/{key}/cancellation-events")
    assert history.status_code == 200
    assert [item["id"] for item in history.json()["items"]] == [event.json()["id"]]
    premature = client.post(
        f"/api/contracts/{key}/cancellation-events/{event.json()['id']}/confirm-sent",
        json={"user_confirmed_sent": True},
    )
    assert premature.status_code == 409
    handoff = client.post(f"/api/contracts/{key}/cancellation-events/{event.json()['id']}/handoff")
    assert handoff.status_code == 200
    assert handoff.json()["status"] == "handed_off"
    missing_confirmation = client.post(
        f"/api/contracts/{key}/cancellation-events/{event.json()['id']}/confirm-sent",
        json={"user_confirmed_sent": False},
    )
    assert missing_confirmation.status_code == 400
    sent = client.post(
        f"/api/contracts/{key}/cancellation-events/{event.json()['id']}/confirm-sent",
        json={"user_confirmed_sent": True},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["user_confirmed_sent_at"] is not None
    denied_received = client.post(
        f"/api/contracts/{key}/cancellation-events/{event.json()['id']}/confirm-received",
        json={"user_confirmed_received": False},
    )
    assert denied_received.status_code == 400
    received = client.post(
        f"/api/contracts/{key}/cancellation-events/{event.json()['id']}/confirm-received",
        json={"user_confirmed_received": True},
    )
    assert received.status_code == 200
    assert received.json()["status"] == "provider_confirmed"
    assert received.json()["provider_confirmed_at"] is not None

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



def test_confirmed_provider_contact_requires_user_confirmation_and_saved_source(client):
    client.post("/api/demo")
    contract = next(
        c for c in client.get("/api/contracts").json()["items"]
        if c["name"] == "Telekom Deutschland GmbH"
    )
    key = contract["key"]
    source_url = "https://www.telekom.de/kontakt"
    client.put(
        f"/api/contracts/{key}/cancellation-contact",
        json={"status": "unverified", "sources": [{
            "title": "Telekom Kontakt", "url": source_url,
            "source_type": "search_candidate", "excerpt": "Kontaktseite",
        }]},
    )
    denied = client.post(
        f"/api/contracts/{key}/cancellation-contact/confirm",
        json={"user_confirmed": False, "source_url": source_url, "email": "kuendigung@telekom.example"},
    )
    assert denied.status_code == 400

    accepted = client.post(
        f"/api/contracts/{key}/cancellation-contact/confirm",
        json={"user_confirmed": True, "source_url": source_url, "email": "kuendigung@telekom.example"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["contact"]["status"] == "verified"
    updated = next(c for c in client.get("/api/contracts").json()["items"] if c["key"] == key)
    assert updated["provider_email"] == "kuendigung@telekom.example"
    assert accepted.json()["contract_fields_updated"] == ["provider_email"]


def test_confirmed_provider_contact_does_not_overwrite_manual_email(client):
    client.post("/api/demo")
    contract = next(
        c for c in client.get("/api/contracts").json()["items"]
        if c["name"] == "Telekom Deutschland GmbH"
    )
    key = contract["key"]
    client.patch(f"/api/contracts/{key}", json={"provider_email": "existing@example.org"})
    source_url = "https://www.telekom.de/kontakt"
    client.put(
        f"/api/contracts/{key}/cancellation-contact",
        json={"sources": [{"title": "Kontakt", "url": source_url}]},
    )
    response = client.post(
        f"/api/contracts/{key}/cancellation-contact/confirm",
        json={"user_confirmed": True, "source_url": source_url, "email": "new@example.org"},
    )
    assert response.status_code == 409



def test_cancellation_deadline_alerts_are_staged(client):
    client.post("/api/demo")
    contract = next(
        item for item in client.get("/api/contracts").json()["items"]
        if item["name"] == "Telekom Deutschland GmbH"
    )
    key = contract["key"]

    # Vertragsende 70 Tage entfernt, Kündigungsfrist ein Monat:
    # Die erste Erinnerung soll in der 45-Tage-Stufe erscheinen.
    client.patch(
        f"/api/contracts/{key}",
        json={"contract_end": (date.today() + timedelta(days=70)).isoformat(), "notice_months": 1},
    )
    overview = client.get("/api/overview").json()
    reminder = next(
        alert for alert in overview["alerts"]
        if alert.get("contract") == key and alert["key"].startswith("deadline:")
    )
    assert ":45d:" in reminder["key"]
    assert reminder["level"] == "warning"

    # Bei näher rückender Frist wird eine neue, getrennte Erinnerungsstufe fällig.
    client.patch(
        f"/api/contracts/{key}",
        json={"contract_end": (date.today() + timedelta(days=50)).isoformat(), "notice_months": 1},
    )
    overview = client.get("/api/overview").json()
    reminder = next(
        alert for alert in overview["alerts"]
        if alert.get("contract") == key and alert["key"].startswith("deadline:")
    )
    assert ":21d:" in reminder["key"]



def test_unconfirmed_cancellation_event_reminder(client, db):
    from datetime import datetime, timedelta

    client.post("/api/demo")
    contract = next(
        item for item in client.get("/api/contracts").json()["items"]
        if item["name"] == "Telekom Deutschland GmbH"
    )
    key = contract["key"]
    event = client.post(
        f"/api/contracts/{key}/cancellation-events",
        json={"mode": "ordinary"},
    ).json()

    # Freshly prepared cancellations must not trigger a reminder yet.
    alerts = client.get("/api/overview").json()["alerts"]
    assert not any(a["key"] == f"cancellation-pending:{event['id']}" for a in alerts)

    # After 24 hours without explicit send confirmation, a warning appears.
    old = (datetime.now() - timedelta(hours=25)).replace(microsecond=0).isoformat()
    db.conn.execute(
        "UPDATE cancellation_events SET prepared_at = ? WHERE id = ?",
        (old, event["id"]),
    )
    alerts = client.get("/api/overview").json()["alerts"]
    reminder = next(a for a in alerts if a["key"] == f"cancellation-pending:{event['id']}")
    assert reminder["contract"] == key
    assert reminder["level"] == "warning"
    assert "tatsächlich versendet" in reminder["text"]

    # After explicit send confirmation, the reminder disappears.
    client.post(f"/api/contracts/{key}/cancellation-events/{event['id']}/handoff")
    sent = client.post(
        f"/api/contracts/{key}/cancellation-events/{event['id']}/confirm-sent",
        json={"user_confirmed_sent": True},
    )
    assert sent.status_code == 200
    alerts = client.get("/api/overview").json()["alerts"]
    assert not any(a["key"] == f"cancellation-pending:{event['id']}" for a in alerts)


def test_unconfirmed_cancellation_event_reminder_ignores_cancelled_contract(client, db):
    from datetime import datetime, timedelta

    client.post("/api/demo")
    contract = next(
        item for item in client.get("/api/contracts").json()["items"]
        if item["name"] == "Telekom Deutschland GmbH"
    )
    key = contract["key"]
    event = client.post(
        f"/api/contracts/{key}/cancellation-events",
        json={"mode": "ordinary"},
    ).json()
    old = (datetime.now() - timedelta(hours=25)).replace(microsecond=0).isoformat()
    db.conn.execute("UPDATE cancellation_events SET prepared_at = ? WHERE id = ?", (old, event["id"]))
    client.patch(f"/api/contracts/{key}", json={"status": "cancelled"})
    alerts = client.get("/api/overview").json()["alerts"]
    assert not any(a["key"] == f"cancellation-pending:{event['id']}" for a in alerts)



def test_cancellation_reminder_days_are_configurable(client, monkeypatch):
    from kassensturz import options

    client.post("/api/demo")
    contract = next(
        item for item in client.get("/api/contracts").json()["items"]
        if item["name"] == "Telekom Deutschland GmbH"
    )
    key = contract["key"]
    configured = dict(options.DEFAULTS, cancellation_reminder_days="30,10")
    monkeypatch.setattr(options, "load", lambda: configured)

    # 25 Tage bis zur Kündigungsfrist: erste, 30-Tage-Stufe.
    client.patch(
        f"/api/contracts/{key}",
        json={"contract_end": (date.today() + timedelta(days=55)).isoformat(), "notice_months": 1},
    )
    alerts = client.get("/api/overview").json()["alerts"]
    reminder = next(a for a in alerts if a.get("contract") == key and a["key"].startswith("deadline:"))
    assert ":30d:" in reminder["key"] and reminder["level"] == "warning"

    # 8 Tage bis zur Frist: letzte, kritische 10-Tage-Stufe.
    client.patch(
        f"/api/contracts/{key}",
        json={"contract_end": (date.today() + timedelta(days=38)).isoformat(), "notice_months": 1},
    )
    alerts = client.get("/api/overview").json()["alerts"]
    reminder = next(a for a in alerts if a.get("contract") == key and a["key"].startswith("deadline:"))
    assert ":10d:" in reminder["key"] and reminder["level"] == "critical"


def test_invalid_cancellation_reminder_days_fall_back_to_defaults(monkeypatch):
    from kassensturz import options

    monkeypatch.setattr(options, "load", lambda: dict(options.DEFAULTS, cancellation_reminder_days="0,abc,999"))
    assert options.cancellation_reminder_days() == [7, 21, 45]
