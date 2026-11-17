"""Haushalt: Personen, Besitz von Konten und was ein Gerät sehen darf.

Ein Konto gehört einer Person oder allen. Ein Handy ist einer Person zugeordnet und
sieht deren Konten und die gemeinsamen. Die Oberfläche in Home Assistant ist die
Verwaltung des Haushalts und zeigt alles – wer Home Assistant verwaltet, kommt ohnehin
an die Datenbank.

Solange kein Konto jemandem gehört, ändert sich nichts: Jedes Gerät sieht alles.
"""
from __future__ import annotations

import re

from .db import Database, now_iso

MAX_PERSONS = 12
MAX_NAME_LENGTH = 40
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class HouseholdError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _name(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HouseholdError(400, "Bitte gib einen Namen an.")
    return " ".join(value.split())[:MAX_NAME_LENGTH]


def _color(value) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _COLOR.match(value):
        raise HouseholdError(400, "Die Farbe ist ungültig.")
    return value.lower()


def list_persons(db: Database) -> list[dict]:
    """Personen mit der Zahl ihrer Konten und ihrer aktiven Geräte."""
    return db.query(
        "SELECT p.id, p.name, p.color, "
        "(SELECT COUNT(*) FROM accounts AS a WHERE a.owner_person_id = p.id) AS accounts, "
        "(SELECT COUNT(*) FROM mobile_devices AS d WHERE d.person_id = p.id AND d.revoked_at IS NULL) AS devices "
        "FROM persons AS p ORDER BY p.sort, p.id"
    )


def person_exists(db: Database, person_id) -> bool:
    return isinstance(person_id, int) and not isinstance(person_id, bool) and bool(
        db.scalar("SELECT 1 FROM persons WHERE id = ?", (person_id,)))


def parse_person_id(db: Database, value) -> int | None:
    """Leer heißt „gemeinsam" oder „keiner Person zugeordnet"; sonst muss es die Person geben."""
    if value in (None, ""):
        return None
    if not person_exists(db, value):
        raise HouseholdError(400, "Diese Person gibt es nicht.")
    return int(value)


def create_person(db: Database, payload: dict) -> dict:
    name = _name(payload.get("name"))
    color = _color(payload.get("color"))
    with db.tx(immediate=True):
        if int(db.scalar("SELECT COUNT(*) FROM persons") or 0) >= MAX_PERSONS:
            raise HouseholdError(409, "Mehr Personen lassen sich nicht anlegen.")
        if db.one("SELECT id FROM persons WHERE lower(name) = lower(?)", (name,)):
            raise HouseholdError(409, "Eine Person mit diesem Namen gibt es schon.")
        person_id = db.insert("persons", {
            "name": name, "color": color, "created": now_iso(),
            "sort": int(db.scalar("SELECT COALESCE(MAX(sort), 0) FROM persons") or 0) + 1})
    return next(p for p in list_persons(db) if p["id"] == person_id)


def update_person(db: Database, person_id: int, payload: dict) -> dict:
    data = {}
    if "name" in payload:
        data["name"] = _name(payload["name"])
    if "color" in payload:
        data["color"] = _color(payload["color"])
    with db.tx(immediate=True):
        if not person_exists(db, person_id):
            raise HouseholdError(404, "Diese Person gibt es nicht.")
        if "name" in data and db.one(
                "SELECT id FROM persons WHERE lower(name) = lower(?) AND id != ?", (data["name"], person_id)):
            raise HouseholdError(409, "Eine Person mit diesem Namen gibt es schon.")
        db.update("persons", "id", person_id, data)
    return next(p for p in list_persons(db) if p["id"] == person_id)


def delete_person(db: Database, person_id: int) -> dict:
    """Entfernt die Person. Ihre Konten bleiben nicht für alle sichtbar zurück.

    Hat sie noch Konten oder Geräte, wird nichts gelöscht: Sonst würden private Konten
    still zu gemeinsamen. Die Verwaltung ordnet sie vorher bewusst neu zu.
    """
    with db.tx(immediate=True):
        if not person_exists(db, person_id):
            raise HouseholdError(404, "Diese Person gibt es nicht.")
        accounts = int(db.scalar("SELECT COUNT(*) FROM accounts WHERE owner_person_id = ?", (person_id,)) or 0)
        devices = int(db.scalar(
            "SELECT COUNT(*) FROM mobile_devices WHERE person_id = ? AND revoked_at IS NULL", (person_id,)) or 0)
        if accounts or devices:
            raise HouseholdError(
                409, "Der Person sind noch Konten oder Geräte zugeordnet. Ordne sie zuerst neu zu.")
        db.execute("UPDATE mobile_devices SET person_id = NULL WHERE person_id = ?", (person_id,))
        db.execute("UPDATE mobile_pairings SET person_id = NULL WHERE person_id = ?", (person_id,))
        db.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    return {"ok": True}


def set_device_person(db: Database, device_id: str, person_id: int | None) -> bool:
    return db.execute_count(
        "UPDATE mobile_devices SET person_id = ? WHERE id = ? AND revoked_at IS NULL", (person_id, device_id)) == 1


# --- Was eine Person sehen und ändern darf --------------------------------

def view(db: Database, person_id: int | None):
    """Lesesicht für die Abfragen eines Geräts."""
    return db.scoped(person_id)


def sees_account(db: Database, person_id: int | None, account_id: int) -> bool:
    return bool(view(db, person_id).scalar("SELECT 1 FROM accounts WHERE id = ?", (account_id,)))


def sees_transaction(db: Database, person_id: int | None, tx_id: int) -> bool:
    return bool(view(db, person_id).scalar("SELECT 1 FROM transactions WHERE id = ?", (tx_id,)))


def sees_receipt(db: Database, person_id: int | None, receipt_id: int) -> bool:
    return bool(view(db, person_id).scalar("SELECT 1 FROM receipts WHERE id = ?", (receipt_id,)))


def sees_contract(db: Database, person_id: int | None, key: str) -> bool:
    return bool(view(db, person_id).scalar("SELECT 1 FROM contracts WHERE key = ?", (key,)))


def profile(db: Database, person_id: int | None) -> dict:
    """Was die App über den Haushalt wissen muss: wer man ist und ob Konten getrennt sind."""
    person = db.one("SELECT id, name, color FROM persons WHERE id = ?", (person_id,)) if person_id else None
    return {
        "person": person,
        "persons": int(db.scalar("SELECT COUNT(*) FROM persons") or 0),
        "private_accounts": db.has_private_accounts(),
    }
