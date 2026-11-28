"""HTTP-Routen der versionierten, per Gerät angemeldeten API für die Handy-App.

Verwaltungsrouten für Kopplung und Geräte sind auf die Ingress-Gegenstelle von
Home Assistant oder Loopback beschränkt. Routen der Handy-App verlangen gültige
Gerätezugangsdaten. Transport und Netzzulassung setzt die Middleware in main durch.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Any
from urllib.parse import urlsplit

import qrcode
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from qrcode.image.svg import SvgPathImage

from . import (
    analytics,
    anomalies,
    audit,
    banksync,
    charging,
    expected,
    household,
    ledger,
    loans,
    mobile_read,
    mobile_write,
    openbanking,
    options,
    papers,
    planned,
    projects,
    report,
    services,
    sharing,
)
from .db import get_db
from .mobile_auth import (
    InvalidCredential,
    MobileAuthService,
    PairingLimitReached,
    PairingRejected,
)
from .mobile_security import address_in_networks, parse_trusted_proxy_networks, socket_peer
from .util import euro

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
    # Ladevorgänge aus Ladecockpit an Buchungen und in der Auswertung
    "charging",
    # Jahresrückblick mit Vergleich zum Vorjahr
    "year",
    # Monatsbericht und Jahresrückblick als PDF
    "report",
)
# Was das Handy eines Kindes bekommt: sein eigenes Konto lesen, nichts, was schreibt.
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
    """Ein eigenständiges SVG-QR-Bild ohne fremden Dienst erzeugen."""
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
    """Eine identifizierte, nur für Admins geltende HA-Ingress-Sitzung oder lokalen Zugriff verlangen."""
    # Eigenständiger Betrieb: Die Middleware hat Benutzername und Passwort schon geprüft und
    # merkt das an der Anfrage selbst vor; von außen lässt sich dieser Zustand nicht setzen.
    if getattr(request.state, "web_login_user", None):
        return True
    peer = socket_peer(request)
    # Ein vertrauenswürdiger Reverse-Proxy kann sich selbst über Loopback verbinden. Eine über das
    # Tailnet weitergeleitete Anfrage nicht für eine lokale Admin-Sitzung von HA halten.
    if address_in_networks(peer, TRUSTED_PROXY_NETWORKS):
        return False
    if peer is None:
        return False
    if peer.compressed == INGRESS_IP:
        # Der Supervisor entfernt nicht vertrauenswürdige Kopien dieser Header und setzt
        # X-Remote-User-Id für die angemeldete Ingress-Sitzung. Das Add-on deklariert
        # außerdem panel_admin: true, sodass nur Admins von HA eine bekommen.
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
    """Was dieses Gerät lesen darf: die Konten seiner Person und die gemeinsamen."""
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
    # Das Handy eines Kindes liest nur. Abmelden und Neuigkeiten als gesehen markieren bleiben möglich.
    if (request.method.upper() != "GET" and request.url.path not in READ_ONLY_ALLOWED
            and household.is_child(get_db(), device.person_id)):
        return _error(403, "read_only", "Mit diesem Handy lässt sich nichts ändern.")
    audit.set_device(get_db(), device)
    return device


@router.post("/api/mobile/pairings")
async def create_pairing(request: Request):
    """Ein einmaliges Kopplungsgeheimnis aus der vertrauenswürdigen lokalen Verwaltung erzeugen."""
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

    # Das ist die einzige Antwort, die das rohe Kopplungsgeheimnis enthält.
    return JSONResponse(
        response,
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/mobile/devices")
def list_devices(request: Request):
    """Nur Metadaten der Geräte auflisten; nie Token-Hashes oder Zugangsdaten preisgeben."""
    if not _local_admin_allowed(request):
        return _error(403, "forbidden", "Nur lokal über die Administration erlaubt.")
    return {"items": _auth_service().list_devices()}


@router.delete("/api/mobile/devices/{device_id}")
def revoke_device(device_id: str, request: Request):
    """Ein Gerät aus der vertrauenswürdigen lokalen Verwaltung widerrufen."""
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
    """Ein gekoppeltes Gerät einer Person des Haushalts zuordnen oder niemandem."""
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
    """Ein einmaliges Kopplungsgeheimnis einlösen und Gerätezugangsdaten ausgeben."""
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
    """Das Refresh-Token rotieren und ein neues Paar aus Access- und Refresh-Token ausgeben."""
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
    """Alle Zugangsdaten des angemeldeten Geräts widerrufen."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    _auth_service().revoke_device(device.id)
    return {"ok": True}


