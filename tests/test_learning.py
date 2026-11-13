"""Lernen aus Korrekturen – nur erfundene Daten."""
from kassensturz import categorize, ledger

from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _account(db, name="Testkonto", kind="giro"):
    return db.insert("accounts", {"name": name, "kind": kind})


def _rows(*items):
    return [{"booking_date": d, "amount_cents": c, "counterparty": who, "purpose": p} for d, c, who, p in items]


def _cat(db, name, kind="expense"):
    return db.insert("categories", {"name": name, "kind": kind})


def _category_of(db, counterparty):
    return [r["category_id"] for r in db.query(
        "SELECT category_id FROM transactions WHERE counterparty = ? ORDER BY id", (counterparty,))]


def test_correction_is_applied_to_similar_and_future_transactions(client, db):
    acc = _account(db)
    hobby = _cat(db, "Testhobby")
    ledger.import_rows(db, acc, _rows(
        ("2026-10-01", -1990, "Erfundener Bastelladen GmbH", "Rechnung 1"),
        ("2026-10-15", -2590, "ERFUNDENER BASTELLADEN GMBH 4711", "Rechnung 2"),
        ("2026-10-20", -500, "Anderer Laden", "Einkauf"),
    ), "datei")
    first = db.one("SELECT id FROM transactions WHERE purpose = 'Rechnung 1'")["id"]

    r = client.patch(f"/api/transactions/{first}", json={"category_id": hobby}).json()

    assert r["learned"] is True and r["recategorized"] == 1
    assert db.scalar("SELECT category_id FROM transactions WHERE purpose = 'Rechnung 2'") == hobby
    assert db.scalar("SELECT rule_ref FROM transactions WHERE purpose = 'Rechnung 2'") == "learned"
    assert db.scalar("SELECT category_id FROM transactions WHERE counterparty = 'Anderer Laden'") != hobby

    ledger.import_rows(db, acc, _rows(("2026-11-02", -1290, "Erfundener Bastelladen GmbH", "Rechnung 3")), "fints")
    assert db.scalar("SELECT category_id FROM transactions WHERE purpose = 'Rechnung 3'") == hobby


def test_income_and_expense_are_learned_separately(client, db):
    acc = _account(db)
    job = _cat(db, "Testlohn", "income")
    ledger.import_rows(db, acc, _rows(
        ("2026-10-01", 250000, "Erfundene Firma AG", "Lohn"),
        ("2026-10-05", -4000, "Erfundene Firma AG", "Kantine"),
    ), "datei")
    lohn = db.one("SELECT id FROM transactions WHERE purpose = 'Lohn'")["id"]
    client.patch(f"/api/transactions/{lohn}", json={"category_id": job})
    assert db.scalar("SELECT category_id FROM transactions WHERE purpose = 'Kantine'") != job


def test_newer_correction_replaces_the_older_one(client, db):
    acc = _account(db)
    a, b = _cat(db, "Erste"), _cat(db, "Zweite")
    ledger.import_rows(db, acc, _rows(
        ("2026-10-01", -100, "Erfundener Kiosk", "1"), ("2026-10-02", -200, "Erfundener Kiosk", "2"),
        ("2026-10-03", -300, "Erfundener Kiosk", "3"),
    ), "datei")
    ids = [r["id"] for r in db.query("SELECT id FROM transactions ORDER BY id")]
    client.patch(f"/api/transactions/{ids[0]}", json={"category_id": a})
    client.patch(f"/api/transactions/{ids[1]}", json={"category_id": b})
    # Von Hand gesetzte Buchungen bleiben, alle anderen folgen der neuesten Korrektur.
    assert _category_of(db, "Erfundener Kiosk") == [a, b, b]
    assert db.scalar("SELECT COUNT(*) FROM learned_categories") == 1


def test_payment_services_and_single_changes_are_not_learned(client, db):
    acc = _account(db)
    cat = _cat(db, "Testkategorie")
    ledger.import_rows(db, acc, _rows(
        ("2026-10-01", -100, "PayPal Europe S.a.r.l.", "Haendler A"), ("2026-10-02", -200, "PayPal Europe S.a.r.l.", "Haendler B"),
        ("2026-10-03", -300, "Erfundener Baecker", "1"), ("2026-10-04", -400, "Erfundener Baecker", "2"),
    ), "datei")
    ids = [r["id"] for r in db.query("SELECT id FROM transactions ORDER BY id")]
    assert client.patch(f"/api/transactions/{ids[0]}", json={"category_id": cat}).json()["learned"] is False
    assert client.patch(f"/api/transactions/{ids[2]}", json={"category_id": cat, "learn": False}).json()["learned"] is False
    assert db.scalar("SELECT COUNT(*) FROM learned_categories") == 0
    assert db.scalar("SELECT category_id FROM transactions WHERE id = ?", (ids[3],)) != cat


