"""HTTP-Schnittstelle und Auslieferung der Oberfläche (über Home-Assistant-Ingress)."""
from __future__ import annotations

import csv
import io
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import (analytics, categorize, contracts, demo, fints_sync, ha, importers, inbox, ledger, letters, openbanking, options,
               secrets_store, services)
from .db import get_db, now_iso
from .mobile_security import (
    InMemoryRateLimiter,
    parse_trusted_proxy_networks,
    request_is_https,
    request_rate_limit_key,
)

log = logging.getLogger("kassensturz")
STATIC = Path(__file__).parent / "static"
INGRESS_IP = "172.30.32.2"
# Proxy addresses are trusted only when explicitly configured by an administrator.
TRUSTED_PROXY_NETWORKS = parse_trusted_proxy_networks(
    os.environ.get("KASSENSTURZ_TRUSTED_PROXIES")
)
MOBILE_API_PREFIXES = ("/api/v1", "/api/mobile")

# Per-process network limits. The limiter fails closed when its bounded key
# table is full and must be replaced by shared storage before multi-worker use.
MOBILE_RATE_LIMITER = InMemoryRateLimiter(max_keys=4096)
MOBILE_RATE_LIMITS = {
    ("POST", "/api/v1/pair"): ("pair", 10, 300),
    ("POST", "/api/v1/auth/refresh"): ("refresh", 30, 60),
    ("POST", "/api/v1/auth/logout"): ("logout", 20, 60),
    ("GET", "/api/v1/me"): ("me", 120, 60),
    ("GET", "/api/v1/overview"): ("overview", 120, 60),
    ("GET", "/api/v1/transactions"): ("transactions", 120, 60),
    ("POST", "/api/mobile/pairings"): ("pairing-create", 5, 900),
    ("GET", "/api/mobile/devices"): ("device-list", 60, 60),
}

@asynccontextmanager
async def lifespan(_app):
    db = get_db()
    categorize.ensure_categories(db)
    inbox.ensure_folder()
    if not os.environ.get("KASSENSTURZ_NO_BACKGROUND"):
        services.start_background()
        services.schedule_refresh()
    yield


