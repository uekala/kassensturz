"""Erwartete Eingänge: Geld, das zurückkommen soll, bleibt offen, bis es da ist.

Eine Retoure, eine Erstattung, Auslagen für jemand anderen: Du merkst an der Ausgabe an, dass Geld
zurückkommt, oder legst einen erwarteten Eingang für sich an. Kassensturz hält ihn offen, erinnert,
wenn er auf sich warten lässt, und hakt ihn ab, sobald der passende Eingang gebucht ist.

Von selbst abgehakt wird nur, was eindeutig ist: derselbe Empfänger wie bei der Ausgabe, derselbe
Betrag, dasselbe Konto, gebucht nach der Ausgabe. Alles andere schlägt Kassensturz nur vor.
"""
from __future__ import annotations

from datetime import date, timedelta

from .db import Database, now_iso
from .util import counterparty_key, euro

# So lange darf ein Eingang auf sich warten lassen, bevor Kassensturz erinnert.
DUE_DAYS = 21
MAX_CENTS = 10_000_000
MAX_LABEL = 80
MAX_NOTE = 200
CLOSED_SHOWN = 10


def _who(tx: dict) -> str | None:
    """Der Name der Gegenseite als Schlüssel. Eine Erstattung kommt als Gutschrift unter dem Namen
    des Händlers, auch wenn er das Geld per Lastschrift mit Gläubiger-ID eingezogen hat."""
    return counterparty_key(tx.get("counterparty")) or None


def _same(payee: str | None, other: str | None) -> bool:
    """Derselbe Name, oder einer beginnt mit dem anderen („Versand GmbH“ und „Versand GmbH Retoure“)."""
    if not payee or not other:
        return False
    short, long = sorted((payee, other), key=len)
    return short == long or (len(short) >= 6 and long.startswith(short + " "))


