"""Erinnerung vor Ablauf der Bankfreigabe und Vermögensverlauf für die App – erfundene Daten."""
from datetime import date, datetime, timedelta, timezone

import pytest

from kassensturz import ledger, openbanking, services
from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _grant(db, days):
    valid = (datetime.now(timezone.utc) + timedelta(days=days, hours=1)).isoformat()
    return db.insert("eb_sessions", {"session_id": "x", "aspsp_name": "Erfundene Bank", "aspsp_country": "DE",
                                     "valid_until": valid, "status": "active"})


def _alerts(db):
    return [a for a in services.alerts(db, services.build_summary(db)) if a["key"].startswith("eb-")]


@pytest.mark.parametrize("days, stage, words", [(14, 14, "Noch 14 Tage."), (9, 14, "Noch 9 Tage."), (7, 7, "Noch 7 Tage."),
                                                (3, 7, "Noch 3 Tage."), (2, 2, "Noch 2 Tage."), (1, 2, "Noch 1 Tag."),
                                                (0, 2, "Heute ist der letzte Tag.")])
def test_grant_reminder_has_three_stages(db, monkeypatch, days, stage, words):
    monkeypatch.setattr(openbanking, "is_configured", lambda _db: True)
    grant = _grant(db, days)
    found = _alerts(db)
    assert len(found) == 1
    assert found[0]["key"].startswith(f"eb-expiring:{grant}:") and found[0]["key"].endswith(f":{stage}")
    assert found[0]["text"].startswith(words)


def test_no_reminder_early_and_expired_is_named(db, monkeypatch):
    monkeypatch.setattr(openbanking, "is_configured", lambda _db: True)
    _grant(db, 15)
    assert _alerts(db) == []
    db.execute("UPDATE eb_sessions SET valid_until = ?", ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),))
    assert [a["title"] for a in _alerts(db)] == ["Freigabe für Erfundene Bank abgelaufen"]


def test_app_reads_the_net_worth_history(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    start = (date.today().replace(day=1) - timedelta(days=70)).isoformat()
    ledger.import_rows(db, acc, [{"booking_date": start, "amount_cents": 100000, "counterparty": "Erfundener Start", "purpose": "Test"}], "datei")
    ledger.set_balance_anchor(db, acc, 100000, date.today().isoformat())
    with https_client() as client:
        assert client.get("/api/v1/networth").status_code == 401
        history = client.get("/api/v1/networth", headers=paired_headers(client)).json()["history"]
        assert history == ledger.net_worth_history(db)
    assert history[-1] == {"date": date.today().isoformat(), "cents": 100000}
    assert all(set(point) == {"date", "cents"} for point in history)
