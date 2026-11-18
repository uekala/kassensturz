"""HTTP-Schnittstelle und Auslieferung der Oberfläche (über Home-Assistant-Ingress)."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import (audit, calendar_feed, categorize, inbox, options, routes_accounts, routes_banks, routes_categories,
               routes_contracts, routes_import, routes_overview, routes_settings, routes_transactions, services)
from .db import close_db, get_db
from .web import _err
from .mobile_api import router as mobile_api_router
from .mobile_security import (
    InMemoryRateLimiter,
    address_in_networks,
    effective_client_ip,
    parse_trusted_proxy_networks,
    request_is_https,
    request_rate_limit_key,
    socket_peer,
)

log = logging.getLogger("kassensturz")
STATIC = Path(__file__).parent / "static"
INGRESS_IP = "172.30.32.2"
# HA app options and standalone environment variables both support explicit
# proxy/client CIDR allowlists. Both values remain empty by default.
NETWORK_SECURITY_SETTINGS = options.network_security_settings()
TRUSTED_PROXY_NETWORKS = parse_trusted_proxy_networks(
    NETWORK_SECURITY_SETTINGS["trusted_proxies"]
)
MOBILE_CLIENT_NETWORKS = parse_trusted_proxy_networks(
    NETWORK_SECURITY_SETTINGS["mobile_client_networks"]
)
MOBILE_API_PREFIXES = ("/api/v1", "/api/mobile")

# Per-process network limits. The limiter fails closed when its bounded key
# table is full and must be replaced by shared storage before multi-worker use.
MOBILE_RATE_LIMITER = InMemoryRateLimiter(max_keys=4096)
MOBILE_RATE_LIMITS = {
    ("GET", "/api/v1/health"): ("health", 60, 60),
    ("POST", "/api/v1/pair"): ("pair", 10, 300),
    ("POST", "/api/v1/auth/refresh"): ("refresh", 30, 60),
    ("POST", "/api/v1/auth/logout"): ("logout", 20, 60),
    ("GET", "/api/v1/me"): ("me", 120, 60),
    ("GET", "/api/v1/overview"): ("overview", 120, 60),
    ("GET", "/api/v1/transactions"): ("transactions", 120, 60),
    ("POST", "/api/v1/transactions"): ("transaction-write", 60, 60),
    ("GET", "/api/v1/stats"): ("stats", 60, 60),
    ("GET", "/api/v1/afford"): ("afford", 60, 60),
    ("GET", "/api/v1/accounts"): ("accounts", 120, 60),
    ("POST", "/api/v1/accounts"): ("account-write", 10, 60),
    ("GET", "/api/v1/sync"): ("sync", 120, 60),
    ("GET", "/api/v1/triage"): ("transactions", 120, 60),
    ("GET", "/api/v1/news"): ("overview", 120, 60),
    ("GET", "/api/v1/networth"): ("stats", 60, 60),
    ("POST", "/api/v1/news/seen"): ("news-seen", 30, 60),
    ("GET", "/api/v1/papers"): ("stats", 60, 60),
    ("GET", "/api/v1/budgets/suggestions"): ("stats", 60, 60),
    ("POST", "/api/v1/sync"): ("sync-start", 6, 60),
    ("GET", "/api/v1/categories"): ("categories", 120, 60),
    ("GET", "/api/v1/contracts"): ("contracts", 60, 60),
    ("GET", "/api/v1/household/sharing"): ("stats", 60, 60),
    ("POST", "/api/v1/household/settlements"): ("transaction-write", 60, 60),
    ("POST", "/api/mobile/pairings"): ("pairing-create", 5, 900),
    ("GET", "/api/mobile/devices"): ("device-list", 60, 60),
}

@asynccontextmanager
async def lifespan(_app):
    db = get_db()
    categorize.ensure_categories(db)
    moved = categorize.upgrade(db)
    if moved:
        logging.getLogger("kassensturz").info("Neue Zuordnungsregeln: %d Buchungen neu zugeordnet", moved)
    inbox.ensure_folder()
    if not os.environ.get("KASSENSTURZ_NO_BACKGROUND"):
        services.start_background()
        services.schedule_refresh()
    try:
        yield
    finally:
        # Home Assistant stops the app for a cold backup (SIGTERM). Leave one
        # complete database file behind: checkpoint the WAL and close.
        close_db()
        logging.getLogger("kassensturz").info("Kassensturz beendet, Datenbank geschlossen")


app = FastAPI(title="Kassensturz", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
class _Static(StaticFiles):
    """Statische Dateien: jedes Mal beim Server nachfragen (ETag), damit nach einem Update kein altes Modul bleibt."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", _Static(directory=STATIC), name="static")
