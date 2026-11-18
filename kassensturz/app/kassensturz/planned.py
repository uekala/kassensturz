"""Geplante Ausgaben: einmalige Zahlungen, die schon feststehen, zählen in der Prognose mit.

Die Handwerkerrechnung im März, die Anzahlung für den Urlaub, die neue Waschmaschine: kein Vertrag,
aber absehbar. Du trägst Betrag, Tag und Konto ein. Bis die Ausgabe gebucht ist, zieht Kassensturz
sie von „frei verfügbar“ ab und rechnet sie in den Verlauf der Prognose ein.

Von selbst abgehakt wird nur, was eindeutig ist: genau eine Abbuchung mit genau diesem Betrag auf
diesem Konto, rund um den geplanten Tag. Alles andere schlägt Kassensturz nur vor.
"""
from __future__ import annotations

from datetime import date, timedelta

from .db import Database, now_iso
from .util import euro

MAX_CENTS = 100_000_000
MAX_LABEL = 80
MAX_NOTE = 200
# So weit im Voraus lässt sich planen.
MAX_AHEAD_DAYS = 3 * 366
# Eine Abbuchung gilt als die geplante, wenn sie höchstens so viele Tage vor dem geplanten Tag liegt.
MATCH_BEFORE_DAYS = 10
CLOSED_SHOWN = 10