def test_explicit_rules_win_and_learned_entries_can_be_forgotten(client, db):
    acc = _account(db)
    learned, ruled = _cat(db, "Gelernt"), _cat(db, "Regel")
    ledger.import_rows(db, acc, _rows(
        ("2026-10-01", -100, "Erfundener Imbiss", "1"), ("2026-10-02", -200, "Erfundener Imbiss", "2"),
    ), "datei")
    ids = [r["id"] for r in db.query("SELECT id FROM transactions ORDER BY id")]
    client.patch(f"/api/transactions/{ids[0]}", json={"category_id": learned})
    assert db.scalar("SELECT category_id FROM transactions WHERE id = ?", (ids[1],)) == learned

    client.post("/api/rules", json={"pattern": "erfundener imbiss", "category_id": ruled})
    assert db.scalar("SELECT category_id FROM transactions WHERE id = ?", (ids[1],)) == ruled
    rule_id = client.get("/api/rules").json()[0]["id"]
    client.delete(f"/api/rules/{rule_id}")

    entry = client.get("/api/learned").json()
    assert [(e["label"], e["category_name"]) for e in entry] == [("Erfundener Imbiss", "Gelernt")]
    r = client.delete(f"/api/learned/{entry[0]['id']}").json()
    assert r["recategorized"] == 1
    assert db.scalar("SELECT category_id FROM transactions WHERE id = ?", (ids[1],)) != learned
    assert db.scalar("SELECT category_id FROM transactions WHERE id = ?", (ids[0],)) == learned


def test_deleting_a_category_forgets_what_was_learned_for_it(client, db):
    acc = _account(db)
    cat = _cat(db, "Kurzlebig")
    ledger.import_rows(db, acc, _rows(("2026-10-01", -100, "Erfundener Friseur", "1")), "datei")
    tx = db.one("SELECT id FROM transactions")["id"]
    client.patch(f"/api/transactions/{tx}", json={"category_id": cat})
    client.delete(f"/api/categories/{cat}")
    assert db.scalar("SELECT COUNT(*) FROM learned_categories") == 0


def test_app_corrections_teach_the_server(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    acc = _account(db)
    cat = _cat(db, "Aus der App")
    ledger.import_rows(db, acc, _rows(
        ("2026-10-01", -100, "Erfundene Apotheke", "1"), ("2026-10-02", -200, "Erfundene Apotheke", "2"),
        ("2026-10-03", -300, "Erfundene Apotheke", "3"),
    ), "fints")
    ids = [r["id"] for r in db.query("SELECT id FROM transactions ORDER BY id")]
    with https_client() as client:
        headers = paired_headers(client)
        r = client.patch(f"/api/v1/transactions/{ids[0]}", json={"category_id": cat}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["learned"] is True and body["also_changed"] == 2
        assert "learned" not in body["transaction"]
        assert _category_of(db, "Erfundene Apotheke") == [cat, cat, cat]

        other = _cat(db, "Nur einmal")
        r = client.patch(f"/api/v1/transactions/{ids[1]}", json={"category_id": other, "learn": False}, headers=headers)
        assert r.json()["learned"] is False and r.json()["also_changed"] == 0
        assert _category_of(db, "Erfundene Apotheke") == [cat, other, cat]
        for bad in ({"learn": True}, {"category_id": cat, "learn": "ja"}):
            assert client.patch(f"/api/v1/transactions/{ids[2]}", json=bad, headers=headers).status_code == 400


def test_learn_key_ignores_legal_forms_numbers_and_short_names():
    key = categorize.learn_key({"counterparty": "Erfundener Bastelladen GmbH 4711"})
    assert key == categorize.learn_key({"counterparty": "ERFUNDENER  BASTELLADEN"})
    assert categorize.learn_key({"counterparty": "AB"}) is None
    assert categorize.learn_key({"counterparty": ""}) is None
    assert categorize.learn_key({"counterparty": "Klarna Bank AB"}) is None