app = FastAPI(title="Kassensturz", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_imports: dict[str, dict] = {}


@app.middleware("http")
async def only_ingress(request: Request, call_next):
    client = request.client.host if request.client else ""

    # Mobile namespaces require direct TLS or an HTTPS assertion from an
    # explicitly trusted proxy. The routes are not registered yet; this is a
    # fail-closed transport gate, not permission to expose a new listener.
    is_mobile_api = request.url.path == "/api/v1" or request.url.path.startswith(
        tuple(prefix + "/" for prefix in MOBILE_API_PREFIXES)
    )
    if is_mobile_api and not request_is_https(request, TRUSTED_PROXY_NETWORKS):
        return JSONResponse(
            {"error": {"code": "https_required", "message": "HTTPS ist erforderlich."}},
            status_code=426,
            headers={"Cache-Control": "no-store"},
        )

    # Development mode never bypasses the existing network boundary. Only
    # the Home Assistant Ingress peer and local loopback clients are accepted.
    if client not in (INGRESS_IP, "127.0.0.1", "::1"):
        return JSONResponse({"detail": "Nur über Home Assistant erreichbar."}, status_code=403)

    if is_mobile_api:
        policy = MOBILE_RATE_LIMITS.get((request.method.upper(), request.url.path))
        if policy is None and request.method.upper() == "DELETE" and request.url.path.startswith(
            "/api/mobile/devices/"
        ):
            policy = ("device-revoke", 10, 300)
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


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


def _err(status: int, text: str):
    raise HTTPException(status_code=status, detail=text)


def _changed() -> None:
    services.schedule_refresh()


# --- Status & Übersicht -------------------------------------------------------------

@app.get("/api/state")
def state():
    db = get_db()
    opts = options.load()
    return {
        "version": options.VERSION,
        "ha": ha.available(),
        "product_id": bool((opts.get("fints_product_id") or "").strip()),
        "accounts": db.scalar("SELECT COUNT(*) FROM accounts WHERE archived = 0"),
        "transactions": db.scalar("SELECT COUNT(*) FROM transactions"),
        "demo": bool(db.scalar("SELECT COUNT(*) FROM accounts WHERE demo = 1")),
        "uncategorized": db.scalar("SELECT COUNT(*) FROM transactions t JOIN categories c ON c.id = t.category_id "
                                   "WHERE c.builtin_key IN ('sonstiges', 'sonstige_einnahmen') AND t.category_locked = 0"),
    }


@app.get("/api/overview")
def overview():
    db = get_db()
    contracts.detect(db)
    s = services.build_summary(db)
    fc = s["forecast"]
    today = date.today()
    soon = [u for u in fc["upcoming"] if (date.fromisoformat(u["date"]) - today).days <= 14]
    cons = s["contracts"]
    return {
        "forecast": fc,
        "accounts": s["accounts"],
        "budgets": s["budgets"],
        "month": s["month"],
        "fixed_monthly_cents": s["fixed_monthly_cents"],
        "contract_count": s["contract_count"],
        "upcoming": soon,
        "alerts": services.alerts(db, s),
        "price_changes": sum(1 for c in cons if c.get("price_change_cents") and c["kind"] == "expense" and c["price_change_cents"] < 0
                             and c["status"] != "ignored"),
    }


# --- Buchungen ---------------------------------------------------------------------

@app.get("/api/transactions")
def transactions(q: str = "", account: int | None = None, category: int | None = None, month: str = "", kind: str = "",
                 contract: str = "", offset: int = 0, limit: int = 100):
    db = get_db()
    where = ["a.archived = 0"]
    params: list = []
    if q:
        where.append("(t.counterparty LIKE ? OR t.purpose LIKE ? OR t.note LIKE ? OR CAST(t.amount_cents AS TEXT) LIKE ?)")
        like = f"%{q}%"
        cents_like = q.replace(",", "").replace(".", "").replace("€", "").strip()
        params += [like, like, like, f"%{cents_like}%"]
    if account:
        where.append("t.account_id = ?")
        params.append(account)
    if category:
        where.append("(t.category_id = ? OR c.parent_id = ? OR t.id IN (SELECT tx_id FROM splits WHERE category_id = ?))")
        params += [category, category, category]
    if month:
        where.append("substr(t.booking_date, 1, 7) = ?")
        params.append(month)
    if contract:
        where.append("t.contract_key = ?")
        params.append(contract)
    if kind == "in":
        where.append("t.amount_cents > 0 AND t.is_transfer = 0")
    elif kind == "out":
        where.append("t.amount_cents < 0 AND t.is_transfer = 0")
    elif kind == "transfer":
        where.append("t.is_transfer = 1")
    elif kind == "uncat":
        where.append("c.builtin_key IN ('sonstiges', 'sonstige_einnahmen') AND t.category_locked = 0")
    sql_where = " AND ".join(where)
    base = (f"FROM transactions t JOIN accounts a ON a.id = t.account_id LEFT JOIN categories c ON c.id = t.category_id "
            f"WHERE {sql_where}")
    total = db.one(f"SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN t.amount_cents > 0 AND t.is_transfer = 0 THEN t.amount_cents END), 0) AS sin, "
                   f"COALESCE(SUM(CASE WHEN t.amount_cents < 0 AND t.is_transfer = 0 THEN t.amount_cents END), 0) AS sout {base}", tuple(params))
    items = db.query(
        f"SELECT t.*, a.name AS account_name, a.kind AS account_kind, c.name AS category_name, c.kind AS category_kind {base} "
        f"ORDER BY t.booking_date DESC, t.id DESC LIMIT ? OFFSET ?",
        (*params, max(1, min(limit, 500)), max(0, offset)),
    )
    if items:
        ids = [i["id"] for i in items]
        splits = db.query(f"SELECT s.*, c.name AS category_name FROM splits s LEFT JOIN categories c ON c.id = s.category_id "
                          f"WHERE s.tx_id IN ({','.join('?' * len(ids))})", tuple(ids))
        by = {}
        for sp in splits:
            by.setdefault(sp["tx_id"], []).append(sp)
        for i in items:
            i["splits"] = by.get(i["id"], [])
            i.pop("hash", None)
    return {"items": items, "total": total["n"], "sum_in": total["sin"], "sum_out": total["sout"]}


@app.patch("/api/transactions/{tx_id}")
def update_transaction(tx_id: int, body: dict = Body(...)):
    db = get_db()
    tx = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not tx:
        _err(404, "Buchung nicht gefunden.")
    data = {}
    if "note" in body:
        data["note"] = (body.get("note") or "").strip() or None
    changed = 0
    if body.get("category_id"):
        cat = db.one("SELECT * FROM categories WHERE id = ?", (body["category_id"],))
        if not cat:
            _err(400, "Kategorie unbekannt.")
        data.update({"category_id": cat["id"], "category_locked": 1, "is_transfer": 1 if cat["kind"] == "transfer" else 0,
                     "rule_ref": "manual"})
        rule = body.get("rule")
        if rule and (rule.get("pattern") or "").strip():
            db.insert("rules", {"pattern": rule["pattern"].strip(), "field": rule.get("field") or "any", "sign": rule.get("sign") or "any",
                                "category_id": cat["id"], "mark_transfer": 1 if cat["kind"] == "transfer" else 0, "priority": 100,
                                "enabled": 1, "created": now_iso()})
    db.update("transactions", "id", tx_id, data)
    if body.get("rule"):
        changed = categorize.recategorize(db)
    _changed()
    return {"ok": True, "recategorized": changed}


@app.post("/api/transactions/{tx_id}/reset")
def reset_transaction(tx_id: int):
    db = get_db()
    db.update("transactions", "id", tx_id, {"category_locked": 0})
    categorize.recategorize(db, [tx_id])
    _changed()
    return {"ok": True}


@app.put("/api/transactions/{tx_id}/splits")
def set_splits(tx_id: int, body: dict = Body(...)):
    db = get_db()
    tx = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not tx:
        _err(404, "Buchung nicht gefunden.")
    parts = body.get("splits") or []
    total = sum(int(p.get("amount_cents") or 0) for p in parts)
    if parts and (abs(total) > abs(tx["amount_cents"]) or any((int(p.get("amount_cents") or 0) * tx["amount_cents"]) <= 0 for p in parts)):
        _err(400, "Die Teilbeträge müssen das gleiche Vorzeichen haben und dürfen zusammen nicht größer als die Buchung sein.")
    with db.tx():
        db.execute("DELETE FROM splits WHERE tx_id = ?", (tx_id,))
        for p in parts:
            db.insert("splits", {"tx_id": tx_id, "amount_cents": int(p["amount_cents"]), "category_id": p.get("category_id"),
                                 "note": (p.get("note") or "").strip() or None})
    _changed()
    return {"ok": True}


@app.get("/api/transactions/{tx_id}/suggest-rule")
def suggest_rule(tx_id: int):
    db = get_db()
    tx = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not tx:
        _err(404, "Buchung nicht gefunden.")
    pattern = categorize.suggest_pattern(tx)
    count = 0
    if pattern:
        rx = categorize._compile(pattern)
        from .util import norm
        for r in db.query("SELECT counterparty, purpose FROM transactions"):
            if rx.search(norm(r["counterparty"])) or rx.search(norm(r["purpose"])):
                count += 1
    return {"pattern": pattern, "matches": count, "sign": "in" if tx["amount_cents"] > 0 else "out"}


# --- Kategorien, Budgets, Regeln ------------------------------------------------------

@app.get("/api/categories")
def categories():
    return get_db().query("SELECT * FROM categories ORDER BY sort, name")


@app.post("/api/categories")
def create_category(body: dict = Body(...)):
    db = get_db()
    name = (body.get("name") or "").strip()
    if not name:
        _err(400, "Name fehlt.")
    parent = body.get("parent_id")
    kind = body.get("kind") or "expense"
    if parent:
        p = db.one("SELECT kind, sort FROM categories WHERE id = ?", (parent,))
        kind = p["kind"] if p else kind
    sort = (db.scalar("SELECT MAX(sort) FROM categories") or 0) + 10
    cid = db.insert("categories", {"name": name[:60], "parent_id": parent, "kind": kind, "sort": sort})
    return db.one("SELECT * FROM categories WHERE id = ?", (cid,))


@app.patch("/api/categories/{cid}")
def update_category(cid: int, body: dict = Body(...)):
    db = get_db()
    data = {}
    if "name" in body and (body["name"] or "").strip():
        data["name"] = body["name"].strip()[:60]
    if "budget_cents" in body:
        b = body["budget_cents"]
        data["budget_cents"] = int(b) if b not in (None, "", 0) else None
    db.update("categories", "id", cid, data)
    _changed()
    return db.one("SELECT * FROM categories WHERE id = ?", (cid,))


@app.delete("/api/categories/{cid}")
def delete_category(cid: int):
    db = get_db()
    cat = db.one("SELECT * FROM categories WHERE id = ?", (cid,))
    if not cat:
        _err(404, "Kategorie nicht gefunden.")
    if cat["builtin_key"]:
        _err(400, "Eingebaute Kategorien lassen sich nur umbenennen.")
    fallback = cat["parent_id"] or db.scalar("SELECT id FROM categories WHERE builtin_key = 'sonstiges'")
    with db.tx():
        db.execute("UPDATE transactions SET category_id = ? WHERE category_id = ?", (fallback, cid))
        db.execute("UPDATE splits SET category_id = ? WHERE category_id = ?", (fallback, cid))
        db.execute("UPDATE rules SET category_id = ? WHERE category_id = ?", (fallback, cid))
        db.execute("UPDATE categories SET parent_id = ? WHERE parent_id = ?", (cat["parent_id"], cid))
        db.execute("DELETE FROM categories WHERE id = ?", (cid,))
    _changed()
    return {"ok": True}


@app.get("/api/budgets")
def get_budgets(month: str = ""):
    db = get_db()
    on = date.fromisoformat(month + "-15") if month else date.today()
    if on.year == date.today().year and on.month == date.today().month:
        on = date.today()
    else:
        from .util import month_end
        on = month_end(on)
    return {"budgets": analytics.budgets(db, on), "stats": analytics.month_stats(db, on.strftime("%Y-%m"))}


@app.get("/api/rules")
def rules():
    db = get_db()
    return db.query("SELECT r.*, c.name AS category_name FROM rules r LEFT JOIN categories c ON c.id = r.category_id ORDER BY r.priority, r.id")


@app.post("/api/rules")
def create_rule(body: dict = Body(...)):
    db = get_db()
    pattern = (body.get("pattern") or "").strip()
    if not pattern:
        _err(400, "Suchbegriff fehlt.")
    cat = db.one("SELECT * FROM categories WHERE id = ?", (body.get("category_id"),)) if body.get("category_id") else None
    rid = db.insert("rules", {"pattern": pattern, "field": body.get("field") or "any", "sign": body.get("sign") or "any",
                              "category_id": cat["id"] if cat else None,
                              "mark_transfer": 1 if (body.get("mark_transfer") or (cat and cat["kind"] == "transfer")) else 0,
                              "priority": int(body.get("priority") or 100), "enabled": 1, "created": now_iso()})
    n = categorize.recategorize(db)
    _changed()
    return {"id": rid, "recategorized": n}


@app.patch("/api/rules/{rid}")
def update_rule(rid: int, body: dict = Body(...)):
    db = get_db()
    data = {k: body[k] for k in ("pattern", "field", "sign", "category_id", "priority", "enabled", "mark_transfer") if k in body}
    db.update("rules", "id", rid, data)
    n = categorize.recategorize(db)
    _changed()
    return {"ok": True, "recategorized": n}


@app.delete("/api/rules/{rid}")
def delete_rule(rid: int):
    db = get_db()
    db.execute("DELETE FROM rules WHERE id = ?", (rid,))
    n = categorize.recategorize(db)
    _changed()
    return {"ok": True, "recategorized": n}


@app.post("/api/recategorize")
def recategorize_all():
    n = categorize.recategorize(get_db())
    _changed()
    return {"recategorized": n}


# --- Konten ----------------------------------------------------------------------------

ACCOUNT_FIELDS = ("name", "kind", "iban", "bank", "settlement_pattern", "in_forecast", "archived", "sort")


@app.get("/api/accounts")
def accounts():
    return ledger.accounts_with_balance(get_db(), include_archived=True)


@app.post("/api/accounts")
def create_account(body: dict = Body(...)):
    db = get_db()
    name = (body.get("name") or "").strip()
    if not name:
        _err(400, "Name fehlt.")
    data = {k: body.get(k) for k in ACCOUNT_FIELDS if k in body}
    data.update({"name": name[:60], "created": now_iso()})
    if data.get("iban"):
        data["iban"] = data["iban"].replace(" ", "").upper()
    aid = db.insert("accounts", data)
    categorize.recategorize(db)
    return db.one("SELECT * FROM accounts WHERE id = ?", (aid,))


@app.patch("/api/accounts/{aid}")
def update_account(aid: int, body: dict = Body(...)):
    db = get_db()
    data = {k: body[k] for k in ACCOUNT_FIELDS if k in body}
    if data.get("iban"):
        data["iban"] = data["iban"].replace(" ", "").upper()
    db.update("accounts", "id", aid, data)
    if {"settlement_pattern", "iban", "kind", "archived"} & set(data):
        categorize.recategorize(db)
    _changed()
    return {"ok": True}


@app.post("/api/accounts/{aid}/balance")
def set_balance(aid: int, body: dict = Body(...)):
    db = get_db()
    cents = body.get("balance_cents")
    if cents is None:
        _err(400, "Betrag fehlt.")
    ledger.set_balance_anchor(db, aid, int(cents), body.get("date") or date.today().isoformat())
    _changed()
    return {"ok": True}


@app.delete("/api/accounts/{aid}")
def delete_account(aid: int):
    db = get_db()
    ledger.delete_account(db, aid)
    categorize.recategorize(db)
    _changed()
    return {"ok": True}


# --- Datei-Import ------------------------------------------------------------------------

def _analysis_public(res: dict) -> dict:
    out = {k: v for k, v in res.items() if k != "rows"}
    out["preview"] = res["rows"][-8:][::-1]
    out["field_labels"] = importers.FIELD_LABELS
    return out


def _match_account(db, res: dict, signature: str | None) -> int | None:
    iban = (res.get("meta") or {}).get("iban")
    if iban:
        acc = db.one("SELECT id FROM accounts WHERE iban = ? AND archived = 0", (iban,))
        if acc:
            return acc["id"]
    if signature:
        prof = db.one("SELECT account_id FROM csv_profiles WHERE signature = ?", (signature,))
        if prof and db.one("SELECT id FROM accounts WHERE id = ?", (prof["account_id"],)):
            return prof["account_id"]
    return None


@app.post("/api/import/analyze")
async def import_analyze(file: UploadFile = File(...)):
    # Stop reading as soon as the upload limit is exceeded instead of first
    # allocating the complete untrusted upload in memory.
    data = await file.read(importers.MAX_IMPORT_BYTES + 1)
    if len(data) > importers.MAX_IMPORT_BYTES:
        _err(400, "Die Datei ist größer als 25 MB.")
    db = get_db()
    for tok in [t for t, v in _imports.items() if time.time() - v["created"] > 1800]:
        _imports.pop(tok, None)
    profile = None
    try:
        res = importers.analyze(data, file.filename or "")
        if res.get("signature"):
            prof = db.one("SELECT mapping FROM csv_profiles WHERE signature = ?", (res["signature"],))
            if prof:
                import json
                profile = json.loads(prof["mapping"])
                res = importers.analyze(data, file.filename or "", profile)
    except Exception as exc:  # noqa: BLE001
        log.exception("Import-Analyse fehlgeschlagen")
        _err(400, f"Die Datei ließ sich nicht lesen: {exc}")
    token = uuid.uuid4().hex
    _imports[token] = {"data": data, "filename": file.filename, "created": time.time()}
    out = _analysis_public(res)
    out.update({"token": token, "account_id": _match_account(db, res, res.get("signature")), "profile_used": bool(profile)})
    return out


@app.post("/api/import/remap")
def import_remap(body: dict = Body(...)):
    item = _imports.get(body.get("token") or "")
    if not item:
        _err(400, "Die Datei ist nicht mehr im Zwischenspeicher. Bitte erneut hochladen.")
    res = importers.analyze(item["data"], item["filename"] or "", body.get("mapping") or {})
    out = _analysis_public(res)
    out["token"] = body["token"]
    return out


@app.post("/api/import/commit")
def import_commit(body: dict = Body(...)):
    import json

    db = get_db()
    item = _imports.get(body.get("token") or "")
    if not item:
        _err(400, "Die Datei ist nicht mehr im Zwischenspeicher. Bitte erneut hochladen.")
    res = importers.analyze(item["data"], item["filename"] or "", body.get("mapping") or None)
    if not res.get("rows"):
        _err(400, res.get("error") or "Keine Buchungen in der Datei gefunden.")
    account_id = body.get("account_id")
    if not account_id:
        new = body.get("new_account") or {}
        name = (new.get("name") or res["suggest"]["name"]).strip()
        kind = new.get("kind") or res["suggest"]["kind"]
        account_id = db.insert("accounts", {
            "name": name[:60], "kind": kind, "iban": (new.get("iban") or res["meta"].get("iban") or None),
            "settlement_pattern": new.get("settlement_pattern", res["suggest"]["settlement"]) or None,
            "in_forecast": 0 if kind == "tagesgeld" else 1, "created": now_iso(),
        })
        categorize.recategorize(db)
    elif not db.one("SELECT id FROM accounts WHERE id = ?", (account_id,)):
        _err(400, "Konto nicht gefunden.")
    result = ledger.import_rows(db, int(account_id), res["rows"], "ordner" if item.get("inbox_file") else "datei", item["filename"],
                                res.get("meta"))
    if res.get("signature"):
        db.execute("INSERT INTO csv_profiles(signature, mapping, account_id, updated) VALUES(?, ?, ?, ?) "
                   "ON CONFLICT(signature) DO UPDATE SET mapping = excluded.mapping, account_id = excluded.account_id, updated = excluded.updated",
                   (res["signature"], json.dumps(res["mapping"]), int(account_id), now_iso()))
    _imports.pop(body["token"], None)
    if item.get("inbox_file"):
        try:
            _, path = inbox.read_file(item["inbox_file"])
            inbox.move_done(path)
        except FileNotFoundError:
            pass
        db.execute("DELETE FROM inbox WHERE filename = ?", (item["inbox_file"],))
    contracts.detect(db)
    services.schedule_refresh()
    acc = db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
    return {"added": result["added"], "skipped": result["skipped"], "account_id": account_id, "balance_known": acc["balance_date"] is not None}


# --- FinTS ---------------------------------------------------------------------------------

@app.get("/api/banks")
def banks():
    return fints_sync.BANK_PRESETS


@app.get("/api/connections")
def connections():
    db = get_db()
    out = []
    for c in db.query("SELECT id, name, blz, login, customer_id, server, tan_mechanism, tan_medium, history_days, last_sync, last_status "
                      "FROM connections ORDER BY id"):
        c["has_pin"] = secrets_store.has_pin(c["id"])
        c["accounts"] = db.query("SELECT id, name FROM accounts WHERE connection_id = ?", (c["id"],))
        out.append(c)
    return out


@app.post("/api/connections")
def create_connection(body: dict = Body(...)):
    db = get_db()
    need = {"name": "Name", "blz": "Bankleitzahl", "login": "Anmeldename", "server": "FinTS-Server"}
    for k, label in need.items():
        if not (body.get(k) or "").strip():
            _err(400, f"{label} fehlt.")
    cid = db.insert("connections", {
        "name": body["name"].strip()[:60], "blz": body["blz"].strip().replace(" ", ""), "login": body["login"].strip(),
        "customer_id": (body.get("customer_id") or "").strip() or None, "server": body["server"].strip(),
        "history_days": int(body.get("history_days") or 365), "created": now_iso(),
    })
    return {"id": cid}


@app.patch("/api/connections/{cid}")
def update_connection(cid: int, body: dict = Body(...)):
    db = get_db()
    data = {k: body[k] for k in ("name", "blz", "login", "customer_id", "server", "history_days") if k in body}
    if {"blz", "login", "customer_id", "server"} & set(data):
        data["client_state"] = None  # Bankdaten neu aushandeln
    db.update("connections", "id", cid, data)
    return {"ok": True}


@app.post("/api/connections/{cid}/reset-tan")
def reset_tan(cid: int):
    get_db().update("connections", "id", cid, {"client_state": None, "tan_mechanism": None, "tan_medium": None})
    return {"ok": True}


@app.delete("/api/connections/{cid}")
def delete_connection(cid: int):
    db = get_db()
    secrets_store.delete_pin(cid)
    db.execute("UPDATE accounts SET connection_id = NULL WHERE connection_id = ?", (cid,))
    db.execute("DELETE FROM connections WHERE id = ?", (cid,))
    return {"ok": True}


@app.delete("/api/connections/{cid}/pin")
def forget_pin(cid: int):
    secrets_store.delete_pin(cid)
    return {"ok": True}


@app.post("/api/connections/{cid}/sync")
def sync(cid: int, body: dict = Body(default={})):
    try:
        job = fints_sync.start(cid, (body.get("pin") or None), bool(body.get("save_pin")), body.get("history_days"),
                               on_done=services.schedule_refresh)
    except fints_sync.UserFacingError as exc:
        _err(400, str(exc))
    return job.public()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = fints_sync.JOBS.get(job_id)
    if not job:
        _err(404, "Abruf nicht gefunden.")
    return job.public()


@app.post("/api/jobs/{job_id}/answer")
def job_answer(job_id: str, body: dict = Body(...)):
    job = fints_sync.answer(job_id, body.get("value"))
    if not job:
        _err(404, "Abruf nicht gefunden.")
    return job.public()


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    job = fints_sync.cancel(job_id)
    if not job:
        _err(404, "Abruf nicht gefunden.")
    return job.public()


# --- Verträge -------------------------------------------------------------------------------

CONTRACT_FIELDS = ("name", "status", "customer_no", "provider_address", "provider_email", "contract_end", "notice_months", "notes",
                   "cancel_effective", "cancelled_on", "category_id", "amount_cents", "interval", "next_due", "match_pattern")


@app.get("/api/contracts")
def list_contracts():
    db = get_db()
    cons = contracts.list_contracts(db)
    today = date.today()
    running = [c for c in cons if c["status"] != "ignored" and contracts.is_running(c, today)]
    return {
        "items": cons,
        "fixed_monthly_cents": analytics.fixed_costs_monthly(running),
        "income_monthly_cents": sum(c["monthly_cents"] for c in running if c["kind"] == "income"),
        "intervals": [i[0] for i in contracts.INTERVALS],
    }


@app.patch("/api/contracts/{key:path}")
def update_contract(key: str, body: dict = Body(...)):
    db = get_db()
    c = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not c:
        _err(404, "Vertrag nicht gefunden.")
    data = {k: (body[k] if body[k] != "" else None) for k in CONTRACT_FIELDS if k in body}
    if body.get("price_change_ack"):
        data["price_change_ack"] = c["amount_cents"]
    if data.get("status") == "cancelled" and not c["cancelled_on"] and "cancelled_on" not in data:
        data["cancelled_on"] = date.today().isoformat()
    data["updated"] = now_iso()
    db.update("contracts", "key", key, data)
    _changed()
    return contracts.enrich(db.one("SELECT * FROM contracts WHERE key = ?", (key,)))


@app.post("/api/contracts")
def create_contract(body: dict = Body(...)):
    db = get_db()
    name = (body.get("name") or "").strip()
    if not name or not body.get("amount_cents") or body.get("interval") not in contracts.INTERVAL_BY_NAME:
        _err(400, "Name, Betrag und Rhythmus sind nötig.")
    kind = "income" if int(body["amount_cents"]) > 0 else "expense"
    key = "manual:" + uuid.uuid4().hex[:10]
    db.insert("contracts", {
        "key": key, "name": name[:60], "counterparty": name[:60], "kind": kind, "interval": body["interval"],
        "amount_cents": int(body["amount_cents"]), "next_due": body.get("next_due") or date.today().isoformat(),
        "category_id": body.get("category_id"), "account_id": body.get("account_id"), "status": "confirmed", "active": 1,
        "manual": 1, "match_pattern": (body.get("match_pattern") or "").strip() or None, "count": 0, "updated": now_iso(),
    })
    _changed()
    return {"key": key}


@app.delete("/api/contracts/{key:path}")
def delete_contract(key: str):
    db = get_db()
    c = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not c:
        _err(404, "Vertrag nicht gefunden.")
    if c["manual"]:
        db.execute("UPDATE transactions SET contract_key = NULL WHERE contract_key = ?", (key,))
        db.execute("DELETE FROM contracts WHERE key = ?", (key,))
    else:
        db.update("contracts", "key", key, {"status": "ignored"})
    _changed()
    return {"ok": True}


@app.post("/api/letter")
def letter(body: dict = Body(...)):
    db = get_db()
    c = db.one("SELECT * FROM contracts WHERE key = ?", (body.get("key"),))
    if not c:
        _err(404, "Vertrag nicht gefunden.")
    return letters.build_letter(db, c, body.get("mode") or "ordentlich", body.get("date"))


# --- Auswertung, Einstellungen, Export ----------------------------------------------------------

@app.get("/api/stats")
def stats(month: str = ""):
    db = get_db()
    month = month or date.today().strftime("%Y-%m")
    return {"month": analytics.month_stats(db, month), "history": analytics.monthly_totals(db, 12)}


@app.get("/api/settings")
def get_settings():
    db = get_db()
    opts = options.load()
    return {"profile": db.get_setting("profile", {}) or {}, "buffer_cents": db.get_setting("buffer_cents", 0) or 0,
            "options": {k: opts.get(k) for k in ("sync_time", "sensors", "notify_service", "warn_threshold")},
            "product_id": bool((opts.get("fints_product_id") or "").strip()), "ha": ha.available()}


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    db = get_db()
    if "profile" in body:
        p = body["profile"] or {}
        db.set_setting("profile", {k: (p.get(k) or "").strip() for k in ("name", "street", "city", "email")})
    if "buffer_cents" in body:
        db.set_setting("buffer_cents", int(body["buffer_cents"] or 0))
    _changed()
    return get_settings()


@app.post("/api/demo")
def load_demo():
    db = get_db()
    res = demo.load_demo(db)
    contracts.detect(db)
    services.schedule_refresh()
    return res


@app.delete("/api/demo")
def remove_demo():
    db = get_db()
    demo.remove_demo(db)
    contracts.detect(db)
    services.schedule_refresh()
    return {"ok": True}


@app.post("/api/refresh")
def refresh():
    services.refresh(get_db(), notify=False)
    return {"ok": True}


@app.get("/api/export.csv")
def export_csv():
    db = get_db()
    rows = db.query("SELECT t.booking_date, t.value_date, a.name AS konto, t.counterparty, t.counterparty_iban, t.purpose, t.amount_cents, "
                    "c.name AS kategorie, t.is_transfer, t.note FROM transactions t JOIN accounts a ON a.id = t.account_id "
                    "LEFT JOIN categories c ON c.id = t.category_id ORDER BY t.booking_date, t.id")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Buchungstag", "Wertstellung", "Konto", "Gegenseite", "IBAN", "Verwendungszweck", "Betrag", "Kategorie", "Umbuchung", "Notiz"])
    for r in rows:
        w.writerow([r["booking_date"], r["value_date"], r["konto"], r["counterparty"] or "", r["counterparty_iban"] or "", r["purpose"] or "",
                    f"{r['amount_cents'] / 100:.2f}".replace(".", ","), r["kategorie"] or "", "ja" if r["is_transfer"] else "", r["note"] or ""])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="kassensturz-{date.today()}.csv"'})


# --- Open Banking (Enable Banking) ------------------------------------------------------------

def _psu(request: Request) -> dict:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return {"ip": fwd or request.headers.get("x-real-ip") or "", "ua": request.headers.get("user-agent") or ""}


def _eb(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except openbanking.EBError as exc:
        _err(400, str(exc))


@app.get("/api/eb")
def eb_status():
    db = get_db()
    cfg = openbanking.get_config(db)
    return {**cfg, "configured": openbanking.is_configured(db), "sessions": openbanking.list_sessions(db),
            "default_redirect": openbanking.DEFAULT_REDIRECT}


@app.put("/api/eb/config")
def eb_config(body: dict = Body(...)):
    db = get_db()
    info = _eb(openbanking.save_config, db, body.get("app_id"), body.get("private_key"), body.get("redirect_url"))
    return {"ok": True, "application": {k: info.get(k) for k in ("name", "environment", "active", "countries") if k in info}}


@app.delete("/api/eb/config")
def eb_config_delete():
    openbanking.remove_config(get_db())
    return {"ok": True}


@app.get("/api/eb/aspsps")
def eb_aspsps(country: str = "DE"):
    return _eb(openbanking.aspsps, get_db(), country)


@app.post("/api/eb/auth")
def eb_auth(request: Request, body: dict = Body(...)):
    return _eb(openbanking.start_auth, get_db(), body.get("aspsp"), body.get("country") or "DE", body.get("renew_id"), _psu(request))


@app.post("/api/eb/complete")
def eb_complete(request: Request, body: dict = Body(...)):
    db = get_db()
    res = _eb(openbanking.complete_auth, db, body.get("text") or "", _psu(request))
    job = openbanking.start_sync(res["id"], psu=_psu(request), on_done=services.schedule_refresh)
    return {**res, "job": job.public()}


@app.post("/api/eb/sessions/{eb_id}/sync")
def eb_sync(request: Request, eb_id: int):
    job = _eb(openbanking.start_sync, eb_id, psu=_psu(request), on_done=services.schedule_refresh)
    return job.public()


@app.patch("/api/eb/sessions/{eb_id}")
def eb_session_update(eb_id: int, body: dict = Body(...)):
    db = get_db()
    if "history_days" in body:
        db.update("eb_sessions", "id", eb_id, {"history_days": int(body["history_days"] or 365)})
    return {"ok": True}


@app.delete("/api/eb/sessions/{eb_id}")
def eb_session_delete(eb_id: int):
    openbanking.delete_session(get_db(), eb_id)
    services.schedule_refresh()
    return {"ok": True}


# --- Eingangsordner -------------------------------------------------------------------------------

@app.get("/api/inbox")
def inbox_status():
    return inbox.status(get_db())


@app.post("/api/inbox/scan")
def inbox_scan():
    res = inbox.scan(get_db())
    if res["imported"]:
        contracts.detect(get_db())
        services.schedule_refresh()
    return res


@app.post("/api/inbox/analyze")
def inbox_analyze(body: dict = Body(...)):
    import json

    db = get_db()
    name = body.get("filename") or ""
    try:
        data, _ = inbox.read_file(name)
    except FileNotFoundError:
        _err(404, "Die Datei liegt nicht mehr im Eingangsordner.")
    res = importers.analyze(data, name)
    profile = None
    if res.get("signature"):
        prof = db.one("SELECT mapping FROM csv_profiles WHERE signature = ?", (res["signature"],))
        if prof:
            profile = json.loads(prof["mapping"])
            res = importers.analyze(data, name, profile)
    token = uuid.uuid4().hex
    _imports[token] = {"data": data, "filename": name, "created": time.time(), "inbox_file": name}
    out = _analysis_public(res)
    out.update({"token": token, "account_id": inbox.match_account(db, res, name), "profile_used": bool(profile)})
    return out


@app.delete("/api/inbox/{filename}")
def inbox_delete(filename: str):
    try:
        inbox.delete_file(get_db(), filename)
    except FileNotFoundError:
        _err(404, "Datei nicht gefunden.")
    return {"ok": True}
