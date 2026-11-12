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
from fastapi.responses import JSONResponse, Response

from . import mobile_read, mobile_write, options, services
from .db import get_db
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
)
INGRESS_IP = "172.30.32.2"
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
        return _auth_service().authenticate_access_token(token)
    except InvalidCredential:
        return _error(
            401,
            "unauthorized",
            "Anmeldung erforderlich.",
            headers={"WWW-Authenticate": "Bearer"},
        )


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

    try:
        pairing = _auth_service().create_pairing()
    except PairingLimitReached:
        return _error(
            429,
            "rate_limited",
            "Zu viele aktive Kopplungsanfragen.",
            headers={"Retry-After": "300"},
        )

    response = {**pairing, "server_url": server_url}
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
    return {
        "device": {"id": device.id, "name": device.name},
        "server": {"name": "Kassensturz", "version": options.VERSION, "storage": "local"},
        "capabilities": list(CAPABILITIES),
    }


@router.get("/api/v1/overview")
def overview(request: Request):
    """Return the allowlisted financial overview for the authenticated device."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_read.get_overview(get_db())


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
):
    """Return a paginated and allowlisted transaction list."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    try:
        return mobile_read.list_transactions(
            get_db(),
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
def stats(request: Request, month: str | None = Query(default=None)):
    """Return category spending, monthly totals and the balance curve."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    try:
        return mobile_read.get_stats(get_db(), month=month)
    except mobile_read.MobileQueryError:
        return _error(400, "invalid_query", "Ungültiger Monat.")


@router.get("/api/v1/accounts")
def accounts(request: Request):
    """Return active accounts with balances and whether manual entries are allowed."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_write.list_accounts(get_db())


@router.get("/api/v1/categories")
def categories(request: Request):
    """Return the category tree for pickers and filters."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_write.list_categories(get_db())


@router.get("/api/v1/contracts")
def contracts_list(request: Request):
    """Return allowlisted contract data without provider contact details."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_write.list_contracts(get_db())


@router.post("/api/v1/transactions")
async def create_transaction(request: Request):
    """Create one manual transaction; a repeated request id is not booked twice."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    payload = await _json_object(request)
    if payload is None:
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    try:
        transaction, created = mobile_write.create_transaction(get_db(), payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    if created:
        services.schedule_refresh()
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
    try:
        transaction = mobile_write.update_transaction(get_db(), parsed_id, payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    services.schedule_refresh()
    return {"transaction": transaction}


@router.delete("/api/v1/transactions/{tx_id}")
def delete_transaction(tx_id: str, request: Request):
    """Delete one manually created transaction. Bank transactions are refused."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None:
        return _error(404, "not_found", "Buchung nicht gefunden.")
    try:
        mobile_write.delete_transaction(get_db(), parsed_id)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    services.schedule_refresh()
    return {"ok": True}


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
    try:
        budget = mobile_write.set_budget(get_db(), parsed_id, payload)
    except mobile_write.MobileWriteError as error:
        return _write_error(error)
    services.schedule_refresh()
    return {"budget": budget}
