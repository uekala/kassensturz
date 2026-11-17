"""Gemeinsame Ausgaben vom eigenen Konto teilen und ausgleichen.

Wer etwas für den Haushalt von seinem eigenen Konto bezahlt, teilt die Buchung. Jede
Person trägt einen Teil; die anderen schulden dem Zahler ihren. Gezahlt hat immer, wem
das Konto gehört. Eine Ausgleichszahlung zwischen zwei Personen wird von Hand
eingetragen und mindert die Schuld.

Geteilt wird bewusst: Die anderen sehen von einer geteilten Buchung Datum, Empfänger,
Betrag und ihren Teil – sonst nichts vom Konto. Diese Abfragen laufen deshalb über die
ganze Datenbank und filtern selbst nach Person.

Gerechnet wird je Paar. Es wird nicht über Dritte verrechnet, damit jede Zahl
nachvollziehbar bleibt.
"""
from __future__ import annotations

from datetime import date

from . import ledger
from .db import Database, now_iso

MAX_WEIGHT = 1000
MAX_SETTLEMENT_CENTS = 100_000_000
MAX_NOTE_LENGTH = 120
RECENT_ITEMS = 50


class SharingError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def clean_weight(value) -> int:
    if not _is_int(value) or not 0 <= value <= MAX_WEIGHT:
        raise SharingError(400, f"Der Anteil muss eine ganze Zahl von 0 bis {MAX_WEIGHT} sein.")
    return value


def _persons(db: Database) -> dict[int, dict]:
    return {p["id"]: p for p in db.query(
        "SELECT id, name, COALESCE(share_weight, 1) AS weight FROM persons ORDER BY sort, id")}


