"""Taschengeld: ein Konto für ein Kind, das sich von selbst füllt.

Ein Taschengeld-Konto ist ein Konto ohne Bankabruf mit der Art ``taschengeld``. Es gehört
einem Kind. Betrag und Rhythmus stehen am Konto; ist ein Termin erreicht, schreibt
Kassensturz den Betrag gut. Ausgaben tragen die Erwachsenen von Hand ein.

Das Geld auf diesem Konto ist eine Abmachung, kein Bankguthaben: Es liegt weiter auf den
Konten der Eltern und ist dort schon gezählt. Deshalb zählt das Taschengeld-Konto weder
zum Vermögen noch zur Prognose noch zur Auswertung des Haushalts. Die Gutschrift ist als
Umbuchung markiert.
"""
from __future__ import annotations

from datetime import date, timedelta

from .db import Database, now_iso
from .util import add_months, tx_hash

KIND = "taschengeld"
SOURCE = "taschengeld"
INTERVALS = ("week", "month")
MAX_CENTS = 100_000  # 1.000 € je Termin
# So viele ausgefallene Termine werden höchstens nachgeholt, etwa nach einer langen Pause des Servers.
MAX_CATCH_UP = 12
LABEL = "Taschengeld"


class AllowanceError(ValueError):
    """Die Angaben zu einem Taschengeld-Konto passen nicht."""


def _step(day: date, interval: str) -> date:
    return day + timedelta(days=7) if interval == "week" else add_months(day, 1)


def rules(db: Database, existing: dict | None, data: dict, today: date | None = None) -> dict:
    """Ergänzt und prüft die Angaben eines Kontos, wenn es ein Taschengeld-Konto ist oder war."""
    existing = existing or {}
    today = today or date.today()
    kind = data.get("kind", existing.get("kind"))
    if kind != KIND:
        if existing.get("kind") == KIND or any(k in data for k in ("allowance_cents", "allowance_interval")):
            data.update({"allowance_cents": None, "allowance_interval": None, "allowance_next": None})
        return data
    owner = data.get("owner_person_id", existing.get("owner_person_id"))
    if owner is None:
        raise AllowanceError("Ein Taschengeld-Konto braucht ein Kind, dem es gehört.")
    cents = data.get("allowance_cents", existing.get("allowance_cents")) or None
    if cents is not None and (isinstance(cents, bool) or not isinstance(cents, int) or not 0 < cents <= MAX_CENTS):
        raise AllowanceError("Das Taschengeld muss zwischen 0,01 € und 1.000 € liegen.")
    interval = data.get("allowance_interval", existing.get("allowance_interval")) or "month"
    if interval not in INTERVALS:
        raise AllowanceError("Taschengeld gibt es wöchentlich oder monatlich.")
    data.update({"allowance_cents": cents, "allowance_interval": interval, "in_forecast": 0})
    if not cents:
        data["allowance_next"] = None
    elif not existing.get("allowance_next"):
        # Die erste Gutschrift kommt heute, danach im gewählten Rhythmus.
        data["allowance_next"] = today.isoformat()
    if not existing and data.get("balance_date") is None:
        # Der Stand gilt bis gestern, damit die Gutschrift von heute schon mitzählt.
        data.update({"balance_cents": 0, "balance_date": (today - timedelta(days=1)).isoformat()})
    return data


def apply(db: Database, today: date | None = None) -> int:
    """Schreibt fälliges Taschengeld gut. Gibt die Zahl der neuen Gutschriften zurück."""
    today = today or date.today()
    due = db.query(
        "SELECT id, allowance_cents, allowance_interval, allowance_next FROM accounts "
        "WHERE kind = ? AND archived = 0 AND allowance_cents > 0 AND allowance_next IS NOT NULL AND allowance_next <= ?",
        (KIND, today.isoformat()))
    if not due:
        return 0
    transfer = db.scalar("SELECT id FROM categories WHERE builtin_key = 'umbuchung'")
    added = 0
    for account in due:
        try:
            day = date.fromisoformat(account["allowance_next"])
        except ValueError:
            day = today
        interval = account["allowance_interval"] if account["allowance_interval"] in INTERVALS else "month"
        with db.tx(immediate=True):
            booked = 0
            while day <= today:
                if booked < MAX_CATCH_UP:
                    iso = day.isoformat()
                    # Der Schlüssel macht jede Gutschrift einmalig, auch wenn zwei Läufe sich überschneiden.
                    key = f"taschengeld:{account['id']}:{iso}"
                    if not db.one("SELECT id FROM transactions WHERE client_request_id = ?", (key,)):
                        db.insert("transactions", {
                            "account_id": account["id"], "booking_date": iso, "value_date": iso,
                            "amount_cents": account["allowance_cents"], "counterparty": LABEL, "source": SOURCE,
                            "category_id": transfer, "category_locked": 1, "is_transfer": 1, "rule_ref": "taschengeld",
                            "client_request_id": key, "created": now_iso(),
                            "hash": tx_hash(account["id"], iso, account["allowance_cents"], LABEL, None)})
                        added += 1
                    booked += 1
                day = _step(day, interval)
            db.update("accounts", "id", account["id"], {"allowance_next": day.isoformat()})
    return added
