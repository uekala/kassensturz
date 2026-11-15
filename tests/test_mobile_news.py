"""Neuigkeiten je Gerät und Papierkram-Übersicht – nur erfundene Daten."""
from datetime import date, timedelta

from kassensturz import ledger, papers
from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _book(db, acc, day, cents, who, transfer=0):
    ledger.import_rows(db, acc, [{"booking_date": day, "amount_cents": cents, "counterparty": who, "purpose": "Test"}], "fints")
    tx = db.scalar("SELECT MAX(id) FROM transactions")
    db.update("transactions", "id", tx, {"is_transfer": transfer})
    return tx


def test_news_start_empty_then_list_what_arrived_until_read(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    _book(db, acc, "2026-11-01", -5000, "Erfundener Altbestand")
    with https_client() as client:
        assert client.get("/api/v1/news").status_code == 401
        assert client.post("/api/v1/news/seen").status_code == 401
        headers = paired_headers(client)
        assert client.get("/api/v1/news", headers=headers).json() == {"count": 0, "income_cents": 0, "expense_cents": 0, "largest": []}

        _book(db, acc, "2026-11-10", -1250, "Erfundene Bäckerei")
        _book(db, acc, "2026-11-11", 280000, "Erfundene Firma GmbH")
        _book(db, acc, "2026-11-12", -64000, "Erfundener Vermieter")
        _book(db, acc, "2026-11-12", -900, "Erfundener Kiosk")
        _book(db, acc, "2026-11-12", -50000, "Erfundene Umbuchung", transfer=1)
        data = client.get("/api/v1/news", headers=headers).json()
        assert (data["count"], data["income_cents"], data["expense_cents"]) == (4, 280000, 66150)
        assert [(i["label"], i["amount_cents"]) for i in data["largest"]] == [
            ("Erfundene Firma GmbH", 280000), ("Erfundener Vermieter", -64000), ("Erfundene Bäckerei", -1250)]
        assert data["largest"][0]["account_name"] == "Testgiro"
        assert client.get("/api/v1/news", headers=headers).json()["count"] == 4

        assert client.post("/api/v1/news/seen", headers=headers).json() == {"ok": True}
        assert client.get("/api/v1/news", headers=headers).json()["count"] == 0
        _book(db, acc, "2026-11-13", -300, "Erfundener Automat")
        assert client.get("/api/v1/news", headers=headers).json()["count"] == 1


def test_news_marker_survives_deleted_transactions_and_forgets_old_devices(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    tx = _book(db, acc, "2026-11-01", -5000, "Erfundener Altbestand")
    db.set_setting("mobile_news_seen", {"altes-geraet": 1})
    with https_client() as client:
        headers = paired_headers(client)
        client.get("/api/v1/news", headers=headers)
        db.execute("DELETE FROM transactions WHERE id = ?", (tx,))
        assert client.get("/api/v1/news", headers=headers).json()["count"] == 0
        client.post("/api/v1/news/seen", headers=headers)
        marks = db.get_setting("mobile_news_seen")
        assert "altes-geraet" not in marks and len(marks) == 1


def test_papers_overview_sums_tax_and_lists_warranties(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    a = _book(db, acc, "2026-03-10", -48000, "Erfundener Malerbetrieb")
    b = _book(db, acc, "2026-06-01", -5000, "Erfundener Verein")
    c = _book(db, acc, "2025-01-15", -59900, "Erfundener Elektromarkt")
    db.update("transactions", "id", a, {"tax_kind": "handwerker"})
    db.update("transactions", "id", b, {"tax_kind": "spende"})
    db.update("transactions", "id", c, {"warranty_until": (date.today() + timedelta(days=20)).isoformat(), "note": "Erfundene Waschmaschine"})
    papers.add_receipt(db, a, "a.pdf", b"%PDF-1.4\n")
    with https_client() as client:
        assert client.get("/api/v1/papers").status_code == 401
        headers = paired_headers(client)
        data = client.get("/api/v1/papers?year=2026", headers=headers).json()
        assert data["tax"]["year"] == 2026 and data["tax"]["total_cents"] == 53000 and data["tax"]["missing_receipts"] == 1
        assert data["tax"]["groups"] == [
            {"kind": "handwerker", "label": "Handwerkerleistung", "count": 1, "total_cents": 48000, "missing_receipts": 0},
            {"kind": "spende", "label": "Spende", "count": 1, "total_cents": 5000, "missing_receipts": 1}]
        assert "items" not in str(data["tax"])
        assert data["warranties"]["running"] == [{"id": c, "label": "Erfundene Waschmaschine", "amount_cents": -59900,
                                                  "booking_date": "2025-01-15", "warranty_until": (date.today() + timedelta(days=20)).isoformat(),
                                                  "days_left": 20, "receipt_count": 0}]
        assert data["warranties"]["expired"] == []
        assert client.get("/api/v1/papers", headers=headers).json()["tax"]["year"] == 2026
        assert client.get("/api/v1/papers?year=abcd", headers=headers).status_code == 400