class ExpectedError(ValueError):
    """Die Angaben passen nicht; ``status`` ist der HTTP-Status dazu."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _date(value, default: date | None) -> str | None:
    if value in (None, ""):
        return default.isoformat() if default else None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ExpectedError(400, "Das Datum ist ungültig.") from None


def _cents(value, limit: int = MAX_CENTS) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= limit:
        raise ExpectedError(400, "Der Betrag ist ungültig.")
    return value


def _text(value, limit: int) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ExpectedError(400, "Der Text ist ungültig.")
    return " ".join((value or "").split())[:limit] or None


def create(db: Database, payload: dict, today: date | None = None) -> dict:
    """Legt einen erwarteten Eingang an: zu einer Ausgabe (``tx_id``) oder für sich allein."""
    today = today or date.today()
    note = _text(payload.get("note"), MAX_NOTE)
    due = _date(payload.get("due_date"), today + timedelta(days=DUE_DAYS))
    tx_id = payload.get("tx_id")
    with db.tx(immediate=True):
        if tx_id is not None:
            tx = db.one("SELECT t.*, a.archived FROM transactions t JOIN accounts a ON a.id = t.account_id WHERE t.id = ?",
                        (tx_id,)) if isinstance(tx_id, int) and not isinstance(tx_id, bool) else None
            if not tx:
                raise ExpectedError(404, "Buchung nicht gefunden.")
            if tx["amount_cents"] >= 0 or tx["is_transfer"]:
                raise ExpectedError(409, "Geld kommt nur zu einer Ausgabe zurück.")
            if db.one("SELECT 1 FROM expected_incomes WHERE tx_id = ? AND status = 'open'", (tx_id,)):
                raise ExpectedError(409, "Zu dieser Ausgabe ist schon ein Eingang offen.")
            cents = _cents(payload.get("cents", -tx["amount_cents"]), -tx["amount_cents"])
            label = _text(payload.get("label"), MAX_LABEL) or _text(tx["counterparty"] or tx["purpose"], MAX_LABEL) or "Erstattung"
            data = {"tx_id": tx_id, "account_id": tx["account_id"], "payee": _who(tx), "since": tx["booking_date"]}
        else:
            label = _text(payload.get("label"), MAX_LABEL)
            if not label:
                raise ExpectedError(400, "Wofür kommt das Geld? Bitte eine Bezeichnung eintragen.")
            account = payload.get("account_id")
            if not isinstance(account, int) or isinstance(account, bool) or not db.one(
                    "SELECT 1 FROM accounts WHERE id = ? AND archived = 0", (account,)):
                raise ExpectedError(400, "Bitte das Konto wählen, auf dem das Geld ankommen soll.")
            cents = _cents(payload.get("cents"))
            data = {"tx_id": None, "account_id": account, "payee": None, "since": today.isoformat()}
        item_id = db.insert("expected_incomes", {**data, "label": label, "cents": cents, "due_date": due, "note": note,
                                                 "status": "open", "created": now_iso()})
    return _one(db, item_id, today)


def _open_incomes(db: Database, item: dict) -> list[dict]:
    """Eingänge auf dem Konto seit der Ausgabe, die noch zu keinem erwarteten Eingang gehören.

    Umbuchungen zählen nicht: Wer PayPal vom Girokonto auflädt, bekommt dort genau den Kaufbetrag
    gutgeschrieben, und das ist keine Erstattung."""
    return db.query(
        "SELECT t.id, t.booking_date, t.amount_cents, t.counterparty "
        "FROM transactions t WHERE t.account_id = ? AND t.amount_cents > 0 AND t.is_transfer = 0 AND t.booking_date >= ? "
        "AND t.id NOT IN (SELECT received_tx_id FROM expected_incomes WHERE received_tx_id IS NOT NULL) "
        "ORDER BY t.booking_date, t.id", (item["account_id"], item["since"]))


def settle(db: Database) -> int:
    """Hakt ab, was eindeutig angekommen ist. Gibt zurück, wie viele es waren."""
    done = 0
    for item in db.query("SELECT * FROM expected_incomes WHERE status = 'open' AND payee IS NOT NULL ORDER BY since, id"):
        for income in _open_incomes(db, item):
            if income["amount_cents"] == item["cents"] and _same(item["payee"], _who(income)):
                db.update("expected_incomes", "id", item["id"], {"status": "received", "received_tx_id": income["id"],
                                                                "closed_on": income["booking_date"]})
                done += 1
                break
    return done


def _candidates(db: Database, item: dict) -> list[dict]:
    """Eingänge, die es sein könnten: gleicher Betrag oder gleicher Empfänger. Höchstens drei."""
    out = []
    for income in _open_incomes(db, item):
        same_payee = _same(item["payee"], _who(income))
        if income["amount_cents"] == item["cents"] or same_payee:
            out.append({"tx_id": income["id"], "booking_date": income["booking_date"], "amount_cents": income["amount_cents"],
                        "counterparty": income["counterparty"]})
    return out[-3:][::-1]


def _shape(db: Database, item: dict, today: date) -> dict:
    account = db.one("SELECT name, owner_person_id FROM accounts WHERE id = ?", (item["account_id"],)) or {}
    is_open = item["status"] == "open"
    out = {
        "id": item["id"], "label": item["label"], "cents": item["cents"], "status": item["status"], "tx_id": item["tx_id"],
        "account_id": item["account_id"], "account": account.get("name"), "owner_person_id": account.get("owner_person_id"),
        "since": item["since"], "due_date": item["due_date"], "note": item["note"], "closed_on": item["closed_on"],
        "received_tx_id": item["received_tx_id"],
        "waiting_days": (today - date.fromisoformat(item["since"])).days if is_open else None,
        "overdue": bool(is_open and item["due_date"] and item["due_date"] < today.isoformat()),
    }
    if is_open:
        out["candidates"] = _candidates(db, item)
    return out


def _one(db: Database, item_id: int, today: date | None = None) -> dict:
    item = db.one("SELECT * FROM expected_incomes WHERE id = ?", (item_id,))
    if not item:
        raise ExpectedError(404, "Diesen erwarteten Eingang gibt es nicht.")
    return _shape(db, item, today or date.today())


def overview(db: Database, today: date | None = None) -> dict:
    """Offene Eingänge, die zuletzt erledigten und die Summe, die noch aussteht."""
    today = today or date.today()
    opened = [_shape(db, i, today) for i in db.query(
        "SELECT * FROM expected_incomes WHERE status = 'open' ORDER BY since, id")]
    closed = [_shape(db, i, today) for i in db.query(
        "SELECT * FROM expected_incomes WHERE status != 'open' ORDER BY closed_on DESC, id DESC LIMIT ?", (CLOSED_SHOWN,))]
    return {"open": opened, "closed": closed, "open_cents": sum(i["cents"] for i in opened),
            "overdue": sum(1 for i in opened if i["overdue"])}


def close(db: Database, item_id: int, payload: dict | None = None, today: date | None = None) -> dict:
    """Von Hand abhaken: mit dem Eingang, der es war, oder ohne."""
    today = today or date.today()
    payload = payload or {}
    with db.tx(immediate=True):
        item = db.one("SELECT * FROM expected_incomes WHERE id = ?", (item_id,))
        if not item:
            raise ExpectedError(404, "Diesen erwarteten Eingang gibt es nicht.")
        if item["status"] != "open":
            raise ExpectedError(409, "Dieser Eingang ist schon erledigt.")
        tx_id, closed_on = payload.get("tx_id"), today.isoformat()
        if tx_id is not None:
            income = next((i for i in _open_incomes(db, item) if i["id"] == tx_id), None)
            if income is None:
                raise ExpectedError(400, "Diese Buchung passt nicht dazu oder gehört schon zu einem anderen Eingang.")
            closed_on = income["booking_date"]
        db.update("expected_incomes", "id", item_id, {"status": "received", "received_tx_id": tx_id, "closed_on": closed_on})
    return _one(db, item_id, today)


def drop(db: Database, item_id: int, today: date | None = None) -> dict:
    """Das Geld kommt nicht mehr."""
    today = today or date.today()
    if db.execute_count("UPDATE expected_incomes SET status = 'dropped', closed_on = ? WHERE id = ? AND status = 'open'",
                        (today.isoformat(), item_id)) != 1:
        raise ExpectedError(409, "Dieser Eingang ist nicht offen.")
    return _one(db, item_id, today)


def reopen(db: Database, item_id: int, today: date | None = None) -> dict:
    """Macht einen erledigten Eingang wieder offen, etwa nach einem falschen Abhaken."""
    with db.tx(immediate=True):
        item = db.one("SELECT * FROM expected_incomes WHERE id = ?", (item_id,))
        if not item or item["status"] == "open":
            raise ExpectedError(409, "Dieser Eingang ist nicht erledigt.")
        if item["tx_id"] and db.one("SELECT 1 FROM expected_incomes WHERE tx_id = ? AND status = 'open'", (item["tx_id"],)):
            raise ExpectedError(409, "Zu dieser Ausgabe ist schon ein Eingang offen.")
        db.update("expected_incomes", "id", item_id, {"status": "open", "received_tx_id": None, "closed_on": None})
    return _one(db, item_id, today)


def prune(db: Database) -> None:
    """Entfernt, was an gelöschten Buchungen oder Konten hing."""
    db.execute("DELETE FROM expected_incomes WHERE account_id NOT IN (SELECT id FROM accounts) "
               "OR (tx_id IS NOT NULL AND tx_id NOT IN (SELECT id FROM transactions))")
    db.execute("UPDATE expected_incomes SET received_tx_id = NULL WHERE received_tx_id IS NOT NULL "
               "AND received_tx_id NOT IN (SELECT id FROM transactions)")


def alerts(db: Database, today: date | None = None) -> list[dict]:
    """Erinnert an Eingänge, die länger ausstehen als gedacht."""
    today = today or date.today()
    out = []
    for item in overview(db, today)["open"]:
        if not item["overdue"]:
            continue
        since = date.fromisoformat(item["since"]).strftime("%d.%m.")
        out.append({"key": f"expected-due:{item['id']}:{item['due_date']}", "level": "warning", "expected": item["id"],
                    "owner_person_id": item["owner_person_id"], "title": f"Geld steht noch aus: {item['label']}",
                    "text": f"{euro(item['cents'])} erwartet seit {since}, Konto {item['account']}. Bisher ist nichts "
                            "angekommen."})
    return out


def arrivals(db: Database, today: date | None = None) -> list[dict]:
    """Was in den letzten Tagen von selbst abgehakt wurde, für die Mitteilung „ist da“."""
    today = today or date.today()
    rows = db.query("SELECT e.*, a.name AS account, a.owner_person_id FROM expected_incomes e JOIN accounts a ON a.id = e.account_id "
                    "WHERE e.status = 'received' AND e.received_tx_id IS NOT NULL AND e.closed_on >= ?",
                    ((today - timedelta(days=7)).isoformat(),))
    return [{"key": f"expected-in:{r['id']}", "owner_person_id": r["owner_person_id"], "title": f"Geld ist da: {r['label']}",
             "text": f"{euro(r['cents'])} am {date.fromisoformat(r['closed_on']).strftime('%d.%m.')} auf {r['account']}."}
            for r in rows]
