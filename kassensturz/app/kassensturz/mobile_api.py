"""HTTP routes for the versioned, device-authenticated mobile API.

Administrative pairing/device-management routes are restricted to the
Home Assistant Ingress peer or loopback. Mobile routes require a valid device
credential. Transport and network admission are enforced by main middleware.
"""
from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlsplit

import qrcode
from qrcode.image.svg import SvgPathImage

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import analytics, anomalies, audit, banksync, expected, household, ledger, loans, mobile_read, mobile_write, openbanking, options, papers, planned, projects, services, sharing
from .db import get_db
from .util import euro
from .mobile_auth import (
    InvalidCredential,
    MobileAuthService,
    PairingLimitReached,
    PairingRejected,
)
from .mobile_security import address_in_networks, parse_trusted_proxy_networks, socket_peer


router = APIRouter()
CAPABILITIES = (
    "overview",
    "transactions",
    "accounts",
    "categories",
    "contracts",
    "transactions.write",
    "transactions.search",
    "stats",
    "budgets.write",
    "contracts.write",
    "categories.learn",
    "afford",
    "review",
    "goals",
    "tax",
    "receipts",
    "warranty",
    "accounts.write",
    "sync",
    "triage",
    "budgets.suggest",
    "news",
    "papers",
    "networth",
    "household",
    "household.sharing",
    "budgets.own",
    # Hinweise erledigen, geplante Ausgaben und erwartete Eingänge anlegen und abhaken
    "plans",
    # Projekte ansehen und Buchungen zuordnen; Tilgungsplan der Kredite
    "projects",
    "loans",
    # Änderungsprotokoll lesen
    "changes",
    # Umsätze und Auswertung nach „Ich“ und „Gemeinsam“ trennen
    "parts",
    # Eine ablaufende Bankfreigabe (Enable Banking) erneuern
    "banks.renew",
    # Wert eines Depots oder Restschuld eines Kredits eintragen
    "accounts.value",
    # Rückfragen der Bank beim Abruf (TAN, Freigabe, Verfahren) am Handy beantworten
    "sync.tan",
)
# What the phone of a child gets: reading its own account, nothing that writes.
CHILD_CAPABILITIES = ("overview", "transactions", "accounts", "categories", "transactions.search", "stats", "goals",
                      "news", "networth", "household")
INGRESS_IP = "172.30.32.2"
# Was auch das Handy eines Kindes darf, obwohl es sonst nur liest
READ_ONLY_ALLOWED = ("/api/v1/auth/logout", "/api/v1/news/seen")
MAX_PAIRING_SECRET_LENGTH = 128
MAX_TOKEN_LENGTH = 128
TRUSTED_PROXY_NETWORKS = parse_trusted_proxy_networks(
    options.network_security_settings()["trusted_proxies"]
)


def _error(
    status: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers=headers,
    )


def _auth_service() -> MobileAuthService:
    return MobileAuthService(get_db())


def _configured_mobile_server_url() -> str | None:
    """Return a strict HTTPS origin configured for mobile pairing QR codes."""
    value = options.load().get("mobile_server_url", "")
    if not isinstance(value, str):
        raise ValueError("Mobile server URL must be a string.")
    value = value.strip()
    if not value:
        return None

    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Mobile server URL is invalid.") from exc

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.path not in ("", "/"))
    ):
        raise ValueError("Mobile server URL must be an HTTPS origin without path.")
    return f"https://{parsed.netloc}".rstrip("/")


def _pairing_qr_svg_base64(payload: str) -> str:
    """Create a self-contained SVG QR image without any external service."""
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=4,
    )
    code.add_data(payload)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathImage)
    svg = image.to_string(encoding="unicode")
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


async def _json_object(request: Request) -> dict[str, Any] | None:
    try:
        payload = await request.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _local_admin_allowed(request: Request) -> bool:
    """Require an identified, admin-only HA Ingress session or local access."""
    peer = socket_peer(request)
    # A trusted reverse proxy may itself connect over loopback. Do not mistake
    # a tailnet-proxied request for a local HA administrator session.
    if address_in_networks(peer, TRUSTED_PROXY_NETWORKS):
        return False
    if peer is None:
        return False
    if peer.compressed == INGRESS_IP:
        # The Supervisor strips untrusted copies of these headers and sets
        # X-Remote-User-Id for the authenticated Ingress session. The add-on
        # also declares panel_admin: true so only HA administrators get one.
        user_id = request.headers.get("x-remote-user-id", "").strip()
        return bool(user_id)
    return peer.is_loopback


# Was die App an einer Buchung ändern kann, in Worten fürs Änderungsprotokoll.
_TX_FIELDS = {"category_id": "Kategorie", "note": "Notiz", "amount_cents": "Betrag", "booking_date": "Datum",
              "counterparty": "Empfänger", "purpose": "Zweck", "account_id": "Konto"}


def _note_tx_change(before: dict | None, payload: dict) -> None:
    if not before:
        return
    after = get_db().one("SELECT * FROM transactions WHERE id = ?", (before["id"],)) or before
    parts = []
    for field, word in _TX_FIELDS.items():
        if field not in payload or after.get(field) == before.get(field):
            continue
        if field == "category_id":
            parts.append(f"Kategorie „{get_db().scalar('SELECT name FROM categories WHERE id = ?', (after['category_id'],))}“")
        elif field == "note":
            parts.append("Notiz geändert" if after.get("note") else "Notiz gelöscht")
        else:
            parts.append(f"{word} geändert")
    if parts:
        audit.note(f"{audit.tx_label(before)}: {', '.join(parts)}", before["account_id"])
    else:
        audit.skip()


