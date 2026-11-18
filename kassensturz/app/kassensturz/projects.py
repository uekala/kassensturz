"""Projekte: Buchungen quer zu Kategorien bündeln und sehen, was etwas insgesamt gekostet hat.

„Urlaub 2027“, „Auto“, „Badsanierung“: Die Kosten dafür liegen in vielen Kategorien und oft über
Monate verteilt. Ein Projekt sammelt die Buchungen ein und zeigt die Summe, die Verteilung auf
Kategorien und Monate und, wenn ein Rahmen gesetzt ist, was davon übrig ist.

Eine Buchung gehört zu höchstens einem Projekt. An Kategorie, Budget und Auswertung der Buchung
ändert das nichts. Erstattungen im Projekt mindern die Kosten; Umbuchungen zählen nicht.
"""
from __future__ import annotations

from collections import defaultdict

from . import ledger
from .db import Database, now_iso

MAX_NAME = 60
MAX_NOTE = 200
MAX_CENTS = 1_000_000_000
# So viele Buchungen nimmt ein Aufruf höchstens auf.
MAX_ASSIGN = 5000
TX_SHOWN = 200


class ProjectError(ValueError):
    """Die Angaben passen nicht; ``status`` ist der HTTP-Status dazu."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _name(db: Database, value, own_id: int | None = None) -> str:
    if value is not None and not isinstance(value, str):
        raise ProjectError(400, "Der Name ist ungültig.")
    name = " ".join((value or "").split())[:MAX_NAME]
    if not name:
        raise ProjectError(400, "Bitte einen Namen für das Projekt eintragen.")
    twin = db.one("SELECT id FROM projects WHERE lower(name) = lower(?)", (name,))
    if twin and twin["id"] != own_id:
        raise ProjectError(409, "Ein Projekt mit diesem Namen gibt es schon.")
    return name


def _budget(value) -> int | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_CENTS:
        raise ProjectError(400, "Der Rahmen ist ungültig.")
    return value


def _note(value) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ProjectError(400, "Die Notiz ist ungültig.")
    return " ".join((value or "").split())[:MAX_NOTE] or None


def _row(db: Database, project_id: int) -> dict:
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not row:
        raise ProjectError(404, "Dieses Projekt gibt es nicht.")
    return row


def _entries(db: Database, project_id: int | None = None) -> dict[int, list[dict]]:
    """Die Buchungen der Projekte als Einträge der Auswertung (Aufteilungen einzeln), je Projekt."""
    links = db.query("SELECT tx_id, project_id FROM project_tx" + (" WHERE project_id = ?" if project_id else ""),
                     (project_id,) if project_id else ())
    if not links:
        return {}
    of = {r["tx_id"]: r["project_id"] for r in links}
    days = db.one(f"SELECT MIN(booking_date) AS first, MAX(booking_date) AS last FROM transactions WHERE id IN "
                  f"(SELECT tx_id FROM project_tx{' WHERE project_id = ?' if project_id else ''})",
                  (project_id,) if project_id else ())
    out: dict[int, list[dict]] = defaultdict(list)
    if not days or not days["first"]:
        return out
    for e in ledger.entries(db, days["first"], days["last"]):
        if e["id"] in of and not e["is_transfer"]:
            out[of[e["id"]]].append(e)
    return out


def _totals(entries: list[dict]) -> dict:
    spent = -sum(e["amount_cents"] for e in entries if e["amount_cents"] < 0)
    back = sum(e["amount_cents"] for e in entries if e["amount_cents"] > 0)
    days = sorted(e["booking_date"] for e in entries)
    return {"cost_cents": spent - back, "spent_cents": spent, "back_cents": back, "count": len({e["id"] for e in entries}),
            "first": days[0] if days else None, "last": days[-1] if days else None}


def _shape(row: dict, entries: list[dict]) -> dict:
    out = {"id": row["id"], "name": row["name"], "note": row["note"], "budget_cents": row["budget_cents"],
           "archived": bool(row["archived"]), **_totals(entries)}
    out["left_cents"] = None if not row["budget_cents"] else row["budget_cents"] - out["cost_cents"]
    return out


def overview(db: Database) -> dict:
    """Alle Projekte mit ihren Kosten: laufende zuerst, darin das zuletzt bebuchte oben."""
    entries = _entries(db)
    items = [_shape(r, entries.get(r["id"], [])) for r in db.query("SELECT * FROM projects")]
    items.sort(key=lambda p: (p["archived"], -(int((p["last"] or "0000-00-00").replace("-", ""))), p["name"].lower()))
    return {"items": items, "active": sum(1 for p in items if not p["archived"])}


def detail(db: Database, project_id: int) -> dict:
    """Ein Projekt mit Ausgaben je Kategorie, Kosten je Monat (Erstattungen abgezogen) und seinen jüngsten Buchungen."""
    row = _row(db, project_id)
    entries = _entries(db, project_id).get(project_id, [])
    out = _shape(row, entries)
    cats = {c["id"]: c for c in db.query("SELECT id, name, parent_id FROM categories")}
    by_cat: dict = defaultdict(int)
    by_month: dict = defaultdict(int)
    for e in entries:
        cat = cats.get(e["category_id"])
        top = cats.get(cat["parent_id"]) if cat and cat["parent_id"] else cat
        if e["amount_cents"] < 0:  # Kategorien zeigen, wofür Geld ausgegeben wurde; Erstattungen stehen als eigene Summe
            by_cat[top["id"] if top else None] += -e["amount_cents"]
        by_month[e["booking_date"][:7]] += -e["amount_cents"]
    out["categories"] = sorted(({"category_id": cid, "name": cats[cid]["name"] if cid in cats else "Ohne Kategorie", "cents": c}
                                for cid, c in by_cat.items() if c), key=lambda x: -x["cents"])
    out["months"] = [{"month": m, "cents": c} for m, c in sorted(by_month.items())]
    out["transactions"] = db.query(
        "SELECT t.id, t.booking_date, t.amount_cents, t.counterparty, t.purpose, t.is_transfer, a.name AS account_name, "
        "c.name AS category_name FROM project_tx p JOIN transactions t ON t.id = p.tx_id JOIN accounts a ON a.id = t.account_id "
        "LEFT JOIN categories c ON c.id = t.category_id WHERE p.project_id = ? ORDER BY t.booking_date DESC, t.id DESC LIMIT ?",
        (project_id, TX_SHOWN))
    return out


def create(db: Database, payload: dict) -> dict:
    with db.tx(immediate=True):
        project_id = db.insert("projects", {"name": _name(db, payload.get("name")), "note": _note(payload.get("note")),
                                            "budget_cents": _budget(payload.get("budget_cents")), "archived": 0,
                                            "created": now_iso()})
    return detail(db, project_id)


def change(db: Database, project_id: int, payload: dict) -> dict:
    with db.tx(immediate=True):
        _row(db, project_id)
        data = {}
        if "name" in payload:
            data["name"] = _name(db, payload["name"], project_id)
        if "note" in payload:
            data["note"] = _note(payload["note"])
        if "budget_cents" in payload:
            data["budget_cents"] = _budget(payload["budget_cents"])
        if "archived" in payload:
            data["archived"] = 1 if payload["archived"] else 0
        if data:
            db.update("projects", "id", project_id, data)
    return detail(db, project_id)


def delete(db: Database, project_id: int) -> None:
    """Löscht das Projekt. Die Buchungen bleiben, nur die Zuordnung fällt weg."""
    with db.tx(immediate=True):
        _row(db, project_id)
        db.execute("DELETE FROM project_tx WHERE project_id = ?", (project_id,))
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def _ids(value) -> list[int]:
    if not isinstance(value, list) or not value or len(value) > MAX_ASSIGN or any(
            isinstance(i, bool) or not isinstance(i, int) for i in value):
        raise ProjectError(400, f"Bitte 1 bis {MAX_ASSIGN} Buchungen angeben.")
    return list(dict.fromkeys(value))


def assign(db: Database, project_id: int, tx_ids) -> dict:
    """Ordnet Buchungen dem Projekt zu. Was in einem anderen Projekt lag, wechselt hierher."""
    ids = _ids(tx_ids)
    with db.tx(immediate=True):
        _row(db, project_id)
        known = set()
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            known |= {r["id"] for r in db.query(
                f"SELECT id FROM transactions WHERE id IN ({','.join('?' * len(chunk))})", tuple(chunk))}
        if not known:
            raise ProjectError(404, "Keine dieser Buchungen gibt es.")
        moved = 0
        for tx_id in ids:
            if tx_id not in known:
                continue
            before = db.scalar("SELECT project_id FROM project_tx WHERE tx_id = ?", (tx_id,))
            if before == project_id:
                continue
            db.execute("INSERT OR REPLACE INTO project_tx(tx_id, project_id) VALUES(?, ?)", (tx_id, project_id))
            moved += 1
    return {"assigned": moved, "project": detail(db, project_id)}


def unassign(db: Database, tx_ids) -> dict:
    ids = _ids(tx_ids)
    removed = 0
    with db.tx(immediate=True):
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            removed += db.execute_count(f"DELETE FROM project_tx WHERE tx_id IN ({','.join('?' * len(chunk))})", tuple(chunk))
    return {"removed": removed}


def set_for(db: Database, tx_id: int, project_id) -> dict:
    """Setzt oder löst das Projekt einer einzelnen Buchung."""
    if not db.one("SELECT 1 FROM transactions WHERE id = ?", (tx_id,)):
        raise ProjectError(404, "Buchung nicht gefunden.")
    if project_id is None:
        unassign(db, [tx_id])
        return {"project_id": None}
    if isinstance(project_id, bool) or not isinstance(project_id, int):
        raise ProjectError(400, "Das Projekt ist ungültig.")
    assign(db, project_id, [tx_id])
    return {"project_id": project_id}


def prune(db: Database) -> None:
    """Entfernt Zuordnungen gelöschter Buchungen."""
    db.execute("DELETE FROM project_tx WHERE tx_id NOT IN (SELECT id FROM transactions)")
