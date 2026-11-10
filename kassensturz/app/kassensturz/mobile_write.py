"""Write operations and reference lists for the device-authenticated mobile API.

The server database stays the single source of truth. Mobile clients may

* create manual transactions on accounts without an automatic bank feed,
* change category and note of any transaction,
* change or delete transactions they created manually.

Bank-imported transactions are never deleted or rewritten here: the next bank
sync would bring them back and the duplicate detection relies on their hash.
Every create request carries a client-generated request id; replaying the same
id returns the already stored transaction instead of inserting a second one.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from typing import Any

from . import categorize, contracts, ledger
from .db import Database, now_iso
from .util import tx_hash


MANUAL_SOURCE = "manual"
MAX_AMOUNT_CENTS = 10**11
MAX_COUNTERPARTY_LENGTH = 100
MAX_PURPOSE_LENGTH = 140
MAX_NOTE_LENGTH = 300
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{15,63}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CREATE_FIELDS = frozenset(
    {
        "client_request_id",
        "account_id",
        "booking_date",
        "amount_cents",
        "counterparty",
        "purpose",
        "category_id",
        "note",
    }
)
UPDATE_FIELDS = frozenset(
    {"booking_date", "amount_cents", "counterparty", "purpose", "category_id", "note"}
)
MANUAL_ONLY_FIELDS = frozenset({"booking_date", "amount_cents", "counterparty", "purpose"})


class MobileWriteError(Exception):
    """A mobile write request was rejected; carries a stable API error code."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _invalid(message: str) -> MobileWriteError:
    return MobileWriteError(400, "invalid_request", message)


