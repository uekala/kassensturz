"""HTTP-Routen: Übersicht, erwartete Eingänge, Projekte, geplante Ausgaben, Auffälligkeiten, Kalender. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Body

from . import anomalies, audit, contracts, expected, ha, options, planned, projects, services
from .db import get_db
from .web import _changed, _err
from .routes_transactions import _tx_filter

router = APIRouter()

# --- Status & Übersicht -------------------------------------------------------------

@router.get("/api/state")
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


@router.get("/api/overview")
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
        "expected": expected.overview(db),
        "planned": planned.overview(db),
        "price_changes": sum(1 for c in cons if c.get("price_change_cents") and c["kind"] == "expense" and c["price_change_cents"] < 0
                             and c["status"] != "ignored"),
    }


def _expected(call, *args):
    try:
        result = call(get_db(), *args)
    except expected.ExpectedError as error:
        _err(error.status, error.message)
    audit.subject(result.get("label"), result.get("account_id"))
    _changed()
    return result


@router.get("/api/expected")
def expected_list():
    return expected.overview(get_db())


@router.post("/api/expected")
def expected_create(body: dict = Body(...)):
    return _expected(expected.create, body)


@router.post("/api/expected/{item_id}/received")
def expected_received(item_id: int, body: dict = Body(default={})):
    return _expected(expected.close, item_id, body)


@router.post("/api/expected/{item_id}/drop")
def expected_drop(item_id: int):
    return _expected(expected.drop, item_id)


@router.post("/api/expected/{item_id}/reopen")
def expected_reopen(item_id: int):
    return _expected(expected.reopen, item_id)


def _projects(call, *args):
    try:
        result = call(get_db(), *args)
    except projects.ProjectError as error:
        _err(error.status, error.message)
    if isinstance(result, dict):
        project = result.get("project") or result
        audit.subject(project.get("name"))
        if "assigned" in result:
            audit.subject(f"{project.get('name')}, {result['assigned']} Buchungen")
    _changed()
    return result


@router.get("/api/projects")
def project_list():
    return projects.overview(get_db())


@router.post("/api/projects")
def project_create(body: dict = Body(...)):
    return _projects(projects.create, body)


# Vor den Routen mit Nummer, sonst gälte „unassign“ als Nummer.
@router.post("/api/projects/unassign")
def project_unassign(body: dict = Body(...)):
    return _projects(projects.unassign, body.get("tx_ids"))


@router.get("/api/projects/{project_id}")
def project_detail(project_id: int):
    try:
        return projects.detail(get_db(), project_id)
    except projects.ProjectError as error:
        _err(error.status, error.message)


@router.post("/api/projects/{project_id}")
def project_change(project_id: int, body: dict = Body(...)):
    return _projects(projects.change, project_id, body)


@router.delete("/api/projects/{project_id}")
def project_delete(project_id: int):
    audit.subject(get_db().scalar("SELECT name FROM projects WHERE id = ?", (project_id,)))
    _projects(projects.delete, project_id)
    return {"ok": True}


@router.post("/api/projects/{project_id}/assign")
def project_assign(project_id: int, body: dict = Body(...)):
    """Ordnet Buchungen zu: einzeln genannte (``tx_ids``) oder alle Treffer eines Filters der Buchungsliste (``filter``)."""
    flt = body.get("filter")
    if flt is None:
        return _projects(projects.assign, project_id, body.get("tx_ids"))
    if not isinstance(flt, dict) or not any(flt.get(k) for k in ("q", "account", "category", "month", "kind", "contract", "project")):
        _err(400, "Ohne Suche oder Filter wären das alle Buchungen. Bitte erst eingrenzen.")

    def number(key):
        value = flt.get(key)
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            _err(400, "Der Filter ist ungültig.")

    sql_where, params = _tx_filter(str(flt.get("q") or ""), number("account"), number("category"), str(flt.get("month") or ""),
                                   str(flt.get("kind") or ""), str(flt.get("contract") or ""), number("project"))
    db = get_db()
    ids = [r["id"] for r in db.query(
        f"SELECT t.id FROM transactions t JOIN accounts a ON a.id = t.account_id LEFT JOIN categories c ON c.id = t.category_id "
        f"WHERE {sql_where} AND t.is_transfer = 0 ORDER BY t.id LIMIT ?", (*params, projects.MAX_ASSIGN + 1))]
    if not ids:
        _err(404, "Zu diesem Filter gibt es keine Buchungen.")
    if len(ids) > projects.MAX_ASSIGN:
        _err(400, f"Das sind mehr als {projects.MAX_ASSIGN} Buchungen. Bitte enger eingrenzen.")
    return _projects(projects.assign, project_id, ids)


def _planned(call, *args):
    try:
        result = call(get_db(), *args)
    except planned.PlannedError as error:
        _err(error.status, error.message)
    audit.subject(result.get("label"), result.get("account_id"))
    _changed()
    return result


@router.get("/api/planned")
def planned_list():
    return planned.overview(get_db())


@router.post("/api/planned")
def planned_create(body: dict = Body(...)):
    return _planned(planned.create, body)


@router.post("/api/planned/{item_id}")
def planned_change(item_id: int, body: dict = Body(...)):
    return _planned(planned.change, item_id, body)


@router.post("/api/planned/{item_id}/paid")
def planned_paid(item_id: int, body: dict = Body(default={})):
    return _planned(planned.close, item_id, body)


@router.post("/api/planned/{item_id}/drop")
def planned_drop(item_id: int):
    return _planned(planned.drop, item_id)


@router.post("/api/planned/{item_id}/reopen")
def planned_reopen(item_id: int):
    return _planned(planned.reopen, item_id)


@router.post("/api/anomalies/ack")
def anomaly_ack(body: dict = Body(...)):
    """Blendet eine Auffälligkeit aus: Die Buchung gilt als geprüft."""
    if not anomalies.acknowledge(get_db(), body.get("key")):
        _err(400, "Diesen Hinweis gibt es nicht.")
    _changed()
    return {"ok": True}
