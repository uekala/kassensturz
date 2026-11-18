"""Auffälligkeiten: Buchungen, auf die sich ein zweiter Blick lohnt.

Drei Dinge fallen auf, jeweils in den letzten zwei Wochen:

- **Doppelt abgebucht:** derselbe Empfänger, derselbe Betrag, dasselbe Konto, höchstens drei Tage
  auseinander.
- **Erste Lastschrift:** eine Lastschrift von jemandem, der bisher nie abgebucht hat. Eine Lastschrift
  lässt sich acht Wochen lang bei der Bank zurückgeben; der Hinweis nennt den letzten Tag.
- **Ungewöhnlich hoher Betrag:** mindestens dreimal so viel wie je zuvor bei diesem Empfänger.

Jeder Hinweis lässt sich als geprüft ausblenden und verschwindet sonst nach zwei Wochen von selbst.
Gerechnet wird nur aus den eigenen Buchungen; was man selbst angelegt oder nachgetragen hat, zählt
nicht als auffällig.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache

from . import categorize
from .db import Database, now_iso
from .util import counterparty_key, euro, norm

WINDOW_DAYS = 14
DOUBLE_DAYS = 3
DOUBLE_MIN_CENTS = 1000
# So lange muss ein Konto schon Buchungen haben, bevor „zum ersten Mal“ etwas bedeutet.
HISTORY_DAYS = 60
# Eine Lastschrift lässt sich acht Wochen nach der Abbuchung ohne Begründung zurückgeben.
RETURN_DAYS = 56
HIGH_FACTOR = 3
HIGH_MIN_EXTRA_CENTS = 5000
HIGH_MIN_EARLIER = 4
HIGH_LOOKBACK_DAYS = 365
# Selbst angelegt oder aus einer anderen App nachgetragen: kennt man schon.
QUIET_SOURCES = ("manual", "taschengeld", "finanzguru")
KINDS = ("double", "debit", "high")
_KEY = re.compile(r"anomaly:(double|debit|high):\d+")


@lru_cache(maxsize=50_000)
def _creditor(value: str | None) -> str | None:
    creditor = re.sub(r"[^a-z0-9]", "", norm(value))
    return f"cid:{creditor}" if len(creditor) >= 8 else None


@lru_cache(maxsize=50_000)
def _plain_name(name: str | None) -> str | None:
    """Der Name als Schlüssel, wenn er für sich allein reicht. Dieselben Namen kommen tausendfach vor."""
    key = counterparty_key(name)
    return key if len(key) >= 3 and categorize.learn_key({"counterparty": name}) == key else None


def _payee(tx: dict) -> str | None:
    """Woran ein Empfänger wiedererkannt wird: an der Gläubiger-ID, sonst am Namen."""
    # Zahlungsdienste und zu kurze Namen brauchen den Verwendungszweck oder die IBAN.
    return _creditor(tx.get("creditor_id")) or _plain_name(tx.get("counterparty")) or categorize.learn_key(tx)


def _is_debit(tx: dict) -> bool:
    return _creditor(tx.get("creditor_id")) is not None or "lastschrift" in norm(tx.get("booking_text"))


def _day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.")


# Das Ergebnis je Sicht, solange sich an den Buchungen nichts geändert hat. Die Übersicht fragt oft,
# die Suche geht aber durch alle früheren Ausgaben.
_cache: dict[tuple, tuple[tuple, list[dict]]] = {}


def _state(db: Database, today: date) -> tuple:
    """Woran sich erkennen lässt, ob neu gesucht werden muss."""
    tx = db.one("SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS last, COALESCE(SUM(category_locked), 0) AS locked, "
                "COUNT(contract_key) AS contracts, COALESCE(SUM(is_transfer), 0) AS transfers FROM transactions")
    accounts = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(archived), 0) AS archived FROM accounts")
    return (today.isoformat(), *tx.values(), *accounts.values(), db.scalar("SELECT COUNT(*) FROM anomaly_acks"))


def find(db: Database, today: date | None = None) -> list[dict]:
    """Die Auffälligkeiten der letzten zwei Wochen, die noch niemand als geprüft markiert hat."""
    today = today or date.today()
    view = (str(db.path), getattr(db, "person_id", None), getattr(db, "part_kind", None))
    state = _state(db, today)
    cached = _cache.get(view)
    if cached is None or cached[0] != state:
        cached = _cache[view] = (state, _search(db, today))
    return [dict(a) for a in cached[1]]


def _search(db: Database, today: date) -> list[dict]:
    start = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    marks = ",".join("?" for _ in QUIET_SOURCES)
    recent = db.query(
        f"""SELECT t.id, t.account_id, t.booking_date, t.amount_cents, t.counterparty, t.counterparty_iban, t.purpose,
                   t.booking_text, t.creditor_id, t.mandate_ref, t.contract_key, t.category_locked,
                   a.name AS account, a.owner_person_id
            FROM transactions t JOIN accounts a ON a.id = t.account_id
            WHERE a.archived = 0 AND a.kind != 'taschengeld' AND t.amount_cents < 0 AND t.is_transfer = 0
              AND t.booking_date >= ? AND t.booking_date <= ? AND COALESCE(t.source, '') NOT IN ({marks})
            ORDER BY t.booking_date, t.id""",
        ((today - timedelta(days=WINDOW_DAYS + DOUBLE_DAYS)).isoformat(), today.isoformat(), *QUIET_SOURCES),
    )
    if not recent:
        return []
    # Geprüft ist die Buchung, nicht nur der eine Hinweis: Danach kommt zu ihr kein weiterer.
    checked = {int(r["key"].rsplit(":", 1)[1]) for r in db.query("SELECT key FROM anomaly_acks")}
    for tx in recent:
        tx["payee"] = _payee(tx)
    found: dict[int, dict] = {}

    def add(kind: str, tx: dict, title: str, text: str, **extra) -> None:
        key = f"anomaly:{kind}:{tx['id']}"
        if tx["id"] in checked or tx["id"] in found or tx["booking_date"] < start:
            return
        found[tx["id"]] = {
            "key": key, "kind": kind, "tx_id": tx["id"], "account_id": tx["account_id"], "account": tx["account"],
            "owner_person_id": tx["owner_person_id"], "counterparty": tx["counterparty"],
            "amount_cents": tx["amount_cents"], "booking_date": tx["booking_date"], "title": title, "text": text, **extra,
        }

    # Doppelt abgebucht
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for tx in recent:
        if tx["payee"] and -tx["amount_cents"] >= DOUBLE_MIN_CENTS:
            groups[(tx["account_id"], tx["amount_cents"], tx["payee"])].append(tx)
    for group in groups.values():
        for before, tx in zip(group, group[1:]):
            gap = (date.fromisoformat(tx["booking_date"]) - date.fromisoformat(before["booking_date"])).days
            if gap <= DOUBLE_DAYS:
                when = (f"zweimal am {_day(tx['booking_date'])}" if gap == 0
                        else f"am {_day(before['booking_date'])} und am {_day(tx['booking_date'])}")
                add("double", tx, f"Doppelt abgebucht? {_name(tx)}",
                    f"{euro(-tx['amount_cents'])} {when}, Konto {tx['account']}. Stimmt das nicht, melde dich beim "
                    "Händler oder bei deiner Bank.", other_tx_id=before["id"], other_date=before["booking_date"])

    # Erste Lastschrift und ungewöhnlich hoher Betrag brauchen den Blick zurück – nur, wenn es Kandidaten gibt.
    window = [tx for tx in recent if tx["booking_date"] >= start and tx["payee"] and tx["id"] not in found
              and tx["id"] not in checked]
    debits = [tx for tx in window if _is_debit(tx) and not tx["category_locked"]]
    highs = [tx for tx in window if not tx["contract_key"]]
    if debits or highs:
        earlier = _earlier(db, {tx["payee"] for tx in debits + highs}, today)
        account_start = {r["account_id"]: r["first"] for r in db.query(
            "SELECT account_id, MIN(booking_date) AS first FROM transactions GROUP BY account_id")}
        for tx in debits:
            known = bisect_left(earlier[tx["payee"]], (tx["booking_date"], tx["id"]))
            settled = (date.fromisoformat(tx["booking_date"]) - timedelta(days=HISTORY_DAYS)).isoformat()
            if known or account_start.get(tx["account_id"], tx["booking_date"]) > settled:
                continue
            until = date.fromisoformat(tx["booking_date"]) + timedelta(days=RETURN_DAYS)
            add("debit", tx, f"Erste Lastschrift von {_name(tx)}",
                f"{euro(-tx['amount_cents'])} am {_day(tx['booking_date'])}, Konto {tx['account']}. Kennst du sie nicht, "
                f"kannst du sie bis {until.strftime('%d.%m.%Y')} bei deiner Bank zurückgeben.",
                return_until=until.isoformat(), creditor_id=tx["creditor_id"], mandate_ref=tx["mandate_ref"])
        for tx in highs:
            since = (date.fromisoformat(tx["booking_date"]) - timedelta(days=HIGH_LOOKBACK_DAYS)).isoformat()
            entries = earlier[tx["payee"]]
            before = [-e[2] for e in entries[bisect_left(entries, (since,)):bisect_left(entries, (tx["booking_date"], tx["id"]))]]
            if len(before) < HIGH_MIN_EARLIER:
                continue
            usual, amount = max(before), -tx["amount_cents"]
            if amount >= HIGH_FACTOR * usual and amount - usual >= HIGH_MIN_EXTRA_CENTS:
                add("high", tx, f"Ungewöhnlich hoher Betrag: {_name(tx)}",
                    f"{euro(amount)} am {_day(tx['booking_date'])}, Konto {tx['account']}. Bisher waren es höchstens "
                    f"{euro(usual)}.", usual_max_cents=usual)
    return sorted(found.values(), key=lambda a: (a["booking_date"], a["tx_id"]), reverse=True)


def _name(tx: dict) -> str:
    text = " ".join((tx.get("counterparty") or "").split())
    return (text if len(text) <= 40 else text[:39] + "…") or "Unbekannt"


def _earlier(db: Database, payees: set[str], today: date) -> dict[str, list[tuple[str, int, int]]]:
    """Alle Ausgaben an diese Empfänger, nach Tag und ID sortiert: (Buchungstag, ID, Betrag)."""
    out: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    if not payees:
        return out
    rows = db.query(
        "SELECT t.id, t.booking_date, t.amount_cents, t.counterparty, t.counterparty_iban, t.purpose, t.creditor_id "
        "FROM transactions t WHERE t.amount_cents < 0 AND t.booking_date <= ?", (today.isoformat(),))
    for row in rows:
        payee = _payee(row)
        if payee in payees:
            out[payee].append((row["booking_date"], row["id"], row["amount_cents"]))
    for entries in out.values():
        entries.sort()
    return out


def acknowledge(db: Database, key: str) -> bool:
    """Blendet einen Hinweis aus. Gibt False zurück, wenn der Schlüssel keiner ist."""
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        return False
    db.execute("INSERT OR IGNORE INTO anomaly_acks(key, created) VALUES(?, ?)", (key, now_iso()))
    return True


def alerts(db: Database, today: date | None = None) -> list[dict]:
    """Die Auffälligkeiten als Hinweise für Übersicht, App und Benachrichtigung."""
    return [{"key": a["key"], "level": "warning", "title": a["title"], "text": a["text"], "anomaly": a,
             "owner_person_id": a["owner_person_id"]} for a in find(db, today)]
