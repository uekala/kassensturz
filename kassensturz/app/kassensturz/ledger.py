"""Buchungen speichern, Duplikate vermeiden, Kontostände berechnen."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from . import categorize
from .db import Database, now_iso
from .util import tx_hash

TX_COLUMNS = ("booking_date", "value_date", "amount_cents", "currency", "counterparty", "counterparty_iban", "purpose",
              "booking_text", "creditor_id", "mandate_ref", "end_to_end")


def import_rows(db: Database, account_id: int, rows: list[dict], source: str, filename: str | None = None,
                meta: dict | None = None) -> dict:
    """Speichert neue Buchungen. Überlappende Zeiträume werden erkannt: pro (Tag, Betrag) wird nur der
    Überschuss gegenüber dem Bestand eingefügt – so stören auch Mischungen aus FinTS und CSV nicht."""
    rows = [r for r in rows if r.get("booking_date") and r.get("amount_cents")]
    added_ids: list[int] = []
    skipped = 0
    if rows:
        first = min(r["booking_date"] for r in rows)
        last = max(r["booking_date"] for r in rows)
        existing = db.query(
            "SELECT booking_date, amount_cents, hash FROM transactions WHERE account_id = ? AND booking_date BETWEEN ? AND ?",
            (account_id, first, last),
        )
        have_counts: dict[tuple, Counter] = defaultdict(Counter)
        for e in existing:
            have_counts[(e["booking_date"], e["amount_cents"])][e["hash"]] += 1
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in rows:
            r["hash"] = tx_hash(account_id, r["booking_date"], r["amount_cents"], r.get("counterparty"), r.get("purpose"))
            groups[(r["booking_date"], r["amount_cents"])].append(r)
        with db.tx():
            import_id = db.insert("imports", {"account_id": account_id, "source": source, "filename": filename, "created": now_iso(),
                                               "added": 0, "skipped": 0})
            created = now_iso()
            for key, group in groups.items():
                # Match exact hashes first, consuming each existing occurrence only once.
                # Remaining same-day/same-amount rows retain the legacy fuzzy fallback
                # (e.g. changed merchant text between FinTS and CSV imports).
                available = have_counts.get(key, Counter()).copy()
                unmatched = []
                exact_matches = 0
                for r in group:
                    if available[r["hash"]] > 0:
                        available[r["hash"]] -= 1
                        exact_matches += 1
                    else:
                        unmatched.append(r)
                fuzzy_matches = min(len(unmatched), sum(available.values()))
                to_insert = unmatched[fuzzy_matches:]
                for r in to_insert:
                    data = {c: r.get(c) for c in TX_COLUMNS}
                    data.update({"account_id": account_id, "source": source, "import_id": import_id, "hash": r["hash"], "created": created})
                    added_ids.append(db.insert("transactions", data))
                skipped += exact_matches + fuzzy_matches
            db.update("imports", "id", import_id, {"added": len(added_ids), "skipped": skipped})
        categorize.recategorize(db, added_ids)
    if meta and meta.get("balance_cents") is not None and meta.get("balance_date"):
        set_balance_anchor(db, account_id, meta["balance_cents"], meta["balance_date"], only_if_newer=True)
    return {"added": len(added_ids), "skipped": skipped, "ids": added_ids}


def set_balance_anchor(db: Database, account_id: int, cents: int, on: str, only_if_newer: bool = False) -> None:
    acc = db.one("SELECT balance_date FROM accounts WHERE id = ?", (account_id,))
    if not acc:
        return
    if only_if_newer and acc["balance_date"] and acc["balance_date"] > on:
        return
    db.update("accounts", "id", account_id, {"balance_cents": int(cents), "balance_date": on})


# Konten, bei denen man einen Wert einträgt, statt Buchungen abzurufen.
VALUE_KINDS = ("depot", "festgeld", "vl", "immobilie", "kredit")
# Rücklagen und Anlagen: nicht für den Alltag, also nicht in „frei verfügbar“ und Prognose.
SAVINGS_KINDS = ("tagesgeld", "sparkonto", *VALUE_KINDS)
MATURING_KINDS = ("festgeld", "kredit")
WORTH_GROUPS = ("alltag", "ruecklagen", "depots", "immobilien", "kredite")


def worth_group(account: dict) -> str:
    """In welchem Teil des Vermögens ein Konto zählt."""
    kind = account.get("kind")
    if kind == "kredit":
        return "kredite"
    if kind == "immobilie":
        return "immobilien"
    if kind == "depot":
        return "depots"
    return "alltag" if account.get("in_forecast") else "ruecklagen"


def signed_value(kind: str | None, cents: int) -> int:
    """Kredite sind Schulden: Die Restschuld zählt immer negativ."""
    return -abs(int(cents)) if kind == "kredit" else int(cents)


def net_worth_history(db: Database, months: int = 12, today: date | None = None) -> list[dict]:
    """Vermögen zum Ende der letzten Monate und heute.

    Konten mit Buchungen: heutiger Stand minus spätere Buchungen. Konten mit eingetragenem
    Wert: der letzte Wert bis zu diesem Tag."""
    today = today or date.today()
    days = []
    year, month = today.year, today.month
    for _ in range(months):
        days.append(date(year, month, 1) - timedelta(days=1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    days = sorted(days) + [today]
    accounts = [a for a in accounts_with_balance(db) if a["balance_known"]]
    # Der Verlauf beginnt erst, wenn für alle Konten Daten vorliegen. Sonst sähe ein neu
    # angelegtes Depot oder ein neu erfasster Kredit wie ein Sprung im Vermögen aus.
    starts = []
    for a in accounts:
        if a["kind"] in VALUE_KINDS:
            starts.append(db.scalar("SELECT MIN(on_date) FROM valuations WHERE account_id = ?", (a["id"],)) or a["balance_date"])
        else:
            starts.append(min(a["first_date"] or a["balance_date"], a["balance_date"]))
    if not starts:
        return []
    start = max(starts)
    out = []
    for day in days:
        iso = day.isoformat()
        if iso < start:
            continue
        total = 0
        for a in accounts:
            if a["kind"] in VALUE_KINDS:
                total += db.scalar("SELECT value_cents FROM valuations WHERE account_id = ? AND on_date <= ? "
                                   "ORDER BY on_date DESC LIMIT 1", (a["id"], iso)) or 0
            else:
                later = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM transactions WHERE account_id = ? "
                                  "AND booking_date > ?", (a["id"], iso))
                total += a["balance_now"] - later
        out.append({"date": iso, "cents": total})
    return out


DRIFT_DAYS = 3
DRIFT_KEEP = 60


def check_balance(db: Database, account_id: int, bank_cents: int, today: date | None = None) -> int:
    """Selbsttest nach einem Bankabruf; gibt die Abweichung dieses Abrufs in Cent zurück.

    Der Bankstand darf sich seit dem letzten Abruf nur um die Summe der neu dazugekommenen
    Buchungen ändern. Was übrig bleibt, ist eine fehlende oder doppelte Buchung – oder ein
    vorgemerkter Umsatz, der sich beim nächsten Abruf wieder ausgleicht. Der erste Abruf
    eines Kontos legt nur den Ausgangspunkt fest."""
    last_tx = int(db.scalar("SELECT COALESCE(MAX(id), 0) FROM transactions WHERE account_id = ?", (account_id,)) or 0)
    prev = db.one("SELECT bank_cents, last_tx_id FROM balance_checks WHERE account_id = ? ORDER BY id DESC LIMIT 1",
                  (account_id,))
    diff = 0
    if prev:
        booked = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM transactions WHERE account_id = ? AND id > ?",
                           (account_id, prev["last_tx_id"]))
        diff = (int(bank_cents) - prev["bank_cents"]) - int(booked)
    db.insert("balance_checks", {"account_id": account_id, "checked_on": (today or date.today()).isoformat(),
                                 "bank_cents": int(bank_cents), "last_tx_id": last_tx, "diff_cents": diff})
    db.execute("DELETE FROM balance_checks WHERE account_id = ? AND id NOT IN "
               "(SELECT id FROM balance_checks WHERE account_id = ? ORDER BY id DESC LIMIT ?)",
               (account_id, account_id, DRIFT_KEEP))
    return diff


def balance_drift(db: Database, account_id: int, today: date | None = None) -> dict | None:
    """Anhaltende Abweichung eines Kontos, oder None.

    Vorgemerkte Umsätze erzeugen erst ein Minus und beim Buchen ein gleich großes Plus. Gemeldet
    wird deshalb nur, was in der Summe übrig bleibt und sich seit mindestens drei Tagen nicht
    mehr verändert hat."""
    rows = db.query("SELECT checked_on, diff_cents FROM balance_checks WHERE account_id = ? ORDER BY id", (account_id,))
    total = sum(r["diff_cents"] for r in rows)
    if not total:
        return None
    since, running = None, 0
    for r in rows:
        running += r["diff_cents"]
        if running != total:
            since = None
        elif since is None:
            since = r["checked_on"]
    if since is None or ((today or date.today()) - date.fromisoformat(since)).days < DRIFT_DAYS:
        return None
    return {"cents": total, "since": since}


def reset_balance_checks(db: Database, account_id: int) -> None:
    """Verwirft die bisherigen Abweichungen; der nächste Abruf ist der neue Ausgangspunkt."""
    db.execute("DELETE FROM balance_checks WHERE account_id = ?", (account_id,))


def record_valuation(db: Database, account_id: int, cents: int, on: str) -> None:
    """Hält den Wert eines Depots fest; ein Eintrag je Tag, der letzte gilt."""
    db.execute("INSERT INTO valuations(account_id, on_date, value_cents, created) VALUES(?, ?, ?, ?) "
               "ON CONFLICT(account_id, on_date) DO UPDATE SET value_cents = excluded.value_cents, created = excluded.created",
               (account_id, on, int(cents), now_iso()))


def valuations(db: Database, account_id: int) -> list[dict]:
    return db.query("SELECT on_date, value_cents FROM valuations WHERE account_id = ? ORDER BY on_date", (account_id,))


def current_balance(db: Database, account: dict) -> int:
    if account.get("balance_date") is not None and account.get("balance_cents") is not None:
        after = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM transactions WHERE account_id = ? AND booking_date > ?",
                          (account["id"], account["balance_date"]))
        return account["balance_cents"] + after
    return db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM transactions WHERE account_id = ?", (account["id"],))


def accounts_with_balance(db: Database, include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM accounts" + ("" if include_archived else " WHERE archived = 0") + " ORDER BY sort, id"
    out = []
    for a in db.query(sql):
        a["balance_now"] = current_balance(db, a)
        a["balance_known"] = a["balance_date"] is not None
        stats = db.one("SELECT COUNT(*) AS n, MIN(booking_date) AS first, MAX(booking_date) AS last FROM transactions WHERE account_id = ?",
                       (a["id"],))
        a.update({"tx_count": stats["n"], "first_date": stats["first"], "last_date": stats["last"]})
        a.pop("fints_ref", None)
        a["group"] = worth_group(a)
        drift = balance_drift(db, a["id"])
        a["drift_cents"], a["drift_since"] = (drift["cents"], drift["since"]) if drift else (None, None)
        a["value_prev_cents"] = a["value_prev_date"] = None
        if a["kind"] in VALUE_KINDS and a["balance_date"]:
            prev = db.one("SELECT on_date, value_cents FROM valuations WHERE account_id = ? AND on_date < ? "
                          "ORDER BY on_date DESC LIMIT 1", (a["id"], a["balance_date"]))
            if prev:
                a["value_prev_cents"], a["value_prev_date"] = prev["value_cents"], prev["on_date"]
        out.append(a)
    return out


def balance_series(db: Database, account_ids: list[int], start: date, end: date) -> list[tuple[str, int]]:
    """Tagesend-Salden (Summe der Konten) zwischen start und end."""
    if not account_ids:
        return [(d.isoformat(), 0) for d in _days(start, end)]
    accounts = db.query(f"SELECT * FROM accounts WHERE id IN ({','.join('?' * len(account_ids))})", tuple(account_ids))
    total_now = 0
    for a in accounts:
        total_now += current_balance(db, a)
    # Rückwärts vom heutigen Stand rechnen
    today = date.today()
    rows = db.query(
        f"SELECT booking_date, SUM(amount_cents) AS s FROM transactions WHERE account_id IN ({','.join('?' * len(account_ids))}) "
        "AND booking_date > ? GROUP BY booking_date",
        (*account_ids, start.isoformat()),
    )
    per_day = {r["booking_date"]: r["s"] for r in rows}
    future_sum = sum(v for k, v in per_day.items() if k > today.isoformat())
    bal = total_now - future_sum  # Stand Ende heute ohne zukünftig datierte Buchungen
    series = {}
    d = today
    while d >= start:
        series[d.isoformat()] = bal
        bal -= per_day.get(d.isoformat(), 0)
        d -= timedelta(days=1)
    return [(d.isoformat(), series[d.isoformat()]) for d in _days(start, min(end, today))]


def _days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def entries(db: Database, start: str | None = None, end: str | None = None, account_ids: list[int] | None = None) -> list[dict]:
    """Buchungen inklusive Aufteilungen als flache Einträge für Auswertungen."""
    sql = ("SELECT t.id, t.account_id, t.booking_date, t.amount_cents, t.category_id, t.is_transfer, t.contract_key, t.counterparty, "
           "c.kind AS cat_kind, c.parent_id AS cat_parent FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
           "JOIN accounts a ON a.id = t.account_id WHERE a.archived = 0")
    params: list = []
    if start:
        sql += " AND t.booking_date >= ?"
        params.append(start)
    if end:
        sql += " AND t.booking_date <= ?"
        params.append(end)
    if account_ids:
        sql += f" AND t.account_id IN ({','.join('?' * len(account_ids))})"
        params += account_ids
    txs = db.query(sql, tuple(params))
    if not txs:
        return []
    split_rows = db.query(
        "SELECT s.tx_id, s.amount_cents, s.category_id, c.kind AS cat_kind, c.parent_id AS cat_parent FROM splits s "
        "LEFT JOIN categories c ON c.id = s.category_id"
    )
    by_tx = defaultdict(list)
    for s in split_rows:
        by_tx[s["tx_id"]].append(s)
    out = []
    for t in txs:
        parts = by_tx.get(t["id"])
        if not parts:
            t["is_transfer"] = 1 if (t["is_transfer"] or t["cat_kind"] == "transfer") else 0
            out.append(t)
            continue
        rest = t["amount_cents"] - sum(p["amount_cents"] for p in parts)
        for p in parts:
            e = dict(t)
            e.update({"amount_cents": p["amount_cents"], "category_id": p["category_id"], "cat_kind": p["cat_kind"],
                      "cat_parent": p["cat_parent"], "is_transfer": 1 if p["cat_kind"] == "transfer" else 0})
            out.append(e)
        if rest:
            e = dict(t)
            e["amount_cents"] = rest
            e["is_transfer"] = 1 if (t["is_transfer"] or t["cat_kind"] == "transfer") else 0
            out.append(e)
    return out


def delete_account(db: Database, account_id: int) -> None:
    with db.tx():
        db.execute("DELETE FROM splits WHERE tx_id IN (SELECT id FROM transactions WHERE account_id = ?)", (account_id,))
        db.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,))
        db.execute("DELETE FROM imports WHERE account_id = ?", (account_id,))
        db.execute("DELETE FROM valuations WHERE account_id = ?", (account_id,))
        db.execute("DELETE FROM balance_checks WHERE account_id = ?", (account_id,))
        db.execute("UPDATE goals SET account_id = NULL WHERE account_id = ?", (account_id,))
        db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