@router.get("/api/v1/me")
def me(request: Request):
    """Das angemeldete Gerät und unbedenkliche Fähigkeiten des Servers zurückgeben."""
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
    """Die Finanzübersicht mit erlaubten Feldern für das angemeldete Gerät zurückgeben."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    result = mobile_read.get_overview(get_db(), view=_view(device))
    result["household"] = household.profile(get_db(), device.person_id)
    result["household"]["balances"] = sharing.for_person(get_db(), device.person_id)
    # Budgets, die nur die eigenen Konten dieser Person zählen; "budgets" sind die des Haushalts.
    result["own_budgets"] = mobile_read.budget_items(household.own_budgets(get_db(), device.person_id))
    if result["household"]["read_only"]:
        # Ein Kind sieht nur sein eigenes Geld: was der Haushalt gegen seine Budgets ausgibt, bleibt bei den Erwachsenen.
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
    """Ausgaben nach Kategorie, Monatssummen und Saldoverlauf zurückgeben."""
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


@router.get("/api/v1/year")
def year_review(request: Request, year: str | None = Query(default=None), part: str | None = Query(default=None)):
    """Den Jahresrückblick zurückgeben, verglichen mit dem Vorjahr."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    view = _part_view(device, part)
    if view is None:
        return _error(400, "invalid_query", "Ungültiges Jahr oder ungültiger Teil.")
    try:
        return mobile_read.get_year(view, year)
    except mobile_read.MobileQueryError:
        return _error(400, "invalid_query", "Für dieses Jahr gibt es keinen Rückblick.")


@router.get("/api/v1/report/{kind}")
def report_pdf(request: Request, kind: str, period: str | None = Query(default=None),
               part: str | None = Query(default=None)):
    """Monatsbericht (period=JJJJ-MM) oder Jahresrückblick (period=JJJJ) als PDF, aus der Sicht des Geräts."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    if kind not in ("month", "year") or household.profile(get_db(), device.person_id)["read_only"]:
        return _error(404, "not_found", "Diesen Bericht gibt es nicht.")
    view = _part_view(device, part)
    if view is None:
        return _error(400, "invalid_query", "Ungültiger Teil.")
    today = date.today()
    try:
        if kind == "month":
            month = period or today.strftime("%Y-%m")
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                raise ValueError("month")
            data = report.month_pdf(view, month)
            name = f"kassensturz-{month}.pdf"
        else:
            year = period or str(today.year)
            if not re.fullmatch(r"\d{4}", year):
                raise ValueError("year")
            data = report.year_pdf(view, int(year))
            name = f"kassensturz-{year}.pdf"
    except ValueError:
        return _error(400, "invalid_query", "Für diesen Zeitraum gibt es keinen Bericht.")
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "no-store"})


@router.get("/api/v1/afford")
def afford(request: Request, amount_cents: int = Query(default=0)):
    """Sagen, was ein Kauf in dieser Höhe bis zum nächsten Gehalt bedeuten würde."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    try:
        return mobile_read.get_afford(_view(device), amount_cents)
    except mobile_read.MobileQueryError:
        return _error(400, "invalid_query", "Ungültiger Betrag.")


