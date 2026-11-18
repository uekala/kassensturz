"""HTTP-Routen: Bankabruf per FinTS und Open Banking. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

from fastapi import APIRouter, Body, Request

from . import fints_sync, openbanking, secrets_store, services
from .db import get_db, now_iso
from .web import _err

router = APIRouter()

# --- FinTS ---------------------------------------------------------------------------------

@router.get("/api/banks")
def banks():
    return fints_sync.BANK_PRESETS


@router.get("/api/connections")
def connections():
    db = get_db()
    out = []
    for c in db.query("SELECT id, name, blz, login, customer_id, server, tan_mechanism, tan_medium, history_days, last_sync, last_status "
                      "FROM connections ORDER BY id"):
        c["has_pin"] = secrets_store.has_pin(c["id"])
        c["accounts"] = db.query("SELECT id, name FROM accounts WHERE connection_id = ?", (c["id"],))
        out.append(c)
    return out


@router.post("/api/connections")
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


@router.patch("/api/connections/{cid}")
def update_connection(cid: int, body: dict = Body(...)):
    db = get_db()
    data = {k: body[k] for k in ("name", "blz", "login", "customer_id", "server", "history_days") if k in body}
    if {"blz", "login", "customer_id", "server"} & set(data):
        data["client_state"] = None  # Bankdaten neu aushandeln
    db.update("connections", "id", cid, data)
    return {"ok": True}


@router.post("/api/connections/{cid}/reset-tan")
def reset_tan(cid: int):
    get_db().update("connections", "id", cid, {"client_state": None, "tan_mechanism": None, "tan_medium": None})
    return {"ok": True}


@router.delete("/api/connections/{cid}")
def delete_connection(cid: int):
    db = get_db()
    secrets_store.delete_pin(cid)
    db.execute("UPDATE accounts SET connection_id = NULL WHERE connection_id = ?", (cid,))
    db.execute("DELETE FROM connections WHERE id = ?", (cid,))
    return {"ok": True}


@router.delete("/api/connections/{cid}/pin")
def forget_pin(cid: int):
    secrets_store.delete_pin(cid)
    return {"ok": True}


@router.post("/api/connections/{cid}/sync")
def sync(cid: int, body: dict = Body(default={})):
    try:
        job = fints_sync.start(cid, (body.get("pin") or None), bool(body.get("save_pin")), body.get("history_days"),
                               on_done=services.schedule_refresh)
    except fints_sync.UserFacingError as exc:
        _err(400, str(exc))
    return job.public()


@router.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = fints_sync.JOBS.get(job_id)
    if not job:
        _err(404, "Abruf nicht gefunden.")
    return job.public()


@router.post("/api/jobs/{job_id}/answer")
def job_answer(job_id: str, body: dict = Body(...)):
    job = fints_sync.answer(job_id, body.get("value"))
    if not job:
        _err(404, "Abruf nicht gefunden.")
    return job.public()


@router.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    job = fints_sync.cancel(job_id)
    if not job:
        _err(404, "Abruf nicht gefunden.")
    return job.public()


# --- Open Banking (Enable Banking) ------------------------------------------------------------

def _psu(request: Request) -> dict:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return {"ip": fwd or request.headers.get("x-real-ip") or "", "ua": request.headers.get("user-agent") or ""}


def _eb(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except openbanking.EBError as exc:
        _err(400, str(exc))


@router.get("/api/eb")
def eb_status():
    db = get_db()
    cfg = openbanking.get_config(db)
    return {**cfg, "configured": openbanking.is_configured(db), "sessions": openbanking.list_sessions(db),
            "default_redirect": openbanking.DEFAULT_REDIRECT}


@router.put("/api/eb/config")
def eb_config(body: dict = Body(...)):
    db = get_db()
    info = _eb(openbanking.save_config, db, body.get("app_id"), body.get("private_key"), body.get("redirect_url"))
    return {"ok": True, "application": {k: info.get(k) for k in ("name", "environment", "active", "countries") if k in info}}


@router.delete("/api/eb/config")
def eb_config_delete():
    openbanking.remove_config(get_db())
    return {"ok": True}


@router.get("/api/eb/aspsps")
def eb_aspsps(country: str = "DE"):
    return _eb(openbanking.aspsps, get_db(), country)


@router.post("/api/eb/auth")
def eb_auth(request: Request, body: dict = Body(...)):
    return _eb(openbanking.start_auth, get_db(), body.get("aspsp"), body.get("country") or "DE", body.get("renew_id"), _psu(request))


@router.post("/api/eb/complete")
def eb_complete(request: Request, body: dict = Body(...)):
    db = get_db()
    res = _eb(openbanking.complete_auth, db, body.get("text") or "", _psu(request))
    job = openbanking.start_sync(res["id"], psu=_psu(request), on_done=services.schedule_refresh)
    return {**res, "job": job.public()}


@router.post("/api/eb/sessions/{eb_id}/sync")
def eb_sync(request: Request, eb_id: int):
    job = _eb(openbanking.start_sync, eb_id, psu=_psu(request), on_done=services.schedule_refresh)
    return job.public()


@router.patch("/api/eb/sessions/{eb_id}")
def eb_session_update(eb_id: int, body: dict = Body(...)):
    db = get_db()
    if "history_days" in body:
        db.update("eb_sessions", "id", eb_id, {"history_days": int(body["history_days"] or 365)})
    return {"ok": True}


@router.delete("/api/eb/sessions/{eb_id}")
def eb_session_delete(eb_id: int):
    openbanking.delete_session(get_db(), eb_id)
    services.schedule_refresh()
    return {"ok": True}
