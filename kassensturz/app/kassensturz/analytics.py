"""Prognose, „frei verfügbar", Budgets und Monatsauswertungen."""
from __future__ import annotations

import calendar
import statistics
from collections import defaultdict
from datetime import date, timedelta

from . import contracts as contracts_mod
from . import ledger, planned, savings, sharing
from .db import Database
from .util import add_months, euro, month_end, month_start

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
    # Was als einmalige Ausgabe geplant war, ist kein Alltag und soll die Tagesrate nicht heben.
    once = planned.paid_tx_ids(db)
    if once:
        es = [e for e in es if e["id"] not in once]
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
    # Geplante Einmalausgaben: stehen fest wie eine Abbuchung, gehören aber zu keinem Vertrag.
    plans = planned.upcoming(db, ids, today + timedelta(days=1), end)
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
    planned_out = sum(p["amount_cents"] for p in plans if p["date"] <= period_end.isoformat())
    buffer = int(db.get_setting("buffer_cents", 0) or 0)
    days_left = (period_end - today).days + 1
    # Rücklage für seltene Kosten: immer ausgewiesen, abgezogen nur auf Wunsch. Wer sie auf
    # einem Tagesgeldkonto hält, hat sie schon aus dem Alltag herausgenommen.
    rsv = savings.reserve(cons, today, period_end)
    deduct = bool(db.get_setting("deduct_reserve", False))
    free = balance_now + fixed_in + fixed_out + planned_out - buffer - (rsv["reserved_cents"] if deduct else 0)

    # Tagesverlauf: Vergangenheit + Prognose
    past = ledger.balance_series(db, ids, today - timedelta(days=60), today)
    by_day = defaultdict(int)
    upcoming = sorted(upcoming + plans, key=lambda x: (x["date"], x["amount_cents"]))
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
        "planned_out_cents": planned_out,
        "variable_daily_cents": rate,
        "variable_expected_cents": rate * days_left,
        "buffer_cents": buffer,
        "reserve_cents": rsv["reserved_cents"],
        "reserve_monthly_cents": rsv["monthly_cents"],
        "reserve_deducted": deduct,
        "reserve_items": rsv["items"],
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


def budgets(db: Database, on: date | None = None, limits: dict[int, int] | None = None) -> list[dict]:
    """Budgets des Monats mit Verbrauch. ``limits`` ersetzt die Budgets der Kategorien,
    etwa durch die eigenen einer Person; gezählt wird, was ``db`` an Buchungen zeigt."""
    on = on or date.today()
    start, end = month_start(on), month_end(on)
    cats, top = category_tree(db)
    spent = defaultdict(int)
    for e in sharing.spending(db, start.isoformat(), end.isoformat()):
        if e["is_transfer"] or e["amount_cents"] >= 0 or not e["category_id"]:
            continue
        spent[e["category_id"]] += -e["amount_cents"]
        if top.get(e["category_id"]) != e["category_id"]:
            spent[("top", top.get(e["category_id"]))] += -e["amount_cents"]
    days = calendar.monthrange(on.year, on.month)[1]
    pace = on.day / days
    out = []
    for cid, c in cats.items():
        b = c["budget_cents"] if limits is None else limits.get(cid)
        if not b:
            continue
        s = spent.get(cid, 0) + (spent.get(("top", cid), 0) if top.get(cid) == cid else 0)
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
    for e in sharing.spending(db, start.isoformat(), end.isoformat()):
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
    for e in sharing.spending(db, start.isoformat(), today.isoformat()):
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


MONTH_NAMES = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
               "November", "Dezember")
MAX_AFFORD_CENTS = 100_000_000