def _note_tx(tx_id: int, what: str) -> None:
    row = get_db().one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if row:
        audit.note(f"{audit.tx_label(row)}: {what}", row["account_id"])


def _view(device):
    """What this device may read: its person's accounts and the shared ones."""
    return household.view(get_db(), device.person_id)


PARTS = {"own", "shared"}


def _part_view(device, part: str | None):
    """Die Sicht des Geräts, auf Wunsch nur die eigenen ("own") oder nur die gemeinsamen Konten ("shared").

    Ein Kind sieht ohnehin nur das Eigene; für Kinderhandys und Geräte ohne Person gibt es keine Teile.
    ``None`` zurück heißt: ungültiger Wunsch."""
    if not part or part == "all":
        return _view(device)
    db = get_db()
    if part not in PARTS or device.person_id is None or household.profile(db, device.person_id)["read_only"]:
        return None
    return db.part(part, device.person_id) if part == "own" else db.part("shared")


def _not_found(what: str) -> JSONResponse:
    # Dieselbe Antwort wie für etwas, das es nicht gibt: Fremde Konten verraten sich nicht.
    return _error(404, "not_found", f"{what} nicht gefunden.")


def _authenticated_device(request: Request):
    header = request.headers.get("authorization", "")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return _error(
            401,
            "unauthorized",
            "Anmeldung erforderlich.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = parts[1]
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return _error(
            401,
            "unauthorized",
            "Anmeldung erforderlich.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        device = _auth_service().authenticate_access_token(token)
    except InvalidCredential:
        return _error(
            401,
            "unauthorized",
            "Anmeldung erforderlich.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # The phone of a child only reads. Signing out and marking news as seen stay possible.
    if (request.method.upper() != "GET" and request.url.path not in READ_ONLY_ALLOWED
            and household.is_child(get_db(), device.person_id)):
        return _error(403, "read_only", "Mit diesem Handy lässt sich nichts ändern.")
    audit.set_device(get_db(), device)
    return device


@router.post("/api/mobile/pairings")
async def create_pairing(request: Request):
    """Create a one-time pairing secret from the trusted local administration."""
    if not _local_admin_allowed(request):
        return _error(403, "forbidden", "Nur lokal über die Administration erlaubt.")

    try:
        server_url = _configured_mobile_server_url()
    except ValueError:
        return _error(
            503,
            "mobile_server_url_invalid",
            "Die Mobile-Serveradresse ist nicht als HTTPS-Adresse konfiguriert.",
        )

    payload = await _json_object(request) or {}
    try:
        person_id = household.parse_person_id(get_db(), payload.get("person_id"))
    except household.HouseholdError as error:
        return _error(error.status, "invalid_request", error.message)

    try:
        pairing = _auth_service().create_pairing(person_id)
    except PairingLimitReached:
        return _error(
            429,
            "rate_limited",
            "Zu viele aktive Kopplungsanfragen.",
            headers={"Retry-After": "300"},
        )

    response = {**pairing, "server_url": server_url, "person_id": person_id}
    if server_url is not None:
        qr_payload = json.dumps(
            {
                "type": "kassensturz-pairing",
                "version": 1,
                "server_url": server_url,
                "pairing_secret": pairing["pairing_secret"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        response["qr_svg_base64"] = _pairing_qr_svg_base64(qr_payload)

    # This is the only response that contains the raw pairing secret.
    return JSONResponse(
        response,
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/mobile/devices")
def list_devices(request: Request):
    """List device metadata only; never reveal token hashes or credentials."""
    if not _local_admin_allowed(request):
        return _error(403, "forbidden", "Nur lokal über die Administration erlaubt.")
    return {"items": _auth_service().list_devices()}


@router.delete("/api/mobile/devices/{device_id}")
def revoke_device(device_id: str, request: Request):
    """Revoke one device from the trusted local administration."""
    if not _local_admin_allowed(request):
        return _error(403, "forbidden", "Nur lokal über die Administration erlaubt.")
    if not device_id or len(device_id) > 128:
        return _error(404, "not_found", "Gerät nicht gefunden.")
    revoked = _auth_service().revoke_device(device_id)
    if not revoked:
        return _error(404, "not_found", "Gerät nicht gefunden.")
    return {"ok": True}


@router.patch("/api/mobile/devices/{device_id}")
async def assign_device(device_id: str, request: Request):
    """Assign a paired device to a person of the household, or to nobody."""
    if not _local_admin_allowed(request):
        return _error(403, "forbidden", "Nur lokal über die Administration erlaubt.")
    payload = await _json_object(request)
    if payload is None or set(payload) != {"person_id"} or not device_id or len(device_id) > 128:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    db = get_db()
    try:
        person_id = household.parse_person_id(db, payload["person_id"])
    except household.HouseholdError as error:
        return _error(error.status, "invalid_request", error.message)
    if not household.set_device_person(db, device_id, person_id):
        return _error(404, "not_found", "Gerät nicht gefunden.")
    return {"ok": True}


@router.get("/api/v1/health")
def mobile_health():
    """Return non-sensitive API health data for pre-pairing connection checks."""
    return {
        "status": "ok",
        "api_version": 1,
        "server": {"name": "Kassensturz", "version": options.VERSION},
    }


@router.post("/api/v1/pair")
async def redeem_pairing(request: Request):
    """Redeem a one-time pairing secret and issue device credentials."""
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")

    pairing_secret = payload.get("pairing_secret")
    device_name = payload.get("device_name")
    if (
        not isinstance(pairing_secret, str)
        or not 43 <= len(pairing_secret) <= MAX_PAIRING_SECRET_LENGTH
        or not isinstance(device_name, str)
        or not 1 <= len(device_name.strip()) <= 64
    ):
        return _error(400, "invalid_request", "Ungültige Anfrage.")

    try:
        credentials = _auth_service().redeem_pairing(pairing_secret, device_name)
    except PairingRejected:
        return _error(409, "pairing_rejected", "Kopplung konnte nicht abgeschlossen werden.")

    return JSONResponse(credentials, status_code=201, headers={"Cache-Control": "no-store"})


@router.post("/api/v1/auth/refresh")
async def refresh_session(request: Request):
    """Rotate the refresh token and issue a fresh access/refresh pair."""
    payload = await _json_object(request)
    refresh_token = payload.get("refresh_token") if payload is not None else None
    if not isinstance(refresh_token, str) or not 43 <= len(refresh_token) <= MAX_TOKEN_LENGTH:
        return _error(400, "invalid_request", "Ungültige Anfrage.")

    try:
        credentials = _auth_service().rotate_refresh_token(refresh_token)
    except InvalidCredential:
        return _error(
            401,
            "unauthorized",
            "Anmeldung erforderlich.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return JSONResponse(credentials, headers={"Cache-Control": "no-store"})


@router.post("/api/v1/auth/logout")
def logout(request: Request):
    """Revoke every credential belonging to the authenticated device."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    _auth_service().revoke_device(device.id)
    return {"ok": True}


@router.get("/api/v1/me")
def me(request: Request):
    """Return the authenticated device and non-sensitive server capabilities."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    profile = household.profile(get_db(), device.person_id)
    return {
        "device": {"id": device.id, "name": device.name},
        "server": {"name": "Kassensturz", "version": options.VERSION, "storage": "local"},
        "capabilities": list(CHILD_CAPABILITIES if profile["read_only"] else CAPABILITIES),
        "household": profile,
    }


@router.get("/api/v1/overview")
def overview(request: Request):
    """Return the allowlisted financial overview for the authenticated device."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    result = mobile_read.get_overview(get_db(), view=_view(device))
    result["household"] = household.profile(get_db(), device.person_id)
    result["household"]["balances"] = sharing.for_person(get_db(), device.person_id)
    # Budgets that only count this person's own accounts; "budgets" are the household's.
    result["own_budgets"] = mobile_read.budget_items(household.own_budgets(get_db(), device.person_id))
    if result["household"]["read_only"]:
        # A child sees its own money only: what the household spends against its budgets stays with the adults.
        result["budgets"] = []
    return result


@router.get("/api/v1/transactions")
def transactions(
    request: Request,
    limit: str | None = Query(default=None),
    offset: str | None = Query(default=None),
    month: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    part: str | None = Query(default=None),
):
    """Return a paginated and allowlisted transaction list."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    view = _part_view(device, part)
    if view is None:
        return _error(400, "invalid_query", "Ungültige Filter- oder Seitenparameter.")
    try:
        return mobile_read.list_transactions(
            view,
            limit=limit,
            offset=offset,
            month=month,
            account_id=account_id,
            category_id=category_id,
            q=q,
            kind=kind,
        )
    except mobile_read.MobileQueryError:
        return _error(400, "invalid_query", "Ungültige Filter- oder Seitenparameter.")


def _write_error(error: mobile_write.MobileWriteError) -> JSONResponse:
    return _error(error.status, error.code, error.message)


def _transaction_id(value: str) -> int | None:
    if not value.isascii() or not value.isdigit() or len(value) > 18:
        return None
    return int(value)


@router.get("/api/v1/stats")
def stats(request: Request, month: str | None = Query(default=None), part: str | None = Query(default=None)):
    """Return category spending, monthly totals and the balance curve."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    view = _part_view(device, part)
    if view is None:
        return _error(400, "invalid_query", "Ungültiger Monat oder Teil.")
    try:
        return mobile_read.get_stats(view, month=month)
    except mobile_read.MobileQueryError:
        return _error(400, "invalid_query", "Ungültiger Monat.")


@router.get("/api/v1/afford")
def afford(request: Request, amount_cents: int = Query(default=0)):
    """Say what a purchase of this amount would mean until the next salary."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    try:
        return mobile_read.get_afford(_view(device), amount_cents)
    except mobile_read.MobileQueryError:
        return _error(400, "invalid_query", "Ungültiger Betrag.")


@router.get("/api/v1/accounts")
def accounts(request: Request):
    """Return active accounts with balances and whether manual entries are allowed."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_write.list_accounts(_view(device))


def _sync_for(device, state: dict) -> dict:
    """The fetch state for this phone. A child's phone gets neither renewals nor the bank's questions."""
    adult = not household.is_child(get_db(), device.person_id)
    out = _sync_public(state, renew=adult)
    out["question"] = banksync.question() if adult else None
    return out


def _sync_public(state: dict, renew: bool = False) -> dict:
    """Bank names and times only. ``renew`` is the local number of a consent
    that may be renewed from this phone; never the session at the bank."""
    return {
        "sources": [
            {"name": s["name"], "last_sync": s["last_sync"], "state": s["state"], "days_left": s["days_left"],
             "accounts": s["accounts"], "renew": s.get("renew") if renew else None}
            for s in state["sources"]
        ],
        "last_sync": state["last_sync"],
        "newest_sync": state["newest_sync"],
        "next_sync": state["next_sync"],
        "run": state["run"],
        "can_start": state["can_start"],
        "wait_minutes": state["wait_minutes"],
    }


@router.get("/api/v1/sync")
def sync_status(request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return _sync_for(device, banksync.status(_view(device)))


@router.post("/api/v1/sync/answer")
async def sync_answer(request: Request):
    """Answer the bank's question of a running fetch: a TAN, a choice, or "approved in the banking app".

    ``qid`` names the exact question; an answer to one that is no longer open is refused."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None or set(payload) - {"qid", "value", "cancel"}:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    qid = payload.get("qid")
    if not isinstance(qid, str) or not qid or len(qid) > 32:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    try:
        if payload.get("cancel") is True:
            banksync.cancel(qid)
        else:
            banksync.answer(qid, payload.get("value"))
    except banksync.AnswerRefused as refused:
        return _error(409, "bank_refused", str(refused))
    return _sync_for(device, banksync.status(_view(device)))


def _psu(request: Request) -> dict:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return {"ip": forwarded or (request.client.host if request.client else ""),
            "ua": request.headers.get("user-agent") or ""}


@router.post("/api/v1/banks/renew")
async def bank_renew_start(request: Request):
    """Start renewing an expiring consent. Returns the bank's page to open; nothing changes yet."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    eb_id = (payload or {}).get("id")
    if not isinstance(eb_id, int) or isinstance(eb_id, bool):
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    db = get_db()
    session = openbanking.renewable(db, eb_id)
    if session is None:
        return _error(409, "bank_refused", "Diese Freigabe muss gerade nicht erneuert werden.")
    try:
        started = openbanking.start_auth(db, session["aspsp_name"], session["aspsp_country"] or "DE", eb_id, _psu(request))
    except openbanking.EBError as error:
        return _error(409, "bank_refused", str(error))
    return {"name": session["aspsp_name"], "url": started["url"], "days": started["days"]}


@router.post("/api/v1/banks/renew/complete")
async def bank_renew_complete(request: Request):
    """Finish a renewal with the address the bank sent the browser back to.

    Only a renewal started above is accepted, never a new bank. No fetch is
    started here: the next regular one uses the new consent."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    text = (payload or {}).get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return _error(400, "invalid_request", "Bitte die vollständige Adresse einfügen.")
    db = get_db()
    try:
        if openbanking.pending_renewal(text) is None:
            return _error(409, "bank_refused", "Diese Freigabe gehört zu keinem offenen Vorgang. Starte das Erneuern bitte noch einmal.")
        done = openbanking.complete_auth(db, text, _psu(request))
    except openbanking.EBError as error:
        return _error(409, "bank_refused", str(error))
    audit.subject(done["aspsp"])
    services.schedule_refresh()
    return {"name": done["aspsp"], "valid_until": done["valid_until"], "accounts": len(done["accounts"])}


@router.post("/api/v1/sync")
async def sync_start(request: Request):
    """Fetch new transactions from all banks that work without further input.

    With ``{"interactive": true}`` a bank may ask back (TAN and the like); the app answers above."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    interactive = isinstance(payload, dict) and payload.get("interactive") is True
    try:
        state = banksync.start(_view(device), psu=_psu(request), on_done=services.schedule_refresh,
                               interactive=interactive)
    except banksync.SyncRefused as refused:
        return _error(409, refused.code, refused.message)
    return JSONResponse(_sync_for(device, state), status_code=202)


@router.post("/api/v1/accounts")
async def create_account(request: Request):
    """Create a cash account, the only kind the app may add."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    try:
        account = mobile_write.create_cash_account(get_db(), payload, owner_person_id=device.person_id)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    services.schedule_refresh()
    return JSONResponse({"account": account}, status_code=201)


@router.put("/api/v1/accounts/{account_id}/value")
async def set_account_value(account_id: str, request: Request):
    """Enter today's value of a deposit or the remaining debt of a loan the person sees."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed = _transaction_id(account_id)
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    db = get_db()
    if parsed is None or not household.sees_account(db, device.person_id, parsed):
        return _not_found("Konto")
    try:
        _account, sentence = mobile_write.set_account_value(db, parsed, payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    audit.note(sentence, parsed)
    services.schedule_refresh()
    account = next((a for a in mobile_write.list_accounts(_view(device))["items"] if a["id"] == parsed), None)
    return {"account": account}


@router.get("/api/v1/categories")
def categories(request: Request):
    """Return the category tree for pickers and filters."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    result = mobile_write.list_categories(_view(device))
    if household.is_child(get_db(), device.person_id):
        # Names are needed to label the child's own transactions; the household's limits are not.
        for item in result["items"]:
            item["budget_cents"] = None
    return result


@router.get("/api/v1/contracts")
def contracts_list(request: Request):
    """Return allowlisted contract data without provider contact details."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_write.list_contracts(get_db(), view=_view(device))


@router.post("/api/v1/transactions")
async def create_transaction(request: Request):
    """Create one manual transaction; a repeated request id is not booked twice."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    account_id = payload.get("account_id")
    if (isinstance(account_id, int) and not isinstance(account_id, bool)
            and not household.sees_account(get_db(), device.person_id, account_id)):
        return _write_error(mobile_write.unknown_account())
    try:
        transaction, created = mobile_write.create_transaction(get_db(), payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    if created:
        row = get_db().one("SELECT * FROM transactions WHERE id = ?", (transaction["id"],))
        if row:
            audit.note(f"Buchung angelegt: {audit.tx_label(row)}", row["account_id"])
        services.schedule_refresh()
    else:
        audit.skip()  # dieselbe Anfrage noch einmal: nichts Neues
    return JSONResponse(
        {"transaction": transaction, "created": created},
        status_code=201 if created else 200,
    )


@router.patch("/api/v1/transactions/{tx_id}")
async def update_transaction(tx_id: str, request: Request):
    """Change category/note of any transaction or all fields of a manual one."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None:
        return _error(404, "not_found", "Buchung nicht gefunden.")
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    if not household.sees_transaction(get_db(), device.person_id, parsed_id):
        return _not_found("Buchung")
    before = get_db().one("SELECT * FROM transactions WHERE id = ?", (parsed_id,))
    try:
        transaction = mobile_write.update_transaction(get_db(), parsed_id, payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    _note_tx_change(before, payload)
    services.schedule_refresh()
    return {
        "learned": transaction.pop("learned", False),
        "also_changed": transaction.pop("also_changed", 0),
        "transaction": transaction,
    }


@router.delete("/api/v1/transactions/{tx_id}")
def delete_transaction(tx_id: str, request: Request):
    """Delete one manually created transaction. Bank transactions are refused."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None:
        return _error(404, "not_found", "Buchung nicht gefunden.")
    if not household.sees_transaction(get_db(), device.person_id, parsed_id):
        return _not_found("Buchung")
    before = get_db().one("SELECT * FROM transactions WHERE id = ?", (parsed_id,))
    try:
        mobile_write.delete_transaction(get_db(), parsed_id)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    if before:
        audit.note(f"Buchung gelöscht: {audit.tx_label(before)}", before["account_id"])
    services.schedule_refresh()
    return {"ok": True}


@router.get("/api/v1/transactions/{tx_id}/receipts")
def list_receipts(tx_id: str, request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None:
        return _error(404, "not_found", "Buchung nicht gefunden.")
    if not household.sees_transaction(get_db(), device.person_id, parsed_id):
        return _not_found("Buchung")
    try:
        return mobile_write.list_receipts(get_db(), parsed_id)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)


@router.post("/api/v1/transactions/{tx_id}/receipts")
async def add_receipt(tx_id: str, request: Request, filename: str = Query(default="", max_length=200)):
    """Attach one photo or PDF. The body is the raw file."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None:
        return _error(404, "not_found", "Buchung nicht gefunden.")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > papers.MAX_RECEIPT_BYTES:
        return _error(413, "too_large", "Die Datei ist größer als 10 MB.")
    # Stop reading once the limit is exceeded instead of buffering an arbitrarily large body.
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > papers.MAX_RECEIPT_BYTES:
            return _error(413, "too_large", "Die Datei ist größer als 10 MB.")
    if not household.sees_transaction(get_db(), device.person_id, parsed_id):
        return _not_found("Buchung")
    try:
        receipt = mobile_write.add_receipt(get_db(), parsed_id, filename, bytes(data))
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    return JSONResponse({"receipt": receipt}, status_code=201)


@router.get("/api/v1/receipts/{receipt_id}")
def receipt_file(receipt_id: str, request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(receipt_id)
    if parsed_id is None:
        return _error(404, "not_found", "Beleg nicht gefunden.")
    if not household.sees_receipt(get_db(), device.person_id, parsed_id):
        return _not_found("Beleg")
    try:
        row, path = mobile_write.receipt_file(get_db(), parsed_id)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    return FileResponse(path, media_type=row["mime"], filename=row["filename"], content_disposition_type="inline",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/api/v1/receipts/{receipt_id}")
def delete_receipt(receipt_id: str, request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(receipt_id)
    if parsed_id is None:
        return _error(404, "not_found", "Beleg nicht gefunden.")
    if not household.sees_receipt(get_db(), device.person_id, parsed_id):
        return _not_found("Beleg")
    try:
        mobile_write.delete_receipt(get_db(), parsed_id)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    return {"ok": True}


def _sharing_error(error: sharing.SharingError) -> JSONResponse:
    code = {400: "invalid_request", 404: "not_found"}.get(error.status, "not_possible")
    return _error(error.status, code, error.message)


def _own_payment(device, tx_id: int) -> bool:
    """Only the person whose account paid may share a transaction or take that back."""
    db = get_db()
    if device.person_id is None or not household.sees_transaction(db, device.person_id, tx_id):
        return False
    owner = db.scalar("SELECT a.owner_person_id FROM transactions AS t JOIN accounts AS a ON a.id = t.account_id "
                      "WHERE t.id = ?", (tx_id,))
    return owner is None or owner == device.person_id


@router.get("/api/v1/household/sharing")
def household_sharing(request: Request):
    """Shared expenses this person is part of, what is open, and settlements."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    if device.person_id is None:
        return {"balances": [], "items": [], "settlements": [], "open": [], "persons": []}
    db = get_db()
    return {
        **sharing.overview(db, device.person_id),
        "open": sharing.for_person(db, device.person_id),
        # Names only, to pick whom a settlement went to.
        "persons": [{"id": p["id"], "name": p["name"]} for p in household.list_persons(db)],
    }


@router.get("/api/v1/transactions/{tx_id}/share")
def transaction_share(tx_id: str, request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None or not household.sees_transaction(get_db(), device.person_id, parsed_id):
        return _not_found("Buchung")
    try:
        return sharing.get_share(get_db(), parsed_id)
    except sharing.SharingError as error:
        return _sharing_error(error)


@router.put("/api/v1/transactions/{tx_id}/share")
async def share_transaction(tx_id: str, request: Request):
    """Share an expense paid from the person's own account with the household."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None or not _own_payment(device, parsed_id):
        return _not_found("Buchung")
    payload = await _json_object(request)
    if payload is None or set(payload) - {"parts"}:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    try:
        result = sharing.set_share(get_db(), parsed_id, payload.get("parts"))
    except sharing.SharingError as error:
        return _sharing_error(error)
    _note_tx(parsed_id, "mit dem Haushalt geteilt")
    return result


@router.delete("/api/v1/transactions/{tx_id}/share")
def unshare_transaction(tx_id: str, request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None or not _own_payment(device, parsed_id):
        return _not_found("Buchung")
    try:
        result = sharing.clear_share(get_db(), parsed_id)
    except sharing.SharingError as error:
        return _sharing_error(error)
    _note_tx(parsed_id, "Teilen aufgehoben")
    return result


@router.post("/api/v1/household/settlements")
async def add_settlement(request: Request):
    """Record that this person has paid another one back."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None or set(payload) - {"to_person_id", "cents", "note"} or device.person_id is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    try:
        settlement = sharing.add_settlement(get_db(), {**payload, "from_person_id": device.person_id})
    except sharing.SharingError as error:
        return _sharing_error(error)
    audit.note(f"Ausgleichszahlung: {settlement.get('from')} an {settlement.get('to')}, {euro(settlement.get('cents'))}")
    return JSONResponse({"settlement": settlement}, status_code=201)


@router.get("/api/v1/networth")
def net_worth_history(request: Request):
    """Net worth at the end of the last months and today."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return {"history": ledger.net_worth_history(_view(device))}


@router.get("/api/v1/news")
def news(request: Request):
    """New transactions since this device last marked them as read."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_read.news(_view(device), device.id)


@router.post("/api/v1/news/seen")
def news_seen(request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    db = get_db()
    known = {row["id"] for row in db.query("SELECT id FROM mobile_devices WHERE revoked_at IS NULL")}
    mobile_read.mark_news_seen(_view(device), device.id, known)
    return {"ok": True}


@router.get("/api/v1/papers")
def papers_overview(request: Request, year: str | None = Query(default=None)):
    """Tax overview of one year and running warranties."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    if year not in (None, "") and not (year.isdigit() and len(year) == 4):
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    return mobile_read.papers_overview(_view(device), int(year) if year else None)


@router.get("/api/v1/triage")
def triage(request: Request, limit: str | None = Query(default=None)):
    """Transactions nobody has put into a real category yet, largest first."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    try:
        return mobile_read.triage(_view(device), limit=int(limit) if limit not in (None, "") else None)
    except (ValueError, mobile_read.MobileQueryError):
        return _error(400, "invalid_request", "Ungültige Anfrage.")


@router.get("/api/v1/budgets/suggestions")
def budget_suggestions(request: Request):
    """Budgets derived from the spending of the last full months."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return analytics.budget_suggestions(_view(device))


# --- Hinweise, geplante Ausgaben, erwartete Eingänge -----------------------------------------
# Abhaken geht nur für, was die Person sieht: Die Kennung muss in ihrer eigenen Übersicht stehen.

def _visible_open(device, kind: str, item_id: str):
    parsed = _transaction_id(item_id)
    if parsed is None:
        return None
    view = _view(device)
    items = planned.overview(view)["open"] if kind == "planned" else expected.overview(view)["open"]
    return next((i for i in items if i["id"] == parsed), None)


def _plan_error(error) -> JSONResponse:
    code = {400: "invalid_request", 404: "not_found", 409: "not_possible"}.get(error.status, "not_possible")
    return _error(error.status, code, error.message)


@router.post("/api/v1/alerts/ack")
async def acknowledge_alert(request: Request):
    """Mark an anomaly the person can see as checked; it no longer shows."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None or set(payload) != {"key"} or not isinstance(payload["key"], str):
        return _error(400, "invalid_request", "Erwartet wird genau das Feld key.")
    seen = {a["key"]: a for a in anomalies.alerts(_view(device))}
    if payload["key"] not in seen:
        return _not_found("Hinweis")
    anomalies.acknowledge(get_db(), payload["key"])
    audit.subject(seen[payload["key"]]["title"])
    services.schedule_refresh()
    return {"ok": True}


@router.post("/api/v1/planned")
async def create_planned(request: Request):
    """Plan a one-off expense on an account the person sees."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None or set(payload) - {"label", "cents", "due_date", "account_id", "note"}:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    account_id = payload.get("account_id")
    if (not isinstance(account_id, int) or isinstance(account_id, bool)
            or not household.sees_account(get_db(), device.person_id, account_id)):
        return _not_found("Konto")
    try:
        item = planned.create(get_db(), payload)
    except planned.PlannedError as error:
        return _plan_error(error)
    audit.subject(item["label"], item["account_id"])
    services.schedule_refresh()
    return JSONResponse({"planned": mobile_read.plans(_view(device))["planned"]}, status_code=201)


@router.post("/api/v1/planned/{item_id}/{action}")
def settle_planned(item_id: str, action: str, request: Request):
    """Tick a planned expense off as paid, or drop it."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    if action not in ("paid", "drop"):
        return _not_found("Aktion")
    item = _visible_open(device, "planned", item_id)
    if item is None:
        return _not_found("Geplante Ausgabe")
    try:
        (planned.close if action == "paid" else planned.drop)(get_db(), item["id"])
    except planned.PlannedError as error:
        return _plan_error(error)
    audit.note(f"Geplante Ausgabe {'abgehakt' if action == 'paid' else 'gestrichen'}: {item['label']}", item["account_id"])
    services.schedule_refresh()
    return {"ok": True}


@router.post("/api/v1/expected")
async def create_expected(request: Request):
    """Note that money comes back for an expense the person sees."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None or set(payload) - {"tx_id", "cents", "due_date", "note"}:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    tx_id = payload.get("tx_id")
    if (not isinstance(tx_id, int) or isinstance(tx_id, bool)
            or not household.sees_transaction(get_db(), device.person_id, tx_id)):
        return _not_found("Buchung")
    try:
        item = expected.create(get_db(), payload)
    except expected.ExpectedError as error:
        return _plan_error(error)
    audit.subject(item["label"], item["account_id"])
    services.schedule_refresh()
    return JSONResponse({"expected": mobile_read.plans(_view(device))["expected"]}, status_code=201)


@router.post("/api/v1/expected/{item_id}/{action}")
def settle_expected(item_id: str, action: str, request: Request):
    """Tick an expected income off as received, or drop it."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    if action not in ("received", "drop"):
        return _not_found("Aktion")
    item = _visible_open(device, "expected", item_id)
    if item is None:
        return _not_found("Erwarteter Eingang")
    try:
        (expected.close if action == "received" else expected.drop)(get_db(), item["id"])
    except expected.ExpectedError as error:
        return _plan_error(error)
    audit.note(f"Erwarteten Eingang {'abgehakt' if action == 'received' else 'abgelegt'}: {item['label']}", item["account_id"])
    services.schedule_refresh()
    return {"ok": True}


# --- Projekte und Kredite ---------------------------------------------------------------------
# Projektnamen sieht der ganze Haushalt; Buchungen und Summen nur aus den Konten, die die Person sieht.

def _project_item(p: dict) -> dict:
    return {"id": int(p["id"]), "name": p["name"], "note": p.get("note"), "budget_cents": p.get("budget_cents"),
            "left_cents": p.get("left_cents"), "archived": bool(p.get("archived")), "cost_cents": int(p["cost_cents"]),
            "spent_cents": int(p["spent_cents"]), "back_cents": int(p["back_cents"]), "count": int(p["count"]),
            "first": p.get("first"), "last": p.get("last")}


@router.get("/api/v1/projects")
def list_projects(request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return {"items": [_project_item(p) for p in projects.overview(_view(device))["items"]]}


@router.get("/api/v1/projects/{project_id}")
def project_detail(project_id: str, request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed = _transaction_id(project_id)
    if parsed is None:
        return _not_found("Projekt")
    try:
        p = projects.detail(_view(device), parsed)
    except projects.ProjectError:
        return _not_found("Projekt")
    return {**_project_item(p),
            "categories": [{"name": c["name"], "cents": int(c["cents"])} for c in p["categories"]],
            "months": [{"month": m["month"], "cents": int(m["cents"])} for m in p["months"]],
            "transactions": [{"id": int(t["id"]), "booking_date": t["booking_date"], "amount_cents": int(t["amount_cents"]),
                              "counterparty": t["counterparty"] or t["purpose"], "category": t["category_name"],
                              "account": t["account_name"], "transfer": bool(t["is_transfer"])}
                             for t in p["transactions"][:100]]}


@router.get("/api/v1/transactions/{tx_id}/project")
def transaction_project(tx_id: str, request: Request):
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed = _transaction_id(tx_id)
    if parsed is None or not household.sees_transaction(get_db(), device.person_id, parsed):
        return _not_found("Buchung")
    current = get_db().scalar("SELECT project_id FROM project_tx WHERE tx_id = ?", (parsed,))
    options_ = [{"id": int(p["id"]), "name": p["name"]} for p in projects.overview(get_db())["items"]
                if not p["archived"] or p["id"] == current]
    return {"project_id": current, "projects": options_}


@router.put("/api/v1/transactions/{tx_id}/project")
async def set_transaction_project(tx_id: str, request: Request):
    """Put a transaction the person sees into a project, or take it out (null)."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed = _transaction_id(tx_id)
    if parsed is None or not household.sees_transaction(get_db(), device.person_id, parsed):
        return _not_found("Buchung")
    payload = await _json_object(request)
    if payload is None or set(payload) != {"project_id"}:
        return _error(400, "invalid_request", "Erwartet wird genau das Feld project_id.")
    db = get_db()
    before = db.scalar("SELECT project_id FROM project_tx WHERE tx_id = ?", (parsed,))
    try:
        projects.set_for(db, parsed, payload["project_id"])
    except projects.ProjectError as error:
        return _plan_error(error)
    if payload["project_id"] == before:
        audit.skip()
    else:
        row = db.one("SELECT * FROM transactions WHERE id = ?", (parsed,))
        name = db.scalar("SELECT name FROM projects WHERE id = ?", (payload["project_id"],)) if payload["project_id"] else None
        audit.note(f"{audit.tx_label(row)}: " + (f"Projekt „{name}“" if name else "aus dem Projekt genommen"), row["account_id"])
    return {"project_id": payload["project_id"]}


# Eigene Budgets einer anderen Person stehen nicht im Protokoll am Handy.
_OWN_BUDGET_ROUTES = ("PUT /api/v1/budgets/own/{category_id}", "PUT /api/persons/{pid}/budgets/{cid}")


@router.get("/api/v1/changes")
def list_changes(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    """Who changed what, newest first: only entries about accounts the person sees or about the whole household."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    view = _view(device)
    where = "WHERE NOT (route IN (?, ?) AND COALESCE(person_id, -1) != ?)"
    params = (*_OWN_BUDGET_ROUTES, device.person_id if device.person_id is not None else -1)
    rows = view.query(f"SELECT at, actor, actor_kind, text FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*params, limit, offset))
    total = view.scalar(f"SELECT COUNT(*) FROM audit_log {where}", params)
    return {"items": [{"at": r["at"], "actor": r["actor"], "phone": r["actor_kind"] == "phone", "text": r["text"]}
                      for r in rows], "total": int(total or 0)}


@router.get("/api/v1/accounts/{account_id}/loan")
def loan_plan(account_id: str, request: Request, extra_cents: int = Query(default=0)):
    """Repayment plan of a loan the person sees; with extra_cents, the effect of a special repayment today."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed = _transaction_id(account_id)
    if parsed is None or not household.sees_account(get_db(), device.person_id, parsed):
        return _not_found("Konto")
    try:
        plan = loans.overview(get_db(), parsed, extra_cents)
    except loans.LoanError as error:
        return _plan_error(error)
    plan.pop("account_id", None)
    return plan


@router.put("/api/v1/budgets/{category_id}")
async def set_budget(category_id: str, request: Request):
    """Set the monthly budget of an expense category; null removes it."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(category_id)
    if parsed_id is None:
        return _error(404, "not_found", "Kategorie nicht gefunden.")
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    old = get_db().scalar("SELECT budget_cents FROM categories WHERE id = ?", (parsed_id,))
    try:
        budget = mobile_write.set_budget(get_db(), parsed_id, payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    new = budget["limit_cents"]
    if new == old:
        audit.skip()
    elif new is None:
        audit.note(f"Budget „{budget['name']}“ entfernt (vorher {euro(old)})")
    else:
        audit.note(f"Budget „{budget['name']}“: {euro(new)}" + (f" statt {euro(old)}" if old else ""))
    services.schedule_refresh()
    return {"budget": budget}


@router.put("/api/v1/budgets/own/{category_id}")
async def set_own_budget(category_id: str, request: Request):
    """Set or remove a budget that only counts this person's own accounts."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(category_id)
    if parsed_id is None:
        return _not_found("Kategorie")
    payload = await _json_object(request)
    if payload is None or set(payload) != {"limit_cents"}:
        return _error(400, "invalid_request", "Erwartet wird genau das Feld limit_cents.")
    try:
        budget = household.set_own_budget(get_db(), device.person_id, parsed_id, payload["limit_cents"])
    except household.HouseholdError as error:
        code = {400: "invalid_request", 404: "not_found"}.get(error.status, "not_possible")
        return _error(error.status, code, error.message)
    audit.note(f"Eigenes Budget für „{budget['name']}“: " + (euro(budget["limit_cents"]) if budget["limit_cents"] else "entfernt"))
    services.schedule_refresh()
    return {"budget": budget}


@router.patch("/api/v1/contracts/{key:path}")
async def update_contract(key: str, request: Request):
    """Confirm, ignore or cancel a contract, or acknowledge a price change."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    if not household.sees_contract(get_db(), device.person_id, key):
        return _not_found("Vertrag")
    try:
        contract = mobile_write.update_contract(get_db(), key, payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    services.schedule_refresh()
    return {"contract": contract}


@router.post("/api/v1/contracts/{key:path}/letter")
async def contract_letter(key: str, request: Request):
    """Build the cancellation letter; nothing is stored or sent."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    if not household.sees_contract(get_db(), device.person_id, key):
        return _not_found("Vertrag")
    try:
        return mobile_write.contract_letter(get_db(), key, payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