app.include_router(mobile_api_router)



@app.middleware("http")
async def audit_trail(request: Request, call_next):
    """Schreibt erfolgreiche Änderungen ins Protokoll, mit dem, der sie gemacht hat."""
    if request.method not in audit.WRITE_METHODS or not request.url.path.startswith("/api/"):
        return await call_next(request)
    holder, token = audit.begin(request)
    try:
        response = await call_next(request)
    finally:
        audit.end(token)
    route = request.scope.get("route")
    if response.status_code < 400 and route is not None:
        try:
            audit.finish(get_db(), holder, request.method, route.path)
        except Exception:  # noqa: BLE001 – das Protokoll darf keine Änderung scheitern lassen
            log.warning("Änderungsprotokoll nicht geschrieben", exc_info=True)
    return response


@app.middleware("http")
async def only_ingress(request: Request, call_next):
    client = request.client.host if request.client else ""

    # Der Zahlungskalender: Home Assistant Core holt ihn aus seinem internen Netz. Nur diese eine
    # Leseadresse, nur mit Schlüssel in der Adresse; alles andere bleibt Ingress und lokal vorbehalten.
    # Auf dem Green kommen Home Assistant Core und der Tailscale-Proxy von derselben Adresse (172.30.32.1).
    # Unterschied: Der Proxy setzt immer X-Forwarded-*; Core holt den Kalender ohne. Mit diesen Kopfzeilen,
    # also übers Tailnet, gibt es den Kalender nicht.
    if request.url.path.startswith("/calendar/"):
        if (request.method == "GET" and calendar_feed.peer_allowed(client)
                and not calendar_feed.forwarded(request.headers)):
            return await call_next(request)
        return JSONResponse({"detail": "Nicht erreichbar."}, status_code=403, headers={"Cache-Control": "no-store"})

    # Mobile namespaces require direct TLS or an HTTPS assertion from an
    # explicitly trusted proxy. Route registration does not publish a port;
    # the add-on port mapping remains disabled until an administrator opts in.
    is_mobile_api = request.url.path in MOBILE_API_PREFIXES or request.url.path.startswith(
        tuple(prefix + "/" for prefix in MOBILE_API_PREFIXES)
    )
    peer = request.client.host if request.client else ""
    existing_local_peer = peer in (INGRESS_IP, "127.0.0.1", "::1")
    is_local_admin_path = (
        request.url.path in ("/api/mobile/pairings", "/api/mobile/devices")
        or request.url.path.startswith("/api/mobile/devices/")
    )
    # The HA Ingress and loopback admin plane is already protected by the
    # trusted local boundary; TLS is terminated by HA in front of Ingress.
    # Native mobile traffic must always use direct TLS or a trusted HTTPS proxy.
    if (
        is_mobile_api
        and not request_is_https(request, TRUSTED_PROXY_NETWORKS)
        and not (is_local_admin_path and existing_local_peer)
    ):
        return JSONResponse(
            {"error": {"code": "https_required", "message": "HTTPS ist erforderlich."}},
            status_code=426,
            headers={"Cache-Control": "no-store"},
        )

    # Existing browser/API traffic remains restricted to Ingress and loopback.
    # Mobile namespaces additionally allow only explicitly configured private
    # client networks; an empty allowlist therefore keeps remote access closed.
    proxy_peer_allowed = address_in_networks(
        socket_peer(request),
        TRUSTED_PROXY_NETWORKS,
    )
    mobile_peer_allowed = is_mobile_api and (
        proxy_peer_allowed
        or address_in_networks(
            effective_client_ip(request, TRUSTED_PROXY_NETWORKS),
            MOBILE_CLIENT_NETWORKS,
        )
    )
    if not existing_local_peer and not mobile_peer_allowed:
        message = "Nur über Home Assistant oder ein freigegebenes privates Netz erreichbar."
        # "detail" stays for the existing web client; mobile clients read "error".
        body: dict = {"detail": message}
        if is_mobile_api:
            body["error"] = {"code": "network_not_allowed", "message": message}
        return JSONResponse(body, status_code=403, headers={"Cache-Control": "no-store"})

    if is_mobile_api:
        policy = MOBILE_RATE_LIMITS.get((request.method.upper(), request.url.path))
        if policy is None and request.method.upper() == "DELETE" and request.url.path.startswith(
            "/api/mobile/devices/"
        ):
            policy = ("device-revoke", 10, 300)
        if policy is None and request.url.path.startswith("/api/v1/transactions/") and request.url.path.endswith("/receipts"):
            policy = ("receipt-write", 30, 60) if request.method.upper() == "POST" else ("receipts", 120, 60)
        if policy is None and request.url.path.startswith("/api/v1/receipts/"):
            policy = ("receipt-write", 30, 60) if request.method.upper() == "DELETE" else ("receipts", 120, 60)
        if policy is None and request.method.upper() in ("PATCH", "DELETE", "PUT") and request.url.path.startswith(
            "/api/v1/transactions/"
        ):
            policy = ("transaction-write", 60, 60)
        if policy is None and request.method.upper() == "PUT" and request.url.path.startswith("/api/v1/budgets/"):
            policy = ("budget-write", 60, 60)
        if policy is None and request.method.upper() in ("PATCH", "POST") and request.url.path.startswith("/api/v1/contracts/"):
            policy = ("contract-write", 30, 60)
        if policy is not None:
            scope, limit, window_seconds = policy
            key = request_rate_limit_key(
                request,
                TRUSTED_PROXY_NETWORKS,
                scope=scope,
            )
            decision = MOBILE_RATE_LIMITER.hit(
                key,
                limit=limit,
                window_seconds=window_seconds,
            )
            if not decision.allowed:
                return JSONResponse(
                    {"error": {"code": "rate_limited", "message": "Zu viele Anfragen."}},
                    status_code=429,
                    headers={
                        "Retry-After": str(decision.retry_after),
                        "Cache-Control": "no-store",
                    },
                )

    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# Ohne Zeitplan-Durchlauf seit dieser Zeit gilt die App als hängend.
