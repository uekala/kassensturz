"""HTTP-Routen: Konten, Personen, Teilen und Ausgleich. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Body

from . import allowance, audit, categorize, household, ledger, loans, sharing
from .db import get_db, now_iso
from .util import euro
from .web import _changed, _err
from .routes_transactions import _note_tx

router = APIRouter()

# --- Konten ----------------------------------------------------------------------------

ACCOUNT_FIELDS = ("name", "kind", "iban", "bank", "settlement_pattern", "in_forecast", "archived", "sort", "matures_on",
                  "owner_person_id", "allowance_cents", "allowance_interval", "loan_rate_milli", "loan_payment_cents")


def _clean_account(data: dict) -> dict:
    if data.get("iban"):
        data["iban"] = data["iban"].replace(" ", "").upper()
    if "matures_on" in data:
        value = (data["matures_on"] or "").strip() or None
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                _err(400, "Das Datum ist ungültig.")
        data["matures_on"] = value
    if "owner_person_id" in data:
        try:
            data["owner_person_id"] = household.parse_person_id(get_db(), data["owner_person_id"])
        except household.HouseholdError as error:
            _err(error.status, error.message)
    try:
        data.update(loans.clean_terms(data))
    except loans.LoanError as error:
        _err(error.status, error.message)
    return data


def _allowance_rules(existing: dict | None, data: dict) -> dict:
    try:
        return allowance.rules(get_db(), existing, data)
    except allowance.AllowanceError as error:
        _err(400, str(error))


# --- Haushalt ---------------------------------------------------------------

def _household(call, *args):
    try:
        return call(get_db(), *args)
    except household.HouseholdError as error:
        _err(error.status, error.message)


@router.get("/api/changes")
def changes(offset: int = 0, limit: int = 50, actor: str = ""):
    return audit.listing(get_db(), offset, limit, actor or None)


@router.get("/api/persons")
def persons():
    return household.list_persons(get_db())


@router.post("/api/persons")
def create_person(body: dict = Body(...)):
    result = _household(household.create_person, body)
    audit.subject(result.get("name"))
    return result


@router.patch("/api/persons/{pid}")
def update_person(pid: int, body: dict = Body(...)):
    before = get_db().scalar("SELECT name FROM persons WHERE id = ?", (pid,))
    result = _household(household.update_person, pid, body)
    after = result.get("name") if isinstance(result, dict) else None
    audit.subject(f"{before} heißt jetzt {after}" if before and after and before != after else before)
    return result


@router.delete("/api/persons/{pid}")
def delete_person(pid: int):
    audit.subject(get_db().scalar("SELECT name FROM persons WHERE id = ?", (pid,)))
    return _household(household.delete_person, pid)


@router.put("/api/persons/{pid}/budgets/{cid}")
def set_person_budget(pid: int, cid: int, body: dict = Body(...)):
    result = _household(household.set_own_budget, pid, cid, body.get("budget_cents"))
    _note_own_budget(get_db(), pid, result)
    _changed()
    return result


def _note_own_budget(db, person_id, result: dict) -> None:
    person = db.scalar("SELECT name FROM persons WHERE id = ?", (person_id,)) or "?"
    audit.note(f"Eigenes Budget von {person} für „{result['name']}“: "
               + (euro(result["limit_cents"]) if result.get("limit_cents") else "entfernt"))


def _sharing(call, *args):
    try:
        return call(get_db(), *args)
    except sharing.SharingError as error:
        _err(error.status, error.message)


@router.get("/api/household/sharing")
def household_sharing():
    return sharing.overview(get_db())


@router.get("/api/transactions/{tx_id}/share")
def transaction_share(tx_id: int):
    return _sharing(sharing.get_share, tx_id)


@router.put("/api/transactions/{tx_id}/share")
def share_transaction(tx_id: int, body: dict = Body(default={})):
    result = _sharing(sharing.set_share, tx_id, body.get("parts"))
    _note_tx(get_db(), tx_id, "mit dem Haushalt geteilt")
    return result


@router.delete("/api/transactions/{tx_id}/share")
def unshare_transaction(tx_id: int):
    result = _sharing(sharing.clear_share, tx_id)
    _note_tx(get_db(), tx_id, "Teilen aufgehoben")
    return result


@router.post("/api/household/settlements")
def add_settlement(body: dict = Body(...)):
    result = _sharing(sharing.add_settlement, body)
    audit.note(_settlement_text(result))
    return result


def _settlement_text(s: dict) -> str:
    return f"Ausgleichszahlung: {s.get('from')} an {s.get('to')}, {euro(s.get('cents'))}"


@router.delete("/api/household/settlements/{sid}")
def delete_settlement(sid: int):
    _sharing(sharing.delete_settlement, sid)
    return {"ok": True}


@router.get("/api/accounts")
def accounts():
    return ledger.accounts_with_balance(get_db(), include_archived=True)


@router.post("/api/accounts")
def create_account(body: dict = Body(...)):
    db = get_db()
    name = (body.get("name") or "").strip()
    if not name:
        _err(400, "Name fehlt.")
    data = {k: body.get(k) for k in ACCOUNT_FIELDS if k in body}
    data.update({"name": name[:60], "created": now_iso()})
    if "sort" not in body:
        data["sort"] = int(db.scalar("SELECT COALESCE(MAX(sort), 0) FROM accounts") or 0) + 1
    if "in_forecast" not in body and data.get("kind") in ledger.SAVINGS_KINDS:
        # Rücklagen, Anlagen und Kredite sind nicht für den Alltag da.
        data["in_forecast"] = 0
    aid = db.insert("accounts", _allowance_rules(None, _clean_account(data)))
    audit.subject(name[:60], aid)
    categorize.recategorize(db)
    return db.one("SELECT * FROM accounts WHERE id = ?", (aid,))


@router.post("/api/accounts/{aid}/balance-check/reset")
def reset_balance_check(aid: int):
    ledger.reset_balance_checks(get_db(), aid)
    _changed()
    return {"ok": True}


@router.get("/api/networth")
def net_worth():
    return {"history": ledger.net_worth_history(get_db())}


@router.patch("/api/accounts/{aid}")
def update_account(aid: int, body: dict = Body(...)):
    db = get_db()
    existing = db.one("SELECT * FROM accounts WHERE id = ?", (aid,))
    if not existing:
        _err(404, "Konto nicht gefunden.")
    data = _allowance_rules(existing, _clean_account({k: body[k] for k in ACCOUNT_FIELDS if k in body}))
    db.update("accounts", "id", aid, data)
    renamed = data.get("name") and data["name"] != existing["name"]
    audit.subject(f"{existing['name']} heißt jetzt {data['name']}" if renamed else existing["name"], aid)
    if {"settlement_pattern", "iban", "kind", "archived"} & set(data):
        categorize.recategorize(db)
    _changed()
    return {"ok": True}


@router.post("/api/accounts/{aid}/balance")
def set_balance(aid: int, body: dict = Body(...)):
    db = get_db()
    cents = body.get("balance_cents")
    if cents is None:
        _err(400, "Betrag fehlt.")
    on = body.get("date") or date.today().isoformat()
    acc = db.one("SELECT kind FROM accounts WHERE id = ?", (aid,))
    if not acc:
        _err(404, "Konto nicht gefunden.")
    cents = ledger.signed_value(acc["kind"], int(cents))
    name = db.scalar("SELECT name FROM accounts WHERE id = ?", (aid,))
    word = "Restschuld" if acc["kind"] == "kredit" else "Wert" if acc["kind"] in ledger.VALUE_KINDS else "Kontostand"
    audit.note(f"{word} von „{name}“ eingetragen: {euro(abs(cents) if acc['kind'] == 'kredit' else cents)}", aid)
    ledger.set_balance_anchor(db, aid, cents, on)
    if acc["kind"] in ledger.VALUE_KINDS:
        ledger.record_valuation(db, aid, cents, on)
    _changed()
    return {"ok": True}


@router.get("/api/accounts/{aid}/loan")
def loan_plan(aid: int, extra_cents: int = 0):
    try:
        return loans.overview(get_db(), aid, extra_cents)
    except loans.LoanError as error:
        _err(error.status, error.message)


@router.delete("/api/accounts/{aid}")
def delete_account(aid: int):
    db = get_db()
    gone = db.one("SELECT name, (SELECT COUNT(*) FROM transactions WHERE account_id = ?) AS n FROM accounts WHERE id = ?", (aid, aid))
    if gone:
        audit.note(f"Konto „{gone['name']}“ gelöscht, mit {gone['n']} Buchungen")
    ledger.delete_account(db, aid)
    categorize.recategorize(db)
    _changed()
    return {"ok": True}