@router.get("/api/v1/accounts")
def accounts(request: Request):
    """Aktive Konten mit Salden zurückgeben und ob manuelle Einträge erlaubt sind."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return mobile_write.list_accounts(_view(device))


def _sync_for(device, state: dict) -> dict:
    """Der Abrufzustand für dieses Handy. Das Handy eines Kindes bekommt weder Verlängerungen noch die Rückfragen der Bank."""
    adult = not household.is_child(get_db(), device.person_id)
    out = _sync_public(state, renew=adult)
    out["question"] = banksync.question() if adult else None
    return out


def _sync_public(state: dict, renew: bool = False) -> dict:
    """Nur Banknamen und Zeiten. ``renew`` ist die lokale Nummer einer Einwilligung, die von
    diesem Handy aus verlängert werden darf; nie die Sitzung bei der Bank."""
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
    """Die Rückfrage der Bank bei einem laufenden Abruf beantworten: eine TAN, eine Auswahl oder „in der Banking-App freigegeben“.

    ``qid`` nennt die genaue Rückfrage; eine Antwort auf eine, die nicht mehr offen ist, wird abgelehnt."""
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
    """Das Verlängern einer ablaufenden Einwilligung beginnen. Gibt die zu öffnende Seite der Bank zurück; noch ändert sich nichts."""
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
    """Eine Verlängerung mit der Adresse abschließen, an die die Bank den Browser zurückgeschickt hat.

    Nur eine oben begonnene Verlängerung wird angenommen, nie eine neue Bank. Hier beginnt
    kein Abruf: Der nächste reguläre nutzt die neue Einwilligung."""
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
    """Neue Umsätze von allen Banken abrufen, die ohne weitere Eingabe funktionieren.

    Mit ``{"interactive": true}`` darf eine Bank zurückfragen (TAN und Ähnliches); die App antwortet oben."""
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
    """Ein Bargeldkonto anlegen, die einzige Art, die die App hinzufügen darf."""
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
    """Den heutigen Wert einer Geldanlage oder die Restschuld eines Kredits eintragen, den die Person sieht."""
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
    """Den Kategoriebaum für Auswahllisten und Filter zurückgeben."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    result = mobile_write.list_categories(_view(device))
    if household.is_child(get_db(), device.person_id):
        # Namen sind nötig, um die eigenen Umsätze des Kindes zu beschriften; die Grenzen des Haushalts nicht.
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
    """Einen manuellen Umsatz anlegen; eine wiederholte Anfrage-ID wird nicht doppelt gebucht."""
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
    """Kategorie/Notiz eines beliebigen Umsatzes oder alle Felder eines manuellen ändern."""
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
    """Einen von Hand angelegten Umsatz löschen. Bankumsätze werden abgelehnt."""
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
    """Ein Foto oder PDF anhängen. Der Inhalt der Anfrage ist die rohe Datei."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed_id = _transaction_id(tx_id)
    if parsed_id is None:
        return _error(404, "not_found", "Buchung nicht gefunden.")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > papers.MAX_RECEIPT_BYTES:
        return _error(413, "too_large", "Die Datei ist größer als 10 MB.")
    # Mit dem Lesen aufhören, sobald die Grenze überschritten ist, statt einen beliebig großen Inhalt zu puffern.
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
    """Nur die Person, deren Konto bezahlt hat, darf einen Umsatz teilen oder das zurücknehmen."""
    db = get_db()
    if device.person_id is None or not household.sees_transaction(db, device.person_id, tx_id):
        return False
    owner = db.scalar("SELECT a.owner_person_id FROM transactions AS t JOIN accounts AS a ON a.id = t.account_id "
                      "WHERE t.id = ?", (tx_id,))
    return owner is None or owner == device.person_id


@router.get("/api/v1/household/sharing")
def household_sharing(request: Request):
    """Geteilte Ausgaben, an denen diese Person beteiligt ist, was offen ist, und Ausgleiche."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    if device.person_id is None:
        return {"balances": [], "items": [], "settlements": [], "open": [], "persons": []}
    db = get_db()
    return {
        **sharing.overview(db, device.person_id),
        "open": sharing.for_person(db, device.person_id),
        # Nur Namen, um auszuwählen, an wen ein Ausgleich ging.
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
    """Eine vom eigenen Konto der Person bezahlte Ausgabe mit dem Haushalt teilen."""
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
    """Festhalten, dass diese Person einer anderen etwas zurückgezahlt hat."""
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
    """Vermögen am Ende der letzten Monate und heute."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    return {"history": ledger.net_worth_history(_view(device))}


@router.get("/api/v1/news")
def news(request: Request):
    """Neue Umsätze, seit dieses Gerät sie zuletzt als gelesen markiert hat."""
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
    """Steuerübersicht eines Jahres und laufende Garantien."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    if year not in (None, "") and not (year.isdigit() and len(year) == 4):
        return _error(400, "invalid_request", "Ungültige Anfrage.")
    return mobile_read.papers_overview(_view(device), int(year) if year else None)


@router.get("/api/v1/triage")
def triage(request: Request, limit: str | None = Query(default=None)):
    """Umsätze, die noch niemand in eine echte Kategorie gelegt hat, die größten zuerst."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    try:
        return mobile_read.triage(_view(device), limit=int(limit) if limit not in (None, "") else None)
    except (ValueError, mobile_read.MobileQueryError):
        return _error(400, "invalid_request", "Ungültige Anfrage.")


@router.get("/api/v1/budgets/suggestions")
def budget_suggestions(request: Request):
    """Aus den Ausgaben der letzten vollen Monate abgeleitete Budgets."""
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
    """Eine Auffälligkeit, die die Person sehen kann, als geprüft markieren; sie erscheint nicht mehr."""
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
    """Eine einmalige Ausgabe auf einem Konto planen, das die Person sieht."""
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
    """Eine geplante Ausgabe als bezahlt abhaken oder streichen."""
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
    """Festhalten, dass für eine Ausgabe, die die Person sieht, Geld zurückkommt."""
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
    """Eine erwartete Einnahme als erhalten abhaken oder streichen."""
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


def _charge_item(c: dict) -> dict:
    return {"started": c["started"], "site": c["site"], "network": c["network"], "kwh": c["kwh"],
            "total_cents": c["total_cents"], "idle_cents": c["idle_cents"],
            "price_per_kwh_cents": c["price_per_kwh_cents"]}


@router.get("/api/v1/charging")
def charging_months(request: Request):
    """Laden je Monat aus Ladecockpit, soweit diese Person die Buchungen sieht."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    data = charging.summary(_view(device))
    return {"months": [{k: m[k] for k in ("month", "sessions", "kwh", "total_cents", "idle_cents", "price_per_kwh_cents")}
                       for m in data["months"]],
            "count": data["count"], "unlinked_count": data["unlinked_count"]}


@router.get("/api/v1/transactions/{tx_id}/charging")
def transaction_charging(tx_id: str, request: Request):
    """Die Ladung, die eine Buchung bezahlt hat, oder null."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed = _transaction_id(tx_id)
    if parsed is None or not household.sees_transaction(get_db(), device.person_id, parsed):
        return _not_found("Buchung")
    found = charging.for_transactions(get_db(), [parsed]).get(parsed)
    return {"charging": _charge_item(found) if found else None}


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
    """Einen Umsatz, den die Person sieht, einem Projekt zuordnen oder herausnehmen (null)."""
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
    """Wer was geändert hat, das Neueste zuerst: nur Einträge zu Konten, die die Person sieht, oder zum ganzen Haushalt."""
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
    """Tilgungsplan eines Kredits, den die Person sieht; mit extra_cents die Wirkung einer Sondertilgung heute."""
    device = _authenticated_device(request)
    if isinstance(device, Response):
        return device
    parsed = _transaction_id(account_id)
    if parsed is None or not household.sees_account(get_db(), device.person_id, parsed):
        return _not_found("Konto")
    try:
        plan = loans.overview(get_db(), parsed, extra_cents, payments_db=_view(device))
    except loans.LoanError as error:
        return _plan_error(error)
    plan.pop("account_id", None)
    return plan


@router.put("/api/v1/budgets/{category_id}")
async def set_budget(category_id: str, request: Request):
    """Das Monatsbudget einer Ausgabenkategorie setzen; null entfernt es."""
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
    """Ein Budget setzen oder entfernen, das nur die eigenen Konten dieser Person zählt."""
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
    """Einen Vertrag bestätigen, ignorieren oder kündigen, oder eine Preisänderung zur Kenntnis nehmen."""
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
    """Das Kündigungsschreiben erstellen; nichts wird gespeichert oder gesendet."""
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
