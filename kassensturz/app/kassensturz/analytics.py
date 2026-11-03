"""Prognose, „frei verfügbar", Budgets und Monatsauswertungen."""
from __future__ import annotations

import calendar
import statistics
from collections import defaultdict
from datetime import date, timedelta

from . import contracts as contracts_mod
from . import ledger
from .db import Database
from .util import add_months, month_end, month_start

HORIZON_DAYS = 45


def _forecast_accounts(db: Database) -> list[dict]:
    return [a for a in ledger.accounts_with_balance(db) if a["in_forecast"]]


def variable_daily_rate(db: Database, account_ids: list[int]) -> int:
    """Typische tägliche Ausgaben ohne Verträge und Umbuchungen (Cent, positiv)."""
    if not account_ids:
        return 0
    today = date.today()
    start = month_start(add_months(today, -3))
    es = [e for e in ledger.entries(db, start.isoformat(), today.isoformat(), account_ids)
          if e["amount_cents"] < 0 and not e["is_transfer"] and not e["contract_key"]]
    if not es:
        return 0
    first_s = db.scalar(f"SELECT MIN(booking_date) FROM transactions WHERE account_id IN ({','.join('?' * len(account_ids))})",
                        tuple(account_ids))
    first = date.fromisoformat(first_s) if first_s else today
    months = defaultdict(int)
    for e in es:
        months[e["booking_date"][:7]] += -e["amount_cents"]
    full = []
    for i in (1, 2, 3):
        m = add_months(month_start(today), -i)
        if first <= m + timedelta(days=3):
            full.append(months.get(m.strftime("%Y-%m"), 0) / calendar.monthrange(m.year, m.month)[1])
    if full:
        return int(statistics.median(full))
    start_d = max(first, start)
    days = max(14, (today - start_d).days + 1)
    return int(sum(-e["amount_cents"] for e in es) / days)


def forecast(db: Database, horizon_days: int = HORIZON_DAYS) -> dict:
    today = date.today()
    accounts = _forecast_accounts(db)
    ids = [a["id"] for a in accounts]
    balance_now = sum(a["balance_now"] for a in accounts)
    cons = contracts_mod.list_contracts(db)
    end = today + timedelta(days=horizon_days)
    upcoming = [u for u in contracts_mod.upcoming(db, today + timedelta(days=1), end, cons) if u["account_id"] in ids or u["account_id"] is None]
    rate = variable_daily_rate(db, ids)

    # Zeitraum bis zum nächsten Gehaltseingang (oder Monatsende)
    gehalt_ids = {c["key"] for c in cons if c["kind"] == "income" and (c["amount_cents"] or 0) >= 20000}
    next_income = next((u for u in upcoming if u["key"] in gehalt_ids), None)
    if next_income and (date.fromisoformat(next_income["date"]) - today).days <= 40:
        period_end = date.fromisoformat(next_income["date"]) - timedelta(days=1)
        period_label = "bis zum nächsten Gehalt"
    else:
        period_end = month_end(today)
        period_label = "bis Monatsende"
    if period_end < today:
        period_end = today
    in_period = [u for u in upcoming if u["date"] <= period_end.isoformat()]
    fixed_out = sum(u["amount_cents"] for u in in_period if u["amount_cents"] < 0)
    fixed_in = sum(u["amount_cents"] for u in in_period if u["amount_cents"] > 0)
    buffer = int(db.get_setting("buffer_cents", 0) or 0)
    days_left = (period_end - today).days + 1
    free = balance_now + fixed_in + fixed_out - buffer

    # Tagesverlauf: Vergangenheit + Prognose
    past = ledger.balance_series(db, ids, today - timedelta(days=60), today)
    by_day = defaultdict(int)
    for u in upcoming:
        by_day[u["date"]] += u["amount_cents"]
    future = []
    bal = balance_now
    for i in range(1, horizon_days + 1):
        d = today + timedelta(days=i)
        bal += by_day.get(d.isoformat(), 0) - rate
        future.append((d.isoformat(), int(bal)))
    low = min(future, key=lambda x: x[1]) if future else (today.isoformat(), balance_now)
    me = month_end(today).isoformat()
    month_end_value = next((v for d, v in future if d == me), balance_now if me == today.isoformat() else None)
    return {
        "today": today.isoformat(),
        "balance_now": balance_now,
        "accounts": [{"id": a["id"], "name": a["name"], "balance": a["balance_now"], "known": a["balance_known"]} for a in accounts],
        "free_cents": free,
        "free_per_day_cents": int(free / days_left) if days_left else free,
        "period_end": period_end.isoformat(),
        "period_label": period_label,
        "days_left": days_left,
        "fixed_out_cents": fixed_out,
        "fixed_in_cents": fixed_in,
        "variable_daily_cents": rate,
        "variable_expected_cents": rate * days_left,
        "buffer_cents": buffer,
        "month_end_cents": month_end_value,
        "low_point": {"date": low[0], "cents": low[1]},
        "past": past,
        "future": future,
        "upcoming": upcoming,
    }