def _clean_text(value: Any, maximum: int, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise _invalid(f"{field} fehlt.")
        return None
    if not isinstance(value, str):
        raise _invalid(f"{field} muss Text sein.")
    normalized = " ".join(value.split())
    if not normalized:
        if required:
            raise _invalid(f"{field} fehlt.")
        return None
    if len(normalized) > maximum:
        raise _invalid(f"{field} ist zu lang.")
    return normalized


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2**63:
        raise _invalid(f"{field} ist ungültig.")
    return value


def _amount(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid("Der Betrag muss in ganzen Cent angegeben werden.")
    if value == 0 or abs(value) > MAX_AMOUNT_CENTS:
        raise _invalid("Der Betrag ist ungültig.")
    return value


def _booking_date(value: Any, *, today: date | None = None) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise _invalid("Das Buchungsdatum ist ungültig.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _invalid("Das Buchungsdatum ist ungültig.") from exc
    reference = today or date.today()
    if parsed < date(2000, 1, 1) or parsed > reference + timedelta(days=366):
        raise _invalid("Das Buchungsdatum liegt außerhalb des erlaubten Bereichs.")
    return parsed.isoformat()


def _request_id(value: Any) -> str:
    if not isinstance(value, str) or not _REQUEST_ID.fullmatch(value):
        raise _invalid("Die Anfragekennung ist ungültig.")
    return value


def _category(db: Database, value: Any) -> dict:
    category_id = _positive_id(value, "category_id")
    row = db.one("SELECT id, kind FROM categories WHERE id = ?", (category_id,))
    if row is None:
        raise _invalid("Die Kategorie ist unbekannt.")
    return row


def account_accepts_manual_entries(account: dict) -> bool:
    """Only accounts without FinTS or Open Banking feed take manual entries."""
    return (
        not account.get("archived")
        and account.get("connection_id") is None
        and account.get("eb_session_id") is None
    )


def serialize_transaction(row: dict) -> dict:
    """Allowlisted transaction DTO shared by list and write responses."""
    return {
        "id": int(row["id"]),
        "account_id": int(row["account_id"]),
        "booking_date": row["booking_date"],
        "value_date": row.get("value_date"),
        "amount_cents": int(row["amount_cents"]),
        "currency": row.get("currency") or "EUR",
        "counterparty": row.get("counterparty"),
        "purpose": row.get("purpose"),
        "note": row.get("note"),
        "account_name": row.get("account_name"),
        "category": (
            {"id": int(row["category_id"]), "name": row.get("category_name")}
            if row.get("category_id") is not None
            else None
        ),
        "manual": row.get("source") == MANUAL_SOURCE,
    }


def _load(db: Database, where: str, params: tuple) -> dict | None:
    return db.one(
        "SELECT t.id, t.account_id, t.booking_date, t.value_date, t.amount_cents, t.currency, "
        "t.counterparty, t.purpose, t.note, t.source, t.category_id, "
        "a.name AS account_name, c.name AS category_name "
        "FROM transactions AS t JOIN accounts AS a ON a.id = t.account_id "
        "LEFT JOIN categories AS c ON c.id = t.category_id "
        f"WHERE a.archived = 0 AND {where}",
        params,
    )


def _require_transaction(db: Database, tx_id: int) -> dict:
    if isinstance(tx_id, bool) or not isinstance(tx_id, int) or not 0 < tx_id < 2**63:
        raise MobileWriteError(404, "not_found", "Buchung nicht gefunden.")
    row = _load(db, "t.id = ?", (tx_id,))
    if row is None:
        raise MobileWriteError(404, "not_found", "Buchung nicht gefunden.")
    return row


def create_transaction(db: Database, payload: dict, *, today: date | None = None) -> tuple[dict, bool]:
    """Insert one manual transaction. Returns ``(dto, created)``.

    ``created`` is False when the request id was already used; the stored
    transaction is returned unchanged in that case.
    """
    unknown = set(payload) - CREATE_FIELDS
    if unknown:
        raise _invalid("Die Anfrage enthält unbekannte Felder.")

    request_id = _request_id(payload.get("client_request_id"))
    account_id = _positive_id(payload.get("account_id"), "account_id")
    booking_date = _booking_date(payload.get("booking_date"), today=today)
    amount_cents = _amount(payload.get("amount_cents"))
    counterparty = _clean_text(
        payload.get("counterparty"), MAX_COUNTERPARTY_LENGTH, "Gegenüber", required=True
    )
    purpose = _clean_text(payload.get("purpose"), MAX_PURPOSE_LENGTH, "Verwendungszweck")
    note = _clean_text(payload.get("note"), MAX_NOTE_LENGTH, "Notiz")
    category = _category(db, payload["category_id"]) if payload.get("category_id") is not None else None

    with db.tx(immediate=True):
        existing = _load(db, "t.client_request_id = ?", (request_id,))
        if existing is not None:
            return serialize_transaction(existing), False

        account = db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if account is None or account.get("archived"):
            raise _invalid("Das Konto ist unbekannt.")
        if not account_accepts_manual_entries(account):
            raise MobileWriteError(
                409,
                "account_not_manual",
                "Auf Konten mit Bankabruf können keine Umsätze von Hand angelegt werden.",
            )

        data = {
            "account_id": account_id,
            "booking_date": booking_date,
            "value_date": booking_date,
            "amount_cents": amount_cents,
            "currency": account.get("currency") or "EUR",
            "counterparty": counterparty,
            "purpose": purpose,
            "note": note,
            "source": MANUAL_SOURCE,
            "hash": tx_hash(account_id, booking_date, amount_cents, counterparty, purpose),
            "client_request_id": request_id,
            "created": now_iso(),
        }
        if category is not None:
            data.update(
                {
                    "category_id": category["id"],
                    "category_locked": 1,
                    "is_transfer": 1 if category["kind"] == "transfer" else 0,
                    "rule_ref": "manual",
                }
            )
        try:
            tx_id = db.insert("transactions", data)
        except sqlite3.IntegrityError:
            # A concurrent request with the same id won the race.
            existing = _load(db, "t.client_request_id = ?", (request_id,))
            if existing is None:
                raise
            return serialize_transaction(existing), False

    if category is None:
        categorize.recategorize(db, [tx_id])
    return serialize_transaction(_require_transaction(db, tx_id)), True


def update_transaction(db: Database, tx_id: int, payload: dict, *, today: date | None = None) -> dict:
    """Change a transaction. Bank transactions only accept category and note."""
    if not payload:
        raise _invalid("Die Anfrage enthält keine Änderungen.")
    unknown = set(payload) - UPDATE_FIELDS
    if unknown:
        raise _invalid("Die Anfrage enthält unbekannte Felder.")

    with db.tx(immediate=True):
        row = _require_transaction(db, tx_id)
        manual = row.get("source") == MANUAL_SOURCE
        if not manual and set(payload) & MANUAL_ONLY_FIELDS:
            raise MobileWriteError(
                409,
                "not_editable",
                "Bei Bankumsätzen lassen sich nur Kategorie und Notiz ändern.",
            )

        data: dict[str, Any] = {}
        if "note" in payload:
            data["note"] = _clean_text(payload["note"], MAX_NOTE_LENGTH, "Notiz")
        if payload.get("category_id") is not None:
            category = _category(db, payload["category_id"])
            data.update(
                {
                    "category_id": category["id"],
                    "category_locked": 1,
                    "is_transfer": 1 if category["kind"] == "transfer" else 0,
                    "rule_ref": "manual",
                }
            )
        elif "category_id" in payload:
            raise _invalid("Die Kategorie ist unbekannt.")

        if manual:
            if "booking_date" in payload:
                data["booking_date"] = _booking_date(payload["booking_date"], today=today)
                data["value_date"] = data["booking_date"]
            if "amount_cents" in payload:
                data["amount_cents"] = _amount(payload["amount_cents"])
            if "counterparty" in payload:
                data["counterparty"] = _clean_text(
                    payload["counterparty"], MAX_COUNTERPARTY_LENGTH, "Gegenüber", required=True
                )
            if "purpose" in payload:
                data["purpose"] = _clean_text(
                    payload["purpose"], MAX_PURPOSE_LENGTH, "Verwendungszweck"
                )
            if set(data) & MANUAL_ONLY_FIELDS:
                merged = {**row, **data}
                data["hash"] = tx_hash(
                    merged["account_id"],
                    merged["booking_date"],
                    merged["amount_cents"],
                    merged.get("counterparty"),
                    merged.get("purpose"),
                )
        db.update("transactions", "id", tx_id, data)
    return serialize_transaction(_require_transaction(db, tx_id))


def delete_transaction(db: Database, tx_id: int) -> None:
    """Delete one manually created transaction together with its splits."""
    with db.tx(immediate=True):
        row = _require_transaction(db, tx_id)
        if row.get("source") != MANUAL_SOURCE:
            raise MobileWriteError(
                409,
                "not_deletable",
                "Bankumsätze können nicht gelöscht werden.",
            )
        db.execute("DELETE FROM splits WHERE tx_id = ?", (tx_id,))
        db.execute(
            "DELETE FROM transactions WHERE id = ? AND source = ?",
            (tx_id, MANUAL_SOURCE),
        )


def list_accounts(db: Database) -> dict:
    """Active accounts with current balance; no IBAN or bank reference."""
    items = []
    for account in ledger.accounts_with_balance(db):
        items.append(
            {
                "id": int(account["id"]),
                "name": account.get("name"),
                "type": account.get("kind"),
                "currency": account.get("currency") or "EUR",
                "balance_cents": int(account.get("balance_now") or 0),
                "balance_known": bool(account.get("balance_known")),
                "balance_date": account.get("balance_date"),
                "transaction_count": int(account.get("tx_count") or 0),
                "manual_entries": account_accepts_manual_entries(account),
            }
        )
    return {"items": items}


def list_categories(db: Database) -> dict:
    rows = db.query(
        "SELECT id, name, parent_id, kind, color FROM categories ORDER BY sort, name"
    )
    return {
        "items": [
            {
                "id": int(row["id"]),
                "name": row.get("name"),
                "parent_id": row.get("parent_id"),
                "kind": row.get("kind"),
                "color": row.get("color"),
            }
            for row in rows
        ]
    }


def list_contracts(db: Database, *, today: date | None = None) -> dict:
    """Detected and manual contracts without provider contact or customer data."""
    reference = today or date.today()
    contracts.detect(db)
    items = []
    for contract in contracts.list_contracts(db):
        if contract.get("status") == "ignored":
            continue
        items.append(
            {
                "key": contract["key"],
                "name": contract.get("name"),
                "kind": contract.get("kind"),
                "interval": contract.get("interval"),
                "amount_cents": int(contract.get("amount_cents") or 0),
                "monthly_cents": int(contract.get("monthly_cents") or 0),
                "next_due": contract.get("next_due"),
                "status": contract.get("status"),
                "running": bool(contracts.is_running(contract, reference)),
                "category_name": contract.get("category_name"),
                "account_name": contract.get("account_name"),
                "cancellation_deadline": contract.get("deadline"),
            }
        )
    return {"items": items}