def afford(fc: dict, amount_cents: int, threshold_cents: int = 0) -> dict:
    """Was eine Ausgabe von heute für den Rest des Zeitraums bedeutet.

    „Nein“, wenn sie mehr kostet, als nach den festen Abbuchungen frei ist. „Knapp“, wenn danach
    weniger für den Alltag bleibt, als du sonst ausgibst, oder die Prognose unter die Warnschwelle
    fällt. Sonst „ja“."""
    amount = abs(int(amount_cents))
    days = max(1, int(fc["days_left"]))
    free_after = fc["free_cents"] - amount
    everyday = int(fc["variable_expected_cents"])
    low_after = fc["low_point"]["cents"] - amount
    if free_after < 0:
        verdict = "no"
    elif free_after < everyday or low_after < threshold_cents:
        verdict = "tight"
    else:
        verdict = "yes"
    return {
        "amount_cents": amount,
        "verdict": verdict,
        "free_before_cents": int(fc["free_cents"]),
        "free_after_cents": int(free_after),
        "per_day_before_cents": int(fc["free_cents"] / days),
        "per_day_after_cents": int(free_after / days),
        "usual_per_day_cents": int(fc["variable_daily_cents"]),
        "days_left": days,
        "period_end": fc["period_end"],
        "period_label": fc["period_label"],
        "low_point_after": {"date": fc["low_point"]["date"], "cents": int(low_after)},
        "below_threshold": low_after < threshold_cents,
    }


def month_review(db: Database, month: str) -> dict:
    """Monatsabschluss: Einnahmen, Ausgaben, Sparquote und was vom Üblichen abweicht.

    Verglichen wird mit dem Schnitt der drei Monate davor, soweit es dafür Buchungen gibt."""
    y, m = (int(x) for x in month.split("-"))
    start = date(y, m, 1)
    stats = month_stats(db, month)
    earlier = [month_stats(db, add_months(start, -i).strftime("%Y-%m")) for i in (1, 2, 3)]
    earlier = [s for s in earlier if s["income_cents"] or s["expense_cents"]]
    usual_expense = int(sum(s["expense_cents"] for s in earlier) / len(earlier)) if earlier else None
    usual_by_cat: dict = defaultdict(int)
    for s in earlier:
        for item in s["breakdown"]:
            usual_by_cat[item["category_id"]] += item["cents"]
    categories = []
    for item in stats["breakdown"][:5]:
        usual = int(usual_by_cat[item["category_id"]] / len(earlier)) if earlier else None
        categories.append({"category_id": item["category_id"], "name": item["name"], "cents": item["cents"],
                           "usual_cents": usual, "change_cents": None if usual is None else item["cents"] - usual})
    # Auffällig: mindestens 30 € und ein Viertel über dem Üblichen, die größte Abweichung zuerst.
    notable = sorted((c for c in categories if c["change_cents"] is not None and c["change_cents"] >= 3000
                      and c["change_cents"] * 4 >= (c["usual_cents"] or 0)), key=lambda c: -c["change_cents"])
    biggest = None
    for e in sharing.spending(db, start.isoformat(), month_end(start).isoformat()):
        if e["is_transfer"] or e["amount_cents"] >= 0 or e["contract_key"]:
            continue
        if biggest is None or e["amount_cents"] < biggest["amount_cents"]:
            biggest = {"name": (e.get("counterparty") or "Ohne Empfänger")[:60], "amount_cents": e["amount_cents"],
                       "date": e["booking_date"]}
    income, expense = stats["income_cents"], stats["expense_cents"]
    return {
        "month": month,
        "label": f"{MONTH_NAMES[m - 1]} {y}",
        "has_data": bool(income or expense),
        # Ein laufender Monat lässt sich noch nicht mit ganzen Monaten vergleichen.
        "complete": month < date.today().strftime("%Y-%m"),
        "income_cents": income,
        "expense_cents": expense,
        "saved_cents": income - expense,
        "savings_rate": round((income - expense) / income, 4) if income > 0 else None,
        "usual_expense_cents": usual_expense,
        "expense_change_cents": None if usual_expense is None else expense - usual_expense,
        "compared_months": len(earlier),
        "categories": categories,
        "notable": [c["name"] for c in notable[:3]],
        "biggest_expense": biggest,
    }


