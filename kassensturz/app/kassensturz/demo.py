"""Beispieldaten zum Ausprobieren – ohne echte Bankverbindung."""
from __future__ import annotations

import random
from datetime import date, timedelta

from . import ledger
from .db import Database, now_iso
from .util import add_months

DEMO_MONTHS = 7


def _d(day: date) -> str:
    return day.isoformat()


def load_demo(db: Database) -> dict:
    remove_demo(db)
    rnd = random.Random(42)
    today = date.today()
    start = add_months(date(today.year, today.month, 1), -DEMO_MONTHS)

    giro = db.insert("accounts", {"name": "Girokonto", "kind": "giro", "iban": "DE02300501101234567890", "bank": "Beispielbank",
                                  "in_forecast": 1, "demo": 1, "sort": 1, "created": now_iso()})
    paypal = db.insert("accounts", {"name": "PayPal", "kind": "paypal", "settlement_pattern": "paypal", "in_forecast": 1, "demo": 1,
                                    "sort": 2, "created": now_iso()})
    amex = db.insert("accounts", {"name": "American Express", "kind": "kreditkarte", "settlement_pattern": "american express",
                                  "in_forecast": 1, "demo": 1, "sort": 3, "created": now_iso()})
    rows = {giro: [], paypal: [], amex: []}

    def add(acc, day, cents, cp, purpose="", btext=None, cred=None, mref=None, iban=None):
        if day > today:
            return
        rows[acc].append({"booking_date": _d(day), "value_date": _d(day), "amount_cents": cents, "currency": "EUR",
                          "counterparty": cp, "counterparty_iban": iban, "purpose": purpose, "booking_text": btext,
                          "creditor_id": cred, "mandate_ref": mref, "end_to_end": None})

    m = start
    amex_month_total = {}
    while m <= today:
        y, mo = m.year, m.month
        def day(n):
            return date(y, mo, min(n, 28))
        add(giro, day(1), -105000, "Wohnbau Musterstadt eG", "Miete Wohnung 3.OG links", "DAUERAUFTRAG", iban="DE89370400440532013000")
        add(giro, day(28), 345012, "Muster Systemhaus GmbH", f"LOHN/GEHALT {mo:02d}/{y}", "LOHN, GEHALT, RENTE")
        add(giro, day(15), -8900, "Stadtwerke Musterstadt AG", "Abschlag Strom Vertragskonto 400123", "FOLGELASTSCHRIFT",
            cred="DE62ZZZ00000012345", mref="SWK-400123")
        add(giro, day(5), -4495, "Telekom Deutschland GmbH", "Festnetz/Internet Kd-Nr 512345678", "FOLGELASTSCHRIFT",
            cred="DE76ZZZ00000002341", mref="TK512345678")
        add(giro, day(3), -2990, "FitX Deutschland GmbH", "Mitgliedsbeitrag", "FOLGELASTSCHRIFT", cred="DE21ZZZ00000999111", mref="FITX-88812")
        add(giro, day(2), -20000, "Trade Republic Bank GmbH", "Sparplan ETF", "FOLGELASTSCHRIFT", cred="DE11ZZZ00001234567", mref="TR-SP-1")
        if mo in (1, 4, 7, 10):
            add(giro, day(15), -5508, "Rundfunk ARD, ZDF, DRadio", "Beitragsnummer 123456789", "FOLGELASTSCHRIFT",
                cred="DE45ZZZ00000002222", mref="RB123456789")
        if mo in (2, 5, 8, 11):
            add(giro, day(10), -1890, "Allianz Versicherungs-AG", "Privathaftpflicht Vers.-Nr. AS-77812", "FOLGELASTSCHRIFT",
                cred="DE33ZZZ00000004444", mref="AS77812")
        # Lebensmittel und Alltag
        d = date(y, mo, 1)
        while d.month == mo and d <= today:
            if d.weekday() in (1, 4) or rnd.random() < 0.12:
                shop = rnd.choice(["REWE Markt GmbH", "ALDI SUED", "LIDL DIENSTL GMBH", "EDEKA Center"])
                add(giro, d, -rnd.randint(1200, 9800), shop, "Kartenzahlung girocard", "KARTENZAHLUNG")
            if rnd.random() < 0.06:
                add(giro, d, -rnd.randint(800, 3600), "dm-drogerie markt", "Kartenzahlung", "KARTENZAHLUNG")
            if rnd.random() < 0.05:
                add(giro, d, -rnd.choice([5000, 10000]), "Sparkasse Musterstadt", "GA 123 Bargeldauszahlung", "BARGELDAUSZAHLUNG")
            if rnd.random() < 0.10:
                add(amex, d, -rnd.randint(1800, 5200), "TESLA SUPERCHARGER", "Supercharger Session")
            if rnd.random() < 0.08:
                cents = rnd.randint(1500, 6500)
                add(amex, d, -cents, rnd.choice(["Lieferando.de", "L'Osteria", "Vapiano"]), "Restaurant")
            if rnd.random() < 0.05:
                cents = rnd.randint(1200, 8900)
                add(paypal, d, cents, None, "", "Bankgutschrift auf PayPal-Konto")
                add(paypal, d, -cents, rnd.choice(["eBay GmbH", "Zalando SE", "Decathlon Deutschland"]), "Bestellung", "Express-Checkout-Zahlung")
                add(giro, d, -cents, "PayPal Europe S.a.r.l. et Cie S.C.A", f"PP.{rnd.randint(1000,9999)}.PP . Ihr Einkauf bei", "FOLGELASTSCHRIFT",
                    cred="LU96ZZZ0000000000000000058", mref=f"PAYPAL-{rnd.randint(100000,999999)}")
            if rnd.random() < 0.05:
                add(amex, d, -rnd.randint(1500, 12000), "AMAZON EU S.A R.L.", "Amazon.de Bestellung")
            d += timedelta(days=1)
        # Abos
        netflix = -1399 if m < add_months(date(today.year, today.month, 1), -1) else -1599
        add(amex, day(12), netflix, "NETFLIX.COM", "Netflix Abo")
        add(paypal, day(20), 1099, None, "", "Bankgutschrift auf PayPal-Konto")
        add(paypal, day(20), -1099, "Spotify AB", "Spotify Premium", "Abo-Zahlung")
        add(giro, day(20), -1099, "PayPal Europe S.a.r.l. et Cie S.C.A", "PP.4711.PP . Spotify AB", "FOLGELASTSCHRIFT",
            cred="LU96ZZZ0000000000000000058", mref="PAYPAL-SPOTIFY")
        add(amex, day(8), -299, "Google Storage", "Google One 100 GB")
        amex_month_total[(y, mo)] = 0
        m = add_months(m, 1)

    # Amex-Abrechnung: Summe des Vormonats wird am 6. vom Girokonto eingezogen
    for (y, mo) in list(amex_month_total):
        total = sum(-r["amount_cents"] for r in rows[amex] if r["booking_date"].startswith(f"{y}-{mo:02d}") and r["amount_cents"] < 0)
        nxt = add_months(date(y, mo, 1), 1)
        pay_day = date(nxt.year, nxt.month, 6)
        if total and pay_day <= today:
            add(giro, pay_day, -total, "American Express Europe S.A.", "Kartenabrechnung", "FOLGELASTSCHRIFT",
                cred="DE87ZZZ00000014422", mref="AMEX-376000")
            add(amex, pay_day, total, "ZAHLUNG ERHALTEN. BESTEN DANK", "")

    for acc, rs in rows.items():
        ledger.import_rows(db, acc, rs, "demo", "Beispieldaten")
    open_amex = sum(r["amount_cents"] for r in rows[amex]) if rows[amex] else 0
    ledger.set_balance_anchor(db, giro, 243117, today.isoformat())
    ledger.set_balance_anchor(db, paypal, 0, today.isoformat())
    month_charges = sum(r["amount_cents"] for r in rows[amex] if r["booking_date"] >= date(today.year, today.month, 1).isoformat()
                        and r["amount_cents"] < 0)
    prev = add_months(date(today.year, today.month, 1), -1)
    prev_unpaid = 0
    if today.day < 6:
        prev_unpaid = sum(r["amount_cents"] for r in rows[amex] if r["booking_date"].startswith(prev.strftime("%Y-%m")) and r["amount_cents"] < 0)
    ledger.set_balance_anchor(db, amex, month_charges + prev_unpaid, today.isoformat())
    _ = open_amex
    # Beispiel-Budgets
    for key, cents in (("lebensmittel", 50000), ("freizeit", 25000), ("mobilitaet", 18000), ("shopping", 15000)):
        db.execute("UPDATE categories SET budget_cents = ? WHERE builtin_key = ? AND budget_cents IS NULL", (cents, key))
    db.set_setting("demo_budgets", True)
    return {"accounts": 3, "transactions": sum(len(r) for r in rows.values())}


def remove_demo(db: Database) -> None:
    for a in db.query("SELECT id FROM accounts WHERE demo = 1"):
        ledger.delete_account(db, a["id"])
    if db.get_setting("demo_budgets"):
        db.execute("UPDATE categories SET budget_cents = NULL WHERE builtin_key IN ('lebensmittel','freizeit','mobilitaet','shopping')")
        db.set_setting("demo_budgets", False)
    db.execute("DELETE FROM contracts WHERE account_id NOT IN (SELECT id FROM accounts)")