def split_by_weight(total: int, weights: dict[int, int], payer: int) -> dict[int, int]:
    """Teilt ``total`` Cent nach Gewicht. Was beim Runden übrig bleibt, trägt der Zahler,
    sonst die Person mit dem größten Gewicht."""
    active = {pid: w for pid, w in weights.items() if w > 0}
    whole = sum(active.values())
    parts = {pid: total * w // whole for pid, w in active.items()}
    rest = total - sum(parts.values())
    target = payer if payer in parts else max(active, key=lambda pid: (active[pid], -pid))
    parts[target] += rest
    return parts


def _transaction(db: Database, tx_id: int) -> dict:
    row = db.one(
        "SELECT t.id, t.amount_cents, t.is_transfer, t.booking_date, t.counterparty, t.purpose, "
        "a.owner_person_id AS payer_id, a.archived FROM transactions AS t "
        "JOIN accounts AS a ON a.id = t.account_id WHERE t.id = ?", (tx_id,)) if _is_int(tx_id) else None
    if row is None or row["archived"]:
        raise SharingError(404, "Buchung nicht gefunden.")
    return row


def shareable(db: Database, tx: dict) -> str | None:
    """Grund, warum sich die Buchung nicht teilen lässt, oder None."""
    if tx["payer_id"] is None:
        return "Teilen geht nur bei Buchungen auf einem eigenen Konto. Was vom gemeinsamen Konto abgeht, ist schon gemeinsam bezahlt."
    if tx["amount_cents"] >= 0:
        return "Teilen lässt sich nur eine Ausgabe."
    if tx["is_transfer"]:
        return "Eine Umbuchung lässt sich nicht teilen."
    if len(_persons(db)) < 2:
        return "Zum Teilen braucht es mindestens zwei Personen im Haushalt."
    return None


def get_share(db: Database, tx_id: int) -> dict:
    tx = _transaction(db, tx_id)
    persons = _persons(db)
    parts = [
        {"person_id": r["person_id"], "name": persons[r["person_id"]]["name"], "cents": r["cents"]}
        for r in db.query("SELECT person_id, cents FROM tx_shares WHERE tx_id = ? ORDER BY person_id", (tx_id,))
        if r["person_id"] in persons
    ]
    reason = shareable(db, tx)
    return {
        "shareable": reason is None, "reason": reason, "shared": bool(parts) and reason is None,
        "payer_id": tx["payer_id"], "payer": persons.get(tx["payer_id"], {}).get("name"),
        "total_cents": -tx["amount_cents"] if tx["amount_cents"] < 0 else 0, "parts": parts,
    }


def set_share(db: Database, tx_id: int, parts=None) -> dict:
    """Teilt eine Ausgabe. Ohne ``parts`` nach den Anteilen der Personen."""
    with db.tx(immediate=True):
        tx = _transaction(db, tx_id)
        reason = shareable(db, tx)
        if reason:
            raise SharingError(409, reason)
        persons = _persons(db)
        total = -tx["amount_cents"]
        if parts is None:
            weights = {pid: p["weight"] for pid, p in persons.items()}
            if not any(w > 0 for pid, w in weights.items() if pid != tx["payer_id"]):
                raise SharingError(409, "Außer dem Zahler trägt niemand einen Anteil. Stelle die Anteile im Haushalt ein.")
            split = split_by_weight(total, weights, tx["payer_id"])
        else:
            if not isinstance(parts, list) or not parts:
                raise SharingError(400, "Die Aufteilung ist ungültig.")
            split = {}
            for part in parts:
                pid, cents = (part.get("person_id"), part.get("cents")) if isinstance(part, dict) else (None, None)
                if pid not in persons or pid in split or not _is_int(cents) or cents < 0:
                    raise SharingError(400, "Die Aufteilung ist ungültig.")
                split[pid] = cents
            if sum(split.values()) != total:
                raise SharingError(400, "Die Teile ergeben zusammen nicht den Betrag der Buchung.")
            if not any(cents > 0 for pid, cents in split.items() if pid != tx["payer_id"]):
                raise SharingError(400, "Mindestens eine andere Person muss einen Teil tragen.")
        db.execute("DELETE FROM tx_shares WHERE tx_id = ?", (tx_id,))
        db.executemany("INSERT INTO tx_shares(tx_id, person_id, cents) VALUES(?, ?, ?)",
                       [(tx_id, pid, cents) for pid, cents in split.items() if cents > 0])
    return get_share(db, tx_id)


def clear_share(db: Database, tx_id: int) -> dict:
    _transaction(db, tx_id)
    db.execute("DELETE FROM tx_shares WHERE tx_id = ?", (tx_id,))
    return get_share(db, tx_id)


# --- Was offen ist ---------------------------------------------------------

# Nur Teile, deren Buchung es noch gibt und deren Konto noch jemandem gehört.
_DEBTS = (
    "SELECT s.person_id AS debtor, a.owner_person_id AS payer, s.cents, t.id AS tx_id, t.booking_date, "
    "t.counterparty, t.purpose, -t.amount_cents AS total_cents FROM tx_shares AS s "
    "JOIN transactions AS t ON t.id = s.tx_id JOIN accounts AS a ON a.id = t.account_id "
    "WHERE a.owner_person_id IS NOT NULL AND a.archived = 0 AND t.amount_cents < 0 AND t.is_transfer = 0 "
    "AND s.person_id IN (SELECT id FROM persons) AND a.owner_person_id IN (SELECT id FROM persons)"
)


def _pair_net(db: Database) -> dict[tuple[int, int], int]:
    """Je Paar (kleinere ID, größere ID): positiv heißt, die größere schuldet der kleineren."""
    net: dict[tuple[int, int], int] = {}

    def owe(debtor: int, creditor: int, cents: int) -> None:
        if debtor == creditor:
            return
        low, high = min(debtor, creditor), max(debtor, creditor)
        net[(low, high)] = net.get((low, high), 0) + (cents if debtor == high else -cents)

    for row in db.query(f"SELECT debtor, payer, SUM(cents) AS cents FROM ({_DEBTS}) GROUP BY debtor, payer"):
        owe(row["debtor"], row["payer"], row["cents"])
    for row in db.query(
            "SELECT from_person_id AS f, to_person_id AS t, SUM(cents) AS cents FROM settlements "
            "WHERE from_person_id IN (SELECT id FROM persons) AND to_person_id IN (SELECT id FROM persons) "
            "GROUP BY f, t"):
        owe(row["f"], row["t"], -row["cents"])
    return net


def balances(db: Database, person_id: int | None = None) -> list[dict]:
    """Offene Beträge als „wer schuldet wem". Mit ``person_id`` nur die Paare mit dieser Person."""
    persons = _persons(db)
    out = []
    for (low, high), cents in sorted(_pair_net(db).items()):
        if not cents or (person_id is not None and person_id not in (low, high)):
            continue
        debtor, creditor = (high, low) if cents > 0 else (low, high)
        out.append({"from_id": debtor, "from": persons[debtor]["name"], "to_id": creditor,
                    "to": persons[creditor]["name"], "cents": abs(cents)})
    return out


def person_is_settled(db: Database, person_id: int) -> bool:
    return not balances(db, person_id)


def forget_person(db: Database, person_id: int) -> None:
    """Räumt die Einträge einer ausgeglichenen Person weg, bevor sie entfernt wird."""
    db.execute("DELETE FROM tx_shares WHERE person_id = ?", (person_id,))
    db.execute("DELETE FROM tx_shares WHERE tx_id IN (SELECT t.id FROM transactions AS t "
               "JOIN accounts AS a ON a.id = t.account_id WHERE a.owner_person_id = ?)", (person_id,))
    db.execute("DELETE FROM settlements WHERE from_person_id = ? OR to_person_id = ?", (person_id, person_id))


def _label(row: dict) -> str:
    return (row["counterparty"] or row["purpose"] or "Buchung")[:80]


def items(db: Database, person_id: int | None = None, limit: int = RECENT_ITEMS) -> list[dict]:
    """Die jüngsten geteilten Ausgaben. Mit ``person_id`` nur die, an denen sie beteiligt ist."""
    persons = _persons(db)
    where, params = "", []
    if person_id is not None:
        where = "WHERE tx_id IN (SELECT tx_id FROM debts WHERE debtor = ? OR payer = ?)"
        params = [person_id, person_id]
    rows = db.query(
        f"WITH debts AS ({_DEBTS}) SELECT * FROM debts {where} ORDER BY booking_date DESC, tx_id DESC, debtor", params)
    out: dict[int, dict] = {}
    for row in rows:
        item = out.get(row["tx_id"])
        if item is None:
            if len(out) >= limit:
                continue
            item = out[row["tx_id"]] = {
                "tx_id": row["tx_id"], "booking_date": row["booking_date"], "label": _label(row),
                "total_cents": row["total_cents"], "payer_id": row["payer"], "payer": persons[row["payer"]]["name"],
                "parts": []}
        item["parts"].append({"person_id": row["debtor"], "name": persons[row["debtor"]]["name"], "cents": row["cents"]})
    return list(out.values())


def list_settlements(db: Database, person_id: int | None = None, limit: int = RECENT_ITEMS) -> list[dict]:
    persons = _persons(db)
    where, params = "", []
    if person_id is not None:
        where, params = "WHERE from_person_id = ? OR to_person_id = ?", [person_id, person_id]
    rows = db.query(f"SELECT * FROM settlements {where} ORDER BY on_date DESC, id DESC LIMIT ?", (*params, limit))
    return [
        {"id": r["id"], "from_id": r["from_person_id"], "from": persons[r["from_person_id"]]["name"],
         "to_id": r["to_person_id"], "to": persons[r["to_person_id"]]["name"], "cents": r["cents"],
         "on_date": r["on_date"], "note": r["note"]}
        for r in rows if r["from_person_id"] in persons and r["to_person_id"] in persons
    ]


def add_settlement(db: Database, payload: dict, *, today: date | None = None) -> dict:
    persons = _persons(db)
    sender, receiver, cents = payload.get("from_person_id"), payload.get("to_person_id"), payload.get("cents")
    if sender not in persons or receiver not in persons or sender == receiver:
        raise SharingError(400, "Wähle zwei verschiedene Personen.")
    if not _is_int(cents) or not 0 < cents <= MAX_SETTLEMENT_CENTS:
        raise SharingError(400, "Der Betrag ist ungültig.")
    reference = today or date.today()
    on_date = payload.get("on_date") or reference.isoformat()
    try:
        if not isinstance(on_date, str) or date.fromisoformat(on_date) > reference:
            raise ValueError
    except ValueError:
        raise SharingError(400, "Das Datum ist ungültig.") from None
    note = payload.get("note")
    if note is not None and not isinstance(note, str):
        raise SharingError(400, "Die Notiz ist ungültig.")
    note = " ".join(note.split())[:MAX_NOTE_LENGTH] if note else None
    sid = db.insert("settlements", {"from_person_id": sender, "to_person_id": receiver, "cents": cents,
                                    "on_date": on_date, "note": note, "created": now_iso()})
    return next(s for s in list_settlements(db, limit=100000) if s["id"] == sid)


def delete_settlement(db: Database, settlement_id: int) -> None:
    if db.execute_count("DELETE FROM settlements WHERE id = ?", (settlement_id,)) != 1:
        raise SharingError(404, "Ausgleich nicht gefunden.")


# --- Anteilig zählen -------------------------------------------------------

def _scale(entries: list[dict], part: int, total: int) -> list[dict]:
    """Verkleinert die Einträge einer Buchung auf den Teil ``part`` von ``total``, auf den Cent genau."""
    if part <= 0 or total <= 0:
        return []
    whole = sum(e["amount_cents"] for e in entries)
    target = -part if whole == -total else round(whole * part / total)
    scaled = [dict(e, amount_cents=int(e["amount_cents"] * part / total)) for e in entries]
    rest = target - sum(e["amount_cents"] for e in scaled)
    if rest and scaled:
        max(scaled, key=lambda e: abs(e["amount_cents"]))["amount_cents"] += rest
    return [e for e in scaled if e["amount_cents"]]


def spending(db, start: str | None = None, end: str | None = None) -> list[dict]:
    """Einträge für Auswertung und Budgets, bei einer Person mit ihren Teilen geteilter Ausgaben.

    Für die Sicht einer Person zählt eine geteilte Ausgabe anteilig: Hat sie bezahlt, nur
    ihr eigener Teil; hat jemand anderes bezahlt, kommt ihr Teil dazu. Für den Haushalt
    und die Verwaltung bleibt jede Buchung ganz. Kontostände und Prognose rechnen nie
    hiermit – dort zählt, was wirklich vom Konto abging.
    """
    entries = ledger.entries(db, start, end)
    person = getattr(db, "person_id", None)
    if person is None or getattr(db, "part_kind", None) not in ("all", "own"):
        return entries
    main = db.parent
    rows = main.query(f"SELECT tx_id, debtor, payer, cents, total_cents FROM ({_DEBTS}) WHERE payer = ? OR debtor = ?",
                      (person, person))
    if not rows:
        return entries
    paid = {r["tx_id"]: r["total_cents"] for r in rows if r["payer"] == person}
    mine = {r["tx_id"]: r["cents"] for r in rows if r["debtor"] == person}
    borne = {r["tx_id"]: (r["cents"], r["total_cents"]) for r in rows if r["debtor"] == person and r["payer"] != person}

    by_tx: dict[int, list[dict]] = {}
    out = []
    for entry in entries:
        if entry["id"] in paid:
            by_tx.setdefault(entry["id"], []).append(entry)
        else:
            out.append(entry)
    for tx_id, group in by_tx.items():
        out.extend(_scale(group, mine.get(tx_id, 0), paid[tx_id]))
    if borne:
        # Die Buchungen der anderen liegen außerhalb der Sicht; geholt wird nur, was geteilt ist.
        foreign: dict[int, list[dict]] = {}
        for entry in ledger.entries(main, start, end):
            if entry["id"] in borne:
                foreign.setdefault(entry["id"], []).append(entry)
        for tx_id, group in foreign.items():
            part, total = borne[tx_id]
            out.extend(_scale(group, part, total))
    return out


def overview(db: Database, person_id: int | None = None) -> dict:
    return {"balances": balances(db, person_id), "items": items(db, person_id),
            "settlements": list_settlements(db, person_id)}


def for_person(db: Database, person_id: int | None) -> list[dict]:
    """Kurzform für die App: je anderer Person, was offen ist. Positiv heißt, sie schuldet mir."""
    if person_id is None:
        return []
    return [
        {"person": b["from"] if b["to_id"] == person_id else b["to"],
         "cents": b["cents"] if b["to_id"] == person_id else -b["cents"]}
        for b in balances(db, person_id)
    ]
