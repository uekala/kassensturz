from datetime import date, timedelta

from kassensturz import analytics, categorize, contracts, demo, ledger
from kassensturz.db import now_iso


def _acc(db, **kw):
    data = {"name": "Giro", "kind": "giro", "in_forecast": 1, "created": now_iso()}
    data.update(kw)
    return db.insert("accounts", data)


def _row(d, cents, cp="Test", purpose="", **kw):
    r = {"booking_date": d, "value_date": d, "amount_cents": cents, "currency": "EUR", "counterparty": cp, "purpose": purpose}
    r.update(kw)
    return r


def test_overlapping_imports_do_not_duplicate(db):
    aid = _acc(db)
    a = [_row("2026-10-01", -350, "Bäcker"), _row("2026-10-01", -350, "Bäcker"), _row("2026-10-02", -1000, "REWE")]
    assert ledger.import_rows(db, aid, a, "datei")["added"] == 3
    # gleicher Zeitraum aus anderer Quelle mit anderem Text: nichts Neues
    b = [_row("2026-10-01", -350, "BAECKER GMBH", "Kartenzahlung"), _row("2026-10-01", -350, "BAECKER GMBH"),
         _row("2026-10-02", -1000, "REWE Markt GmbH")]
    assert ledger.import_rows(db, aid, b, "fints")["added"] == 0
    # ein dritter Kaffee am selben Tag ist neu
    c = b + [_row("2026-10-01", -350, "BAECKER GMBH")]
    assert ledger.import_rows(db, aid, c, "fints")["added"] == 1


def test_balance_anchor(db):
    aid = _acc(db)
    ledger.import_rows(db, aid, [_row("2026-10-01", -1000), _row("2026-10-05", 5000)], "datei",
                       meta={"balance_cents": 10000, "balance_date": "2026-10-01"})
    acc = db.one("SELECT * FROM accounts WHERE id = ?", (aid,))
    assert ledger.current_balance(db, acc) == 15000
    # älterer Saldo überschreibt keinen neueren
    ledger.import_rows(db, aid, [], "datei", meta={"balance_cents": 1, "balance_date": "2026-09-01"})
    acc = db.one("SELECT * FROM accounts WHERE id = ?", (aid,))
    assert acc["balance_cents"] == 10000


def test_transfers_between_tracked_accounts(db):
    giro = _acc(db, iban="DE02300501101234567890")
    pp = _acc(db, name="PayPal", kind="paypal", settlement_pattern="paypal")
    card = _acc(db, name="Amex", kind="kreditkarte", settlement_pattern="american express")
    save = _acc(db, name="Tagesgeld", kind="tagesgeld", iban="DE12320500000087654321")
    ledger.import_rows(db, giro, [
        _row("2026-10-03", -2000, "PayPal Europe S.a.r.l. et Cie S.C.A", "Ihr Einkauf"),
        _row("2026-10-06", -15000, "American Express Europe S.A.", "Abrechnung"),
        _row("2026-10-07", -50000, "Max Muster", "Sparen", counterparty_iban="DE12320500000087654321"),
        _row("2026-10-08", -3417, "REWE Markt GmbH", "Kartenzahlung"),
    ], "datei")
    ledger.import_rows(db, pp, [_row("2026-10-03", 2000, None, "", booking_text="Bankgutschrift auf PayPal-Konto"),
                                _row("2026-10-03", -2000, "Zalando SE", "Sneaker")], "datei")
    ledger.import_rows(db, card, [_row("2026-10-06", 15000, "ZAHLUNG ERHALTEN. BESTEN DANK")], "datei")
    rows = {(r["account_id"], r["amount_cents"]): r for r in db.query(
        "SELECT t.*, c.builtin_key FROM transactions t LEFT JOIN categories c ON c.id = t.category_id")}
    assert rows[(giro, -2000)]["is_transfer"] == 1
    assert rows[(giro, -15000)]["is_transfer"] == 1
    assert rows[(giro, -50000)]["is_transfer"] == 1
    assert rows[(giro, -3417)]["builtin_key"] == "supermarkt"
    assert rows[(pp, 2000)]["is_transfer"] == 1
    assert rows[(pp, -2000)]["builtin_key"] == "online"
    assert rows[(card, 15000)]["is_transfer"] == 1
    assert save


def test_user_rule_wins_and_recategorizes(db):
    aid = _acc(db)
    ledger.import_rows(db, aid, [_row("2026-10-01", -2000, "Kiosk Müller", "Zeitschrift")], "datei")
    cat = db.scalar("SELECT id FROM categories WHERE builtin_key = 'presse'")
    db.insert("rules", {"pattern": "kiosk müller", "field": "any", "sign": "out", "category_id": cat, "priority": 100, "enabled": 1})
    assert categorize.recategorize(db) == 1
    assert db.scalar("SELECT category_id FROM transactions") == cat


def test_demo_detects_contracts_and_forecast(db):
    demo.load_demo(db)
    contracts.detect(db)
    cons = {c["name"]: c for c in contracts.list_contracts(db)}
    assert cons["Netflix.com"]["price_change_cents"] == -200
    assert cons["Telekom Deutschland GmbH"]["interval"] == "monatlich"
    assert cons["Rundfunk ARD, ZDF, DRadio"]["interval"] == "vierteljährlich"
    assert cons["Muster Systemhaus GmbH"]["kind"] == "income"
    assert not any("Supercharger" in n for n in cons)
    fc = analytics.forecast(db)
    assert fc["period_label"] == "bis zum nächsten Gehalt"
    assert fc["free_cents"] == fc["balance_now"] + fc["fixed_in_cents"] + fc["fixed_out_cents"]
    assert len(fc["future"]) == analytics.HORIZON_DAYS
    # Umbuchungen tauchen in Monatsausgaben nicht auf
    st = analytics.month_stats(db, (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))
    assert all(b["name"] != "Umbuchung" for b in st["breakdown"])


def test_cancelled_contract_leaves_forecast(db):
    demo.load_demo(db)
    contracts.detect(db)
    c = next(c for c in contracts.list_contracts(db) if c["name"] == "Netflix.com")
    before = [u for u in contracts.upcoming(db, date.today(), date.today() + timedelta(days=60)) if u["key"] == c["key"]]
    assert before
    db.update("contracts", "key", c["key"], {"status": "cancelled", "cancel_effective": date.today().isoformat()})
    after = [u for u in contracts.upcoming(db, date.today() + timedelta(days=1), date.today() + timedelta(days=60)) if u["key"] == c["key"]]
    assert after == []


def test_exact_existing_transaction_does_not_hide_new_same_amount_transaction(db):
    aid = _acc(db)
    existing = _row("2026-11-06", -2500, "REWE Markt GmbH", "Kartenzahlung")
    assert ledger.import_rows(db, aid, [existing], "csv")["added"] == 1

    overlapping = [
        _row("2026-11-06", -2500, "REWE Markt GmbH", "Kartenzahlung"),
        _row("2026-11-06", -2500, "Shell Tankstelle", "Kartenzahlung"),
    ]
    result = ledger.import_rows(db, aid, overlapping, "fints")

    assert result["added"] == 1
    rows = db.query(
        "SELECT counterparty FROM transactions WHERE account_id = ? AND booking_date = ? AND amount_cents = ?",
        (aid, "2026-11-06", -2500),
    )
    assert sorted(r["counterparty"] for r in rows) == ["REWE Markt GmbH", "Shell Tankstelle"]