def review_message(review: dict) -> str:
    """Der Monatsabschluss in zwei, drei Sätzen für die Benachrichtigung."""
    saved = review["saved_cents"]
    parts = [f"Einnahmen {euro(review['income_cents'])}, Ausgaben {euro(review['expense_cents'])}."]
    if review["savings_rate"] is not None and saved > 0:
        parts.append(f"Gespart {euro(saved)}, Sparquote {round(review['savings_rate'] * 100)} %.")
    elif saved < 0:
        parts.append(f"{euro(-saved)} mehr ausgegeben als eingenommen.")
    change = review["expense_change_cents"]
    if change is not None and abs(change) >= 5000:
        parts.append(f"{euro(abs(change))} {'mehr' if change > 0 else 'weniger'} als sonst.")
    if review["notable"]:
        parts.append("Auffällig: " + ", ".join(review["notable"]) + ".")
    return " ".join(parts)


SUGGEST_MONTHS = 3


def _round_budget(cents: int) -> int:
    """Auf einen runden Betrag nach oben: 5 € bis 50 €, 10 € bis 500 €, darüber 50 €."""
    step = 500 if cents <= 5000 else 1000 if cents <= 50000 else 5000
    return -(-cents // step) * step


def budget_suggestions(db: Database, today: date | None = None) -> dict:
    """Budgets aus den Ausgaben der letzten vollen Monate.

    Je Oberkategorie der Durchschnitt, aufgerundet. Das Auffangbecken „Sonstiges"
    bekommt keinen Vorschlag: Dort hilft Zuordnen, kein Budget.
    """
    today = today or date.today()
    end = month_start(today) - timedelta(days=1)
    first = db.scalar("SELECT MIN(booking_date) FROM transactions")
    months = []
    if first:
        first_day = date.fromisoformat(first[:10])
        cursor = month_start(end)
        for _ in range(SUGGEST_MONTHS):
            # Nur Monate, die ganz in den Daten liegen; ein angebrochener erster Monat verfälscht den Schnitt.
            if cursor < month_start(first_day) or (cursor == month_start(first_day) and first_day.day > 5):
                break
            months.append(cursor)
            cursor = month_start(cursor - timedelta(days=1))
    if not months:
        return {"months": 0, "items": []}
    cats, top = category_tree(db)
    spent = defaultdict(int)
    for e in sharing.spending(db, months[-1].isoformat(), end.isoformat()):
        if e["is_transfer"] or e["amount_cents"] >= 0 or not e["category_id"]:
            continue
        spent[top.get(e["category_id"], e["category_id"])] += -e["amount_cents"]
    items = []
    for cid, c in cats.items():
        if c["kind"] != "expense" or c["parent_id"] or c.get("builtin_key") == "sonstiges":
            continue
        average = spent.get(cid, 0) // len(months)
        if average < 500:
            continue
        suggested = _round_budget(average)
        current = c["budget_cents"] or None
        # Ein Budget, das schon passt, braucht keinen Vorschlag.
        if current and abs(current - suggested) <= suggested * 0.2:
            continue
        items.append({"category_id": cid, "name": c["name"], "average_cents": average,
                      "suggested_cents": suggested, "current_cents": current})
    items.sort(key=lambda i: -i["average_cents"])
    return {"months": len(months), "items": items}


def _year_period(db: Database, start: date, end: date) -> dict:
    """Summen eines Zeitraums für den Jahresrückblick, ohne Umbuchungen."""
    _cats, top = category_tree(db)
    inc = exp = fixed = count = 0
    by_top: dict = defaultdict(int)
    months: dict = defaultdict(lambda: [0, 0])
    singles = []
    for e in sharing.spending(db, start.isoformat(), end.isoformat()):
        if e["is_transfer"]:
            continue
        count += 1
        cents = e["amount_cents"]
        k = e["booking_date"][:7]
        if cents > 0:
            inc += cents
            months[k][0] += cents
            continue
        exp += -cents
        months[k][1] += -cents
        by_top[top.get(e["category_id"]) if e["category_id"] else None] += -cents
        if e["contract_key"]:
            fixed += -cents
        else:
            singles.append(e)
    singles.sort(key=lambda e: e["amount_cents"])
    return {"income_cents": inc, "expense_cents": exp, "fixed_cents": fixed, "count": count, "by_top": by_top,
            "months": months, "singles": singles[:5]}


def year_review(db: Database, year: int, today: date | None = None) -> dict:
    """Jahresrückblick: Einnahmen, Ausgaben, Sparquote, Monate, Kategorien und große Einzelausgaben.

    Verglichen wird mit dem Vorjahr. Im laufenden Jahr nur bis zum selben Tag, damit ein halbes Jahr nicht
    gegen ein ganzes steht."""
    today = today or date.today()
    if not 2000 <= year <= today.year:
        raise ValueError("year")
    start = date(year, 1, 1)
    running = year == today.year
    end = today if running else date(year, 12, 31)
    cur = _year_period(db, start, end)
    prev_end = end.replace(year=year - 1) if not (end.month == 2 and end.day == 29) else date(year - 1, 2, 28)
    prev = _year_period(db, date(year - 1, 1, 1), prev_end)
    has_prev = bool(prev["income_cents"] or prev["expense_cents"])
    cats, _top = category_tree(db)

    def name(cid):
        return cats[cid]["name"] if cid in cats else "Ohne Kategorie"

    categories = []
    for cid, cents in sorted(cur["by_top"].items(), key=lambda x: -x[1])[:8]:
        before = prev["by_top"].get(cid, 0) if has_prev else None
        categories.append({"category_id": cid, "name": name(cid), "cents": cents,
                           "share": round(cents / cur["expense_cents"], 4) if cur["expense_cents"] else 0,
                           "previous_cents": before, "change_cents": None if before is None else cents - before})
    # Was im Vergleich zum Vorjahr am stärksten gestiegen oder gefallen ist, ab 100 €
    moved = []
    if has_prev:
        for cid in set(cur["by_top"]) | set(prev["by_top"]):
            change = cur["by_top"].get(cid, 0) - prev["by_top"].get(cid, 0)
            if abs(change) >= 10000:
                moved.append({"category_id": cid, "name": name(cid), "change_cents": change,
                              "cents": cur["by_top"].get(cid, 0), "previous_cents": prev["by_top"].get(cid, 0)})
        moved.sort(key=lambda c: -abs(c["change_cents"]))
    months = []
    last_month = end.month
    for m in range(1, 13):
        k = f"{year}-{m:02d}"
        inc, exp = cur["months"].get(k, [0, 0])
        months.append({"month": k, "label": MONTH_NAMES[m - 1], "income_cents": inc, "expense_cents": exp,
                       "saldo_cents": inc - exp, "future": m > last_month})
    # Bester und schwächster Monat nur unter ganzen Monaten mit Buchungen
    full = [mo for mo in months if not mo["future"] and (mo["income_cents"] or mo["expense_cents"])
            and not (running and mo["month"] == today.strftime("%Y-%m"))]
    best = max(full, key=lambda mo: mo["saldo_cents"]) if len(full) >= 2 else None
    worst = min(full, key=lambda mo: mo["saldo_cents"]) if len(full) >= 2 else None
    income, expense = cur["income_cents"], cur["expense_cents"]
    first = db.scalar("SELECT MIN(booking_date) FROM transactions")
    years = list(range(int(first[:4]), today.year + 1)) if first else [today.year]
    return {
        "year": year,
        "running": running,
        "until": end.isoformat(),
        "has_data": bool(income or expense),
        "years": years,
        "income_cents": income,
        "expense_cents": expense,
        "saved_cents": income - expense,
        "savings_rate": round((income - expense) / income, 4) if income > 0 else None,
        "fixed_cents": cur["fixed_cents"],
        "count": cur["count"],
        "previous": {
            "income_cents": prev["income_cents"], "expense_cents": prev["expense_cents"],
            "saved_cents": prev["income_cents"] - prev["expense_cents"], "until": prev_end.isoformat(),
        } if has_prev else None,
        "months": months,
        "best_month": best and {"month": best["month"], "label": best["label"], "saldo_cents": best["saldo_cents"]},
        "worst_month": worst and {"month": worst["month"], "label": worst["label"], "saldo_cents": worst["saldo_cents"]},
        "categories": categories,
        "moved": moved[:4],
        "biggest": [{"name": (e.get("counterparty") or e.get("purpose") or "Ohne Empfänger")[:60],
                     "amount_cents": e["amount_cents"], "date": e["booking_date"]} for e in cur["singles"]],
    }