SCHEDULER_STALE_SECONDS = 900


@app.get("/calendar/{name}")
def calendar_ics(name: str):
    """Der Zahlungskalender als iCalendar-Datei, für „Remote Calendar“ in Home Assistant."""
    db = get_db()
    if not name.endswith(".ics") or not calendar_feed.matches(db, name[:-4]):
        return Response(status_code=404)
    return Response(calendar_feed.ics(calendar_feed.events(db)), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/calendar")
def calendar_state():
    db = get_db()
    value = calendar_feed.token(db)
    upcoming = calendar_feed.events(db)
    return {"enabled": bool(value), "url": calendar_feed.address(value), "count": len(upcoming),
            "next": [{"date": e["date"].isoformat(), "summary": e["summary"]} for e in upcoming[:6]]}


@app.post("/api/calendar")
def calendar_switch(body: dict = Body(...)):
    action = body.get("action")
    if action not in ("on", "renew", "off"):
        _err(400, "Unbekannte Aktion.")
    calendar_feed.switch(get_db(), action)
    audit.subject({"on": "eingeschaltet", "renew": "neue Adresse, die alte gilt nicht mehr", "off": "ausgeschaltet"}[action])
    return calendar_state()


@app.get("/healthz")
def healthz():
    """Für Watchdog und Healthcheck: nur lokal erreichbar, ohne Finanzdaten."""
    problems = []
    try:
        database = get_db()
        # Eine laufende Transaktion (z. B. ein großer Import) ist kein Fehler.
        if database.lock.acquire(timeout=2):
            try:
                database.conn.execute("SELECT 1").fetchone()
            finally:
                database.lock.release()
    except Exception:  # noqa: BLE001
        log.exception("Datenbank antwortet nicht")
        problems.append("database")
    if not os.environ.get("KASSENSTURZ_NO_BACKGROUND") and services.scheduler_age_seconds() > SCHEDULER_STALE_SECONDS:
        problems.append("scheduler")
    return JSONResponse(
        {"status": "error" if problems else "ok", "version": options.VERSION, "problems": problems},
        status_code=503 if problems else 200,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/")
def index():
    # Die Version in den Adressen von Skript und Stil zwingt den Browser nach einem Update zum Neuladen.
    page = (STATIC / "index.html").read_text(encoding="utf-8").replace("?v=0.3.22", f"?v={options.VERSION}")
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


# --- Routen der Bereiche, in der Reihenfolge, in der sie früher hier standen -----------------
app.include_router(routes_overview.router)
app.include_router(routes_transactions.router)
app.include_router(routes_categories.router)
app.include_router(routes_accounts.router)
app.include_router(routes_import.router)
app.include_router(routes_banks.router)
app.include_router(routes_contracts.router)
app.include_router(routes_settings.router)