def category_tree(db: Database) -> tuple[dict, dict]:
    cats = {c["id"]: c for c in db.query("SELECT * FROM categories")}
    top = {}
    for cid, c in cats.items():
        p = c
        while p.get("parent_id") and p["parent_id"] in cats:
            p = cats[p["parent_id"]]
        top[cid] = p["id"]
    return cats, top


def budgets(db: Database, on: date | None = None) -> list[dict]:
    on = on or date.today()
    start, end = month_start(on), month_end(on)
    cats, top = category_tree(db)
    spent = defaultdict(int)
    for e in ledger.entries(db, start.isoformat(), end.isoformat()):
        if e["is_transfer"] or e["amount_cents"] >= 0 or not e["category_id"]:
            continue
        spent[e["category_id"]] += -e["amount_cents"]
        if top.get(e["category_id"]) != e["category_id"]:
            spent[("top", top.get(e["category_id"]))] += -e["amount_cents"]
    days = calendar.monthrange(on.year, on.month)[1]
    pace = on.day / days
    out = []
    for cid, c in cats.items():
        if not c["budget_cents"]:
            continue
        s = spent.get(cid, 0) + (spent.get(("top", cid), 0) if top.get(cid) == cid else 0)
        b = c["budget_cents"]
        ratio = s / b if b else 0
        state = "over" if ratio > 1 else ("warn" if ratio > max(0.8, pace + 0.1) else "ok")
        out.append({"category_id": cid, "name": c["name"], "budget_cents": b, "spent_cents": s, "left_cents": b - s,
                    "ratio": round(ratio, 3), "pace": round(pace, 3), "state": state, "parent_id": c["parent_id"]})
    out.sort(key=lambda x: -x["ratio"])
    return out


def month_stats(db: Database, month: str) -> dict:
    y, m = (int(x) for x in month.split("-"))
    start = date(y, m, 1)
    end = month_end(start)
    cats, top = category_tree(db)
    inc = exp = 0
    by_top = defaultdict(int)
    by_cat = defaultdict(int)
    for e in ledger.entries(db, start.isoformat(), end.isoformat()):
        if e["is_transfer"]:
            continue
        if e["amount_cents"] > 0:
            inc += e["amount_cents"]
        else:
            exp += -e["amount_cents"]
            t = top.get(e["category_id"]) if e["category_id"] else None
            by_top[t] += -e["amount_cents"]
            by_cat[e["category_id"]] += -e["amount_cents"]
    # Erstattungen mindern die Ausgaben ihrer Kategorie nicht – sie zählen als Einnahmen
    breakdown = []
    for t, cents in sorted(by_top.items(), key=lambda x: -x[1]):
        children = [{"category_id": cid, "name": cats[cid]["name"] if cid in cats else "Ohne Kategorie", "cents": v}
                    for cid, v in sorted(by_cat.items(), key=lambda x: -x[1]) if (top.get(cid) if cid else None) == t]
        breakdown.append({"category_id": t, "name": cats[t]["name"] if t in cats else "Ohne Kategorie", "cents": cents,
                          "children": children})
    return {"month": month, "income_cents": inc, "expense_cents": exp, "saldo_cents": inc - exp, "breakdown": breakdown}


def monthly_totals(db: Database, months: int = 12) -> list[dict]:
    today = date.today()
    start = month_start(add_months(today, -(months - 1)))
    res = {}
    for i in range(months):
        k = add_months(start, i).strftime("%Y-%m")
        res[k] = {"month": k, "income_cents": 0, "expense_cents": 0}
    for e in ledger.entries(db, start.isoformat(), today.isoformat()):
        if e["is_transfer"]:
            continue
        k = e["booking_date"][:7]
        if k not in res:
            continue
        if e["amount_cents"] > 0:
            res[k]["income_cents"] += e["amount_cents"]
        else:
            res[k]["expense_cents"] += -e["amount_cents"]
    return list(res.values())


def fixed_costs_monthly(cons: list[dict]) -> int:
    total = 0
    today = date.today()
    for c in cons:
        if c["kind"] != "expense" or not contracts_mod.is_running(c, today):
            continue
        total += -c["monthly_cents"]
    return total
