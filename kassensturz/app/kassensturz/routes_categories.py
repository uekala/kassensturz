"""HTTP-Routen: Kategorien, Budgets, Regeln, Änderungsprotokoll. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Body

from . import analytics, audit, categorize, household
from .db import get_db, now_iso
from .util import euro
from .web import _changed, _err

router = APIRouter()

# --- Kategorien, Budgets, Regeln ------------------------------------------------------

@router.get("/api/categories")
def categories():
    return get_db().query("SELECT * FROM categories ORDER BY sort, name")


@router.post("/api/categories")
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
    audit.subject(name[:60])
    return db.one("SELECT * FROM categories WHERE id = ?", (cid,))


@router.patch("/api/categories/{cid}")
def update_category(cid: int, body: dict = Body(...)):
    db = get_db()
    data = {}
    if "name" in body and (body["name"] or "").strip():
        data["name"] = body["name"].strip()[:60]
    if "budget_cents" in body:
        b = body["budget_cents"]
        data["budget_cents"] = int(b) if b not in (None, "", 0) else None
    before = db.one("SELECT name, budget_cents FROM categories WHERE id = ?", (cid,))
    db.update("categories", "id", cid, data)
    if before:
        _note_category(before, data)
    _changed()
    return db.one("SELECT * FROM categories WHERE id = ?", (cid,))


def _note_category(before: dict, data: dict) -> None:
    parts = []
    if "name" in data and data["name"] != before["name"]:
        parts.append(f"Kategorie „{before['name']}“ heißt jetzt „{data['name']}“")
    if "budget_cents" in data and data["budget_cents"] != before["budget_cents"]:
        name = data.get("name") or before["name"]
        if data["budget_cents"] is None:
            parts.append(f"Budget „{name}“ entfernt (vorher {euro(before['budget_cents'])})")
        elif before["budget_cents"] is None:
            parts.append(f"Budget „{name}“ festgelegt: {euro(data['budget_cents'])}")
        else:
            parts.append(f"Budget „{name}“: {euro(data['budget_cents'])} statt {euro(before['budget_cents'])}")
    for text in parts:
        audit.note(text)
    if not parts:
        audit.skip()


@router.delete("/api/categories/{cid}")
def delete_category(cid: int):
    db = get_db()
    cat = db.one("SELECT * FROM categories WHERE id = ?", (cid,))
    if not cat:
        _err(404, "Kategorie nicht gefunden.")
    audit.subject(cat["name"])
    if cat["builtin_key"]:
        _err(400, "Eingebaute Kategorien lassen sich nur umbenennen.")
    fallback = cat["parent_id"] or db.scalar("SELECT id FROM categories WHERE builtin_key = 'sonstiges'")
    with db.tx():
        db.execute("UPDATE transactions SET category_id = ? WHERE category_id = ?", (fallback, cid))
        db.execute("UPDATE splits SET category_id = ? WHERE category_id = ?", (fallback, cid))
        db.execute("UPDATE rules SET category_id = ? WHERE category_id = ?", (fallback, cid))
        db.execute("DELETE FROM learned_categories WHERE category_id = ?", (cid,))
        db.execute("UPDATE categories SET parent_id = ? WHERE parent_id = ?", (cat["parent_id"], cid))
        db.execute("DELETE FROM categories WHERE id = ?", (cid,))
    _changed()
    return {"ok": True}


@router.get("/api/budgets")
def get_budgets(month: str = "", person: int | None = None):
    """Budgets des Haushalts oder, mit ``person``, die eigenen einer Person auf ihren eigenen Konten."""
    db = get_db()
    on = date.fromisoformat(month + "-15") if month else date.today()
    if on.year == date.today().year and on.month == date.today().month:
        on = date.today()
    else:
        from .util import month_end
        on = month_end(on)
    if person is not None:
        if not household.person_exists(db, person):
            _err(404, "Diese Person gibt es nicht.")
        own = db.part("own", person)
        return {"budgets": household.own_budgets(db, person, on), "stats": analytics.month_stats(own, on.strftime("%Y-%m")),
                "limits": household.own_budget_limits(db, person)}
    shared = db.part("shared")
    return {"budgets": analytics.budgets(shared, on), "stats": analytics.month_stats(db, on.strftime("%Y-%m")),
            # Vorschläge aus den letzten vollen Monaten, wie in der App
            "suggestions": analytics.budget_suggestions(shared)}


@router.get("/api/rules")
def rules():
    db = get_db()
    return db.query("SELECT r.*, c.name AS category_name FROM rules r LEFT JOIN categories c ON c.id = r.category_id ORDER BY r.priority, r.id")


@router.get("/api/learned")
def learned_categories():
    return get_db().query(
        "SELECT l.id, l.label, l.sign, l.category_id, c.name AS category_name FROM learned_categories l "
        "LEFT JOIN categories c ON c.id = l.category_id WHERE l.parent_id IS NULL ORDER BY l.label COLLATE NOCASE")


@router.delete("/api/learned/{lid}")
def forget_learned(lid: int):
    db = get_db()
    categorize.forget(db, lid)
    changed = categorize.recategorize(db)
    _changed()
    return {"ok": True, "recategorized": changed}


@router.post("/api/rules")
def create_rule(body: dict = Body(...)):
    db = get_db()
    pattern = (body.get("pattern") or "").strip()
    if not pattern:
        _err(400, "Suchbegriff fehlt.")
    cat = db.one("SELECT * FROM categories WHERE id = ?", (body.get("category_id"),)) if body.get("category_id") else None
    audit.subject(f"„{pattern[:40]}“ → " + ("Umbuchung" if body.get("mark_transfer") or (cat and cat["kind"] == "transfer")
                                               else (cat["name"] if cat else "keine Kategorie")))
    rid = db.insert("rules", {"pattern": pattern, "field": body.get("field") or "any", "sign": body.get("sign") or "any",
                              "category_id": cat["id"] if cat else None,
                              "mark_transfer": 1 if (body.get("mark_transfer") or (cat and cat["kind"] == "transfer")) else 0,
                              "priority": int(body.get("priority") or 100), "enabled": 1, "created": now_iso()})
    n = categorize.recategorize(db)
    _changed()
    return {"id": rid, "recategorized": n}


@router.patch("/api/rules/{rid}")
def update_rule(rid: int, body: dict = Body(...)):
    db = get_db()
    data = {k: body[k] for k in ("pattern", "field", "sign", "category_id", "priority", "enabled", "mark_transfer") if k in body}
    db.update("rules", "id", rid, data)
    n = categorize.recategorize(db)
    _changed()
    return {"ok": True, "recategorized": n}


@router.delete("/api/rules/{rid}")
def delete_rule(rid: int):
    db = get_db()
    pattern = db.scalar("SELECT pattern FROM rules WHERE id = ?", (rid,))
    audit.subject(f"„{pattern[:40]}“" if pattern else None)
    db.execute("DELETE FROM rules WHERE id = ?", (rid,))
    n = categorize.recategorize(db)
    _changed()
    return {"ok": True, "recategorized": n}


@router.post("/api/recategorize")
def recategorize_all():
    n = categorize.recategorize(get_db())
    _changed()
    return {"recategorized": n}