class PlannedError(ValueError):
    """Die Angaben passen nicht; ``status`` ist der HTTP-Status dazu."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _date(value, today: date) -> str:
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        raise PlannedError(400, "Bitte den Tag eintragen, an dem die Ausgabe ansteht.") from None
    if day < today:
        raise PlannedError(400, "Der Tag liegt in der Vergangenheit.")
    if (day - today).days > MAX_AHEAD_DAYS:
        raise PlannedError(400, "So weit im Voraus lässt sich nicht planen.")
    return day.isoformat()


def _cents(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_CENTS:
        raise PlannedError(400, "Der Betrag ist ungültig.")
    return value


def _text(value, limit: int) -> str | None:
    if value is not None and not isinstance(value, str):
        raise PlannedError(400, "Der Text ist ungültig.")
    return " ".join((value or "").split())[:limit] or None


def _account(db: Database, value) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not db.one(
            "SELECT 1 FROM accounts WHERE id = ? AND archived = 0", (value,)):
        raise PlannedError(400, "Bitte das Konto wählen, von dem die Ausgabe abgeht.")
    return value


def _label(value) -> str:
    label = _text(value, MAX_LABEL)
    if not label:
        raise PlannedError(400, "Wofür ist die Ausgabe? Bitte eine Bezeichnung eintragen.")
    return label


def create(db: Database, payload: dict, today: date | None = None) -> dict:
    today = today or date.today()
    with db.tx(immediate=True):
        item_id = db.insert("planned_expenses", {
            "label": _label(payload.get("label")), "cents": _cents(payload.get("cents")),
            "due_date": _date(payload.get("due_date"), today), "account_id": _account(db, payload.get("account_id")),
            "note": _text(payload.get("note"), MAX_NOTE), "status": "open", "since": today.isoformat(), "created": now_iso()})
    return _one(db, item_id, today)


def change(db: Database, item_id: int, payload: dict, today: date | None = None) -> dict:
    """Ändert, was sich an einem offenen Plan verschoben hat: Betrag, Tag, Konto, Bezeichnung, Notiz."""
    today = today or date.today()
    with db.tx(immediate=True):
        item = db.one("SELECT * FROM planned_expenses WHERE id = ?", (item_id,))
        if not item:
            raise PlannedError(404, "Diese geplante Ausgabe gibt es nicht.")
        if item["status"] != "open":
            raise PlannedError(409, "Diese Ausgabe ist schon erledigt.")
        data = {}
        if "label" in payload:
            data["label"] = _label(payload["label"])
        if "cents" in payload:
            data["cents"] = _cents(payload["cents"])
        # Ein überfälliger Tag darf stehen bleiben, wenn nur der Betrag sich ändert.
        if "due_date" in payload and payload["due_date"] != item["due_date"]:
            data["due_date"] = _date(payload["due_date"], today)
        if "account_id" in payload:
            data["account_id"] = _account(db, payload["account_id"])
        if "note" in payload:
            data["note"] = _text(payload["note"], MAX_NOTE)
        if data:
            db.update("planned_expenses", "id", item_id, data)
    return _one(db, item_id, today)


def _open_expenses(db: Database, item: dict) -> list[dict]:
    """Abbuchungen auf dem Konto, die die geplante Ausgabe sein könnten: seit dem Eintragen, frühestens
    zehn Tage vor dem geplanten Tag, kein Vertrag, keine Umbuchung, noch keinem anderen Plan zugeordnet."""
    start = max(item["since"], (date.fromisoformat(item["due_date"]) - timedelta(days=MATCH_BEFORE_DAYS)).isoformat())
    return db.query(
        "SELECT t.id, t.booking_date, t.amount_cents, t.counterparty, t.purpose FROM transactions t "
        "WHERE t.account_id = ? AND t.amount_cents < 0 AND t.is_transfer = 0 AND t.contract_key IS NULL AND t.booking_date >= ? "
        "AND t.id NOT IN (SELECT paid_tx_id FROM planned_expenses WHERE paid_tx_id IS NOT NULL) "
        "ORDER BY t.booking_date, t.id", (item["account_id"], start))


def settle(db: Database) -> int:
    """Hakt ab, was eindeutig bezahlt ist. Gibt zurück, wie viele es waren."""
    done = 0
    for item in db.query("SELECT * FROM planned_expenses WHERE status = 'open' ORDER BY due_date, id"):
        exact = [t for t in _open_expenses(db, item) if -t["amount_cents"] == item["cents"]]
        if len(exact) == 1:
            db.update("planned_expenses", "id", item["id"], {"status": "paid", "paid_tx_id": exact[0]["id"],
                                                            "closed_on": exact[0]["booking_date"]})
            done += 1
    return done


def _candidates(db: Database, item: dict) -> list[dict]:
    """Abbuchungen in der Größenordnung des Plans (halb bis anderthalbfach). Höchstens drei, die nächste zuerst."""
    cents = item["cents"]
    near = [t for t in _open_expenses(db, item) if cents <= -t["amount_cents"] * 2 and -t["amount_cents"] * 2 <= cents * 3]
    near.sort(key=lambda t: (abs(-t["amount_cents"] - cents), t["booking_date"]))
    return [{"tx_id": t["id"], "booking_date": t["booking_date"], "amount_cents": t["amount_cents"],
             "counterparty": t["counterparty"] or t["purpose"]} for t in near[:3]]


def _shape(db: Database, item: dict, today: date) -> dict:
    account = db.one("SELECT name, owner_person_id, in_forecast FROM accounts WHERE id = ?", (item["account_id"],)) or {}
    is_open = item["status"] == "open"
    out = {
        "id": item["id"], "label": item["label"], "cents": item["cents"], "status": item["status"],
        "account_id": item["account_id"], "account": account.get("name"), "owner_person_id": account.get("owner_person_id"),
        "in_forecast": bool(account.get("in_forecast")), "due_date": item["due_date"], "note": item["note"],
        "closed_on": item["closed_on"], "paid_tx_id": item["paid_tx_id"],
        "days_left": (date.fromisoformat(item["due_date"]) - today).days if is_open else None,
        "overdue": bool(is_open and item["due_date"] < today.isoformat()),
    }
    if is_open:
        out["candidates"] = _candidates(db, item)
    return out


def _one(db: Database, item_id: int, today: date | None = None) -> dict:
    item = db.one("SELECT * FROM planned_expenses WHERE id = ?", (item_id,))
    if not item:
        raise PlannedError(404, "Diese geplante Ausgabe gibt es nicht.")
    return _shape(db, item, today or date.today())


def overview(db: Database, today: date | None = None) -> dict:
    """Offene Pläne nach Tag, die zuletzt erledigten und die Summe, die noch ansteht."""
    today = today or date.today()
    opened = [_shape(db, i, today) for i in db.query(
        "SELECT * FROM planned_expenses WHERE status = 'open' ORDER BY due_date, id")]
    closed = [_shape(db, i, today) for i in db.query(
        "SELECT * FROM planned_expenses WHERE status != 'open' ORDER BY closed_on DESC, id DESC LIMIT ?", (CLOSED_SHOWN,))]
    return {"open": opened, "closed": closed, "open_cents": sum(i["cents"] for i in opened),
            "overdue": sum(1 for i in opened if i["overdue"])}


def upcoming(db: Database, account_ids: list[int], start: date, end: date) -> list[dict]:
    """Offene Pläne auf diesen Konten als Zahlungen für die Prognose, in der Form der Vertragszahlungen.

    Was überfällig und noch offen ist, steht weiter aus und zählt am ersten Tag des Zeitraums."""
    if not account_ids:
        return []
    marks = ",".join("?" * len(account_ids))
    rows = db.query(f"SELECT * FROM planned_expenses WHERE status = 'open' AND due_date <= ? AND account_id IN ({marks}) "
                    "ORDER BY due_date, id", (end.isoformat(), *account_ids))
    out = []
    for r in rows:
        late = r["due_date"] < start.isoformat()
        out.append({"key": f"planned:{r['id']}", "planned": r["id"], "name": r["label"], "amount_cents": -r["cents"],
                    "kind": "planned", "account_id": r["account_id"], "interval": None,
                    "date": start.isoformat() if late else r["due_date"],
                    "overdue": r["due_date"] < (start - timedelta(days=1)).isoformat()})
    return out


def paid_tx_ids(db: Database) -> set[int]:
    """Buchungen, die eine geplante Ausgabe waren. Sie zählen nicht zu den üblichen Alltagsausgaben."""
    return {r["paid_tx_id"] for r in db.query("SELECT paid_tx_id FROM planned_expenses WHERE paid_tx_id IS NOT NULL")}


def close(db: Database, item_id: int, payload: dict | None = None, today: date | None = None) -> dict:
    """Von Hand abhaken: mit der Abbuchung, die es war, oder ohne."""
    today = today or date.today()
    payload = payload or {}
    with db.tx(immediate=True):
        item = db.one("SELECT * FROM planned_expenses WHERE id = ?", (item_id,))
        if not item:
            raise PlannedError(404, "Diese geplante Ausgabe gibt es nicht.")
        if item["status"] != "open":
            raise PlannedError(409, "Diese Ausgabe ist schon erledigt.")
        tx_id, closed_on = payload.get("tx_id"), today.isoformat()
        if tx_id is not None:
            paid = next((t for t in _open_expenses(db, item) if t["id"] == tx_id), None)
            if paid is None:
                raise PlannedError(400, "Diese Buchung passt nicht dazu oder gehört schon zu einem anderen Plan.")
            closed_on = paid["booking_date"]
        db.update("planned_expenses", "id", item_id, {"status": "paid", "paid_tx_id": tx_id, "closed_on": closed_on})
    return _one(db, item_id, today)


def drop(db: Database, item_id: int, today: date | None = None) -> dict:
    """Die Ausgabe fällt aus."""
    today = today or date.today()
    if db.execute_count("UPDATE planned_expenses SET status = 'dropped', closed_on = ? WHERE id = ? AND status = 'open'",
                        (today.isoformat(), item_id)) != 1:
        raise PlannedError(409, "Diese Ausgabe ist nicht offen.")
    return _one(db, item_id, today)


def reopen(db: Database, item_id: int, today: date | None = None) -> dict:
    """Macht eine erledigte Ausgabe wieder offen, etwa nach einem falschen Abhaken."""
    with db.tx(immediate=True):
        item = db.one("SELECT * FROM planned_expenses WHERE id = ?", (item_id,))
        if not item or item["status"] == "open":
            raise PlannedError(409, "Diese Ausgabe ist nicht erledigt.")
        db.update("planned_expenses", "id", item_id, {"status": "open", "paid_tx_id": None, "closed_on": None})
    return _one(db, item_id, today)


def prune(db: Database) -> None:
    """Entfernt, was an gelöschten Konten hing, und löst die Verbindung zu gelöschten Buchungen."""
    db.execute("DELETE FROM planned_expenses WHERE account_id NOT IN (SELECT id FROM accounts)")
    db.execute("UPDATE planned_expenses SET paid_tx_id = NULL WHERE paid_tx_id IS NOT NULL "
               "AND paid_tx_id NOT IN (SELECT id FROM transactions)")


def alerts(db: Database, today: date | None = None) -> list[dict]:
    """Fragt nach, wenn der geplante Tag vorbei ist und keine passende Abbuchung kam."""
    today = today or date.today()
    out = []
    for item in overview(db, today)["open"]:
        if not item["overdue"]:
            continue
        due = date.fromisoformat(item["due_date"]).strftime("%d.%m.")
        out.append({"key": f"planned-due:{item['id']}:{item['due_date']}", "level": "warning", "planned": item["id"],
                    "owner_person_id": item["owner_person_id"], "title": f"Geplante Ausgabe offen: {item['label']}",
                    "text": f"{euro(item['cents'])} waren für den {due} geplant, Konto {item['account']}. Schon bezahlt, "
                            "verschoben oder entfallen? Solange sie offen ist, zählt sie in der Prognose mit."})
    return out
