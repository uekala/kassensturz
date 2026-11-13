"""Rücklagen für seltene Kosten und Sparziele."""
from __future__ import annotations

import math
from datetime import date

from . import contracts as contracts_mod
from . import ledger
from .db import Database, now_iso
from .util import add_months

MAX_GOAL_CENTS = 1_000_000_000
MAX_GOALS = 50


def reserve(cons: list[dict], today: date, period_end: date) -> dict:
    """Was für viertel-, halb- und jährliche Verträge heute zurückgelegt sein sollte.

    Jede Zahlung wird gleichmäßig über ihren Abstand verteilt: Eine Versicherung über 600 €
    im Jahr braucht 50 € im Monat, sechs Monate nach der letzten Abbuchung also 300 €.
    Was noch im laufenden Zeitraum abgebucht wird, steckt schon in den festen Abbuchungen
    und zählt hier nicht."""
    items = []
    for c in cons:
        spec = contracts_mod.INTERVAL_BY_NAME.get(c.get("interval") or "")
        months = spec[4] if spec else 0
        if months < 3 or c.get("kind") != "expense" or not c.get("next_due"):
            continue
        if not contracts_mod.is_running(c, today):
            continue
        try:
            due = date.fromisoformat(c["next_due"])
        except ValueError:
            continue
        if due <= period_end:
            continue
        amount = abs(int(c["amount_cents"] or 0))
        start = add_months(due, -months)
        span = max(1, (due - start).days)
        share = min(1.0, max(0.0, (today - start).days / span))
        items.append({"key": c["key"], "name": c["name"], "amount_cents": amount, "next_due": c["next_due"],
                      "interval": c["interval"], "monthly_cents": round(amount / months),
                      "reserved_cents": round(amount * share)})
    items.sort(key=lambda i: i["next_due"])
    return {"items": items, "reserved_cents": sum(i["reserved_cents"] for i in items),
            "monthly_cents": sum(i["monthly_cents"] for i in items)}


def _months_left(today: date, due: date) -> int:
    """Volle und angebrochene Monate bis zum Ziel, mindestens einer."""
    months = (due.year - today.year) * 12 + due.month - today.month
    if due.day > today.day:
        months += 1
    return max(1, months)


def list_goals(db: Database, today: date | None = None) -> list[dict]:
    """Sparziele mit Stand, Rest und nötiger Monatsrate.

    Hängt ein Ziel an einem Konto, zählt dessen Stand; mehrere Ziele am selben Konto teilen ihn
    in der Reihenfolge, in der sie angelegt wurden. Ohne Konto gilt der von Hand gepflegte Betrag."""
    today = today or date.today()
    balances = {a["id"]: max(0, a["balance_now"]) for a in ledger.accounts_with_balance(db) if a["balance_known"]}
    names = {a["id"]: a["name"] for a in db.query("SELECT id, name FROM accounts")}
    out = []
    for g in db.query("SELECT * FROM goals ORDER BY id"):
        target = int(g["target_cents"])
        if g["account_id"] in balances:
            saved = min(target, balances[g["account_id"]])
            balances[g["account_id"]] -= saved
        else:
            saved = min(target, max(0, int(g["saved_cents"] or 0)))
        rest = target - saved
        due = None
        try:
            due = date.fromisoformat(g["due_date"]) if g["due_date"] else None
        except ValueError:
            due = None
        monthly = None
        if rest and due and due > today:
            monthly = math.ceil(rest / _months_left(today, due))
        status = "done" if rest == 0 else "late" if due and due <= today else "open"
        out.append({"id": g["id"], "name": g["name"], "target_cents": target, "saved_cents": saved, "rest_cents": rest,
                    "due_date": g["due_date"], "account_id": g["account_id"], "account_name": names.get(g["account_id"]),
                    "linked": g["account_id"] in names, "monthly_cents": monthly, "status": status,
                    "progress": round(saved / target, 4) if target else 0})
    return out


class GoalError(ValueError):
    """Die Angaben zu einem Sparziel passen nicht."""


def _clean(db: Database, body: dict, existing: dict | None = None) -> dict:
    data: dict = {}
    if "name" in body or not existing:
        name = " ".join(str(body.get("name") or "").split())[:60]
        if not name:
            raise GoalError("Name fehlt.")
        data["name"] = name
    if "target_cents" in body or not existing:
        target = body.get("target_cents")
        if isinstance(target, bool) or not isinstance(target, int) or not 0 < target <= MAX_GOAL_CENTS:
            raise GoalError("Bitte einen Zielbetrag größer als 0 eingeben.")
        data["target_cents"] = target
    if "saved_cents" in body:
        saved = body.get("saved_cents") or 0
        if isinstance(saved, bool) or not isinstance(saved, int) or not 0 <= saved <= MAX_GOAL_CENTS:
            raise GoalError("Der gesparte Betrag ist ungültig.")
        data["saved_cents"] = saved
    if "due_date" in body:
        due = (body.get("due_date") or "").strip() or None
        if due:
            try:
                date.fromisoformat(due)
            except ValueError as error:
                raise GoalError("Das Datum ist ungültig.") from error
        data["due_date"] = due
    if "account_id" in body:
        account = body.get("account_id") or None
        if account is not None and not db.one("SELECT id FROM accounts WHERE id = ?", (account,)):
            raise GoalError("Das Konto gibt es nicht.")
        data["account_id"] = account
    return data


def create_goal(db: Database, body: dict) -> int:
    if int(db.scalar("SELECT COUNT(*) FROM goals") or 0) >= MAX_GOALS:
        raise GoalError("Mehr Sparziele gehen nicht.")
    data = _clean(db, body)
    data["created"] = now_iso()
    return db.insert("goals", data)


def update_goal(db: Database, goal_id: int, body: dict) -> bool:
    existing = db.one("SELECT * FROM goals WHERE id = ?", (goal_id,))
    if not existing:
        return False
    data = _clean(db, body, existing)
    if data:
        db.update("goals", "id", goal_id, data)
    return True
