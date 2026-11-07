"""Erkennung wiederkehrender Zahlungen (Verträge, Abos, Gehalt) samt Preisänderungen."""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from .db import Database, now_iso
from .util import add_months, counterparty_key, norm

# Name, Tage, Toleranz (Tage), Mindestanzahl Buchungen, Monate (für exakte Fortschreibung)
INTERVALS = [
    ("wöchentlich", 7, 2, 5, None),
    ("monatlich", 30.44, 6, 3, 1),
    ("alle 2 Monate", 60.9, 8, 3, 2),
    ("vierteljährlich", 91.3, 12, 2, 3),
    ("halbjährlich", 182.6, 18, 2, 6),
    ("jährlich", 365.25, 25, 2, 12),
]
INTERVAL_BY_NAME = {i[0]: i for i in INTERVALS}

LOOKBACK_DAYS = 430


def monthly_factor(interval: str | None) -> float:
    spec = INTERVAL_BY_NAME.get(interval or "")
    return 30.44 / spec[1] if spec else 0.0


def next_after(d: date, interval: str) -> date:
    spec = INTERVAL_BY_NAME[interval]
    if spec[4]:
        return add_months(d, spec[4])
    return d + timedelta(days=round(spec[1]))


def _pretty(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    name = re.sub(r"(?i)\b(sagt danke|vielen dank|zweigniederlassung.*)$", "", name).strip(" ,.-/")
    if name.isupper() and len(name) > 3:
        name = name.title().replace("Gmbh", "GmbH").replace(" Ag", " AG").replace(" Se", " SE")
        name = re.sub(r"\.(Com|De|Net|Org|Io|Eu)\b", lambda m: "." + m.group(1).lower(), name)
    return name[:60] or "Unbekannt"


def _analyze(txs: list[dict], tol_ratio: float) -> dict | None:
    """Prüft eine Buchungsfolge auf Regelmäßigkeit und stabile Beträge."""
    by_day: dict[str, list[int]] = defaultdict(list)
    for t in txs:
        by_day[t["booking_date"]].append(t["amount_cents"])
    days = sorted(by_day)
    if len(days) < 2:
        return None
    dates = [date.fromisoformat(d) for d in days]
    # Mehrere Buchungen am selben Tag sind keine gemeinsame Zahlung. Für eine
    # bereits nach Betrag gruppierte Folge wird ein tatsächlich gebuchter
    # Repräsentant gewählt, statt die Einzelbeträge zu einer Summe zu addieren.
    amounts = []
    for day in days:
        values = by_day[day]
        median = statistics.median(values)
        amounts.append(min(values, key=lambda value: abs(value - median)))
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    best = None
    for name, length, tol, min_n, _months in INTERVALS:
        if len(dates) < min_n:
            continue
        ok = 0
        for g in gaps:
            if any(abs(g - k * length) <= tol * k for k in (1, 2)):
                ok += 1
        ratio = ok / len(gaps)
        med = statistics.median(gaps)
        if ratio >= 0.75 and abs(med - length) <= tol * 1.5:
            score = ratio - abs(med - length) / length
            if not best or score > best[0]:
                best = (score, name, length)
    if not best:
        return None
    _, interval, length = best
    recent = amounts[-6:]
    med_amt = statistics.median(recent)
    tol_abs = max(150, abs(med_amt) * tol_ratio)
    within = sum(1 for a in recent if abs(a - med_amt) <= tol_abs) / len(recent)
    before_last = recent[:-1]
    stable_before = len(before_last) >= 2 and max(before_last) - min(before_last) <= max(100, abs(statistics.median(before_last)) * 0.03)
    if within < 0.6 and not stable_before:
        return None
    last_amount = amounts[-1]
    prev_amount = None
    if len(amounts) >= 3:
        older = amounts[:-1][-4:]
        ref = statistics.median(older)
        if max(older) - min(older) <= max(100, abs(ref) * 0.03):
            diff = last_amount - ref
            if abs(diff) >= 50 and abs(diff) >= abs(ref) * 0.01:
                prev_amount = int(ref)
    variable = within < 1.0 and not stable_before
    forecast_amount = int(statistics.median(amounts[-3:])) if variable else last_amount
    last = dates[-1]
    nxt = next_after(last, interval)
    active = date.today() <= last + timedelta(days=round(length * 1.5) + 6)
    return {
        "interval": interval, "amount_cents": forecast_amount, "prev_amount_cents": prev_amount,
        "first_date": dates[0].isoformat(), "last_date": last.isoformat(), "next_due": nxt.isoformat(),
        "count": len(dates), "active": 1 if active else 0, "variable": variable,
    }


def _group_key(t: dict) -> str | None:
    sign = "in" if t["amount_cents"] > 0 else "out"
    if t.get("creditor_id") and sign == "out":
        return f"cred:{t['creditor_id'].upper()}:{(t.get('mandate_ref') or '').upper()}"
    k = counterparty_key(t.get("counterparty"))
    if not k:
        k = counterparty_key(t.get("purpose"))[:24]
    if len(k) < 3:
        return None
    return f"name:{k}:{sign}"


def detect(db: Database) -> dict:
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    txs = db.query(
        "SELECT t.id, t.account_id, t.booking_date, t.amount_cents, t.counterparty, t.purpose, t.creditor_id, t.mandate_ref, "
        "t.category_id, t.is_transfer, c.kind AS cat_kind FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
        "JOIN accounts a ON a.id = t.account_id WHERE a.archived = 0 AND t.booking_date >= ? ORDER BY t.booking_date",
        (since,),
    )
    txs = [t for t in txs if not t["is_transfer"] and t["cat_kind"] != "transfer"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in txs:
        k = _group_key(t)
        if k:
            groups[k].append(t)

    found: dict[str, tuple[dict, list[dict]]] = {}
    for key, group in groups.items():
        tol = 0.30 if key.startswith("cred:") else 0.12
        # Bei mehreren Buchungen desselben Zahlungspartners am selben Tag
        # zuerst nach Einzelbeträgen clustern. Eine Gesamtsumme pro Tag kann
        # sonst unterschiedliche Abos oder Käufe zu einer Zahlung verfälschen.
        has_same_day_bookings = len({t["booking_date"] for t in group}) < len(group)
        res = None if has_same_day_bookings else _analyze(group, tol)
        if res:
            found[key] = (res, group)
            continue
        if len(group) < 3:
            continue
        # Händler mit gemischten Käufen (z. B. Amazon): nach Betrag clustern
        clusters: list[list[dict]] = []
        for t in sorted(group, key=lambda x: x["amount_cents"]):
            if clusters:
                ref = statistics.median(c["amount_cents"] for c in clusters[-1])
                if abs(t["amount_cents"] - ref) <= max(50, abs(ref) * 0.04):
                    clusters[-1].append(t)
                    continue
            clusters.append([t])
        for c in clusters:
            if len(c) >= 4:
                res = _analyze(sorted(c, key=lambda x: x["booking_date"]), 0.03)
                if res:
                    ref = int(statistics.median(x["amount_cents"] for x in c))
                    found[f"{key}:{ref}"] = (res, c)

    existing = {c["key"]: c for c in db.query("SELECT * FROM contracts")}
    # Bereits beendete Folgen nur weiterführen, wenn sie schon bekannt sind
    found = {k: v for k, v in found.items() if v[0]["active"] or k in existing}
    with db.tx():
        db.execute("UPDATE transactions SET contract_key = NULL WHERE contract_key IS NOT NULL AND contract_key NOT LIKE 'manual:%'")
        for key, (res, group) in found.items():
            names = Counter(_pretty(t["counterparty"] or t["purpose"] or "") for t in group)
            cats = Counter(t["category_id"] for t in group if t["category_id"])
            accs = Counter(t["account_id"] for t in group)
            data = {
                "counterparty": names.most_common(1)[0][0],
                "kind": "income" if res["amount_cents"] > 0 else "expense",
                "interval": res["interval"], "amount_cents": res["amount_cents"], "prev_amount_cents": res["prev_amount_cents"],
                "first_date": res["first_date"], "last_date": res["last_date"], "next_due": res["next_due"], "count": res["count"],
                "category_id": cats.most_common(1)[0][0] if cats else None, "account_id": accs.most_common(1)[0][0],
                "active": res["active"], "updated": now_iso(),
            }
            if key in existing:
                old = existing[key]
                if old["status"] == "cancelled" and old["cancel_effective"] and old["cancel_effective"] < res["last_date"]:
                    data["status"] = "detected"  # trotz Kündigung weiter abgebucht – wieder sichtbar machen
                if old["price_change_ack"] is not None and old["price_change_ack"] != res["amount_cents"]:
                    data["price_change_ack"] = None
                db.update("contracts", "key", key, data)
            else:
                data.update({"key": key, "name": data["counterparty"], "status": "detected"})
                db.insert("contracts", data)
            ids = [t["id"] for t in group]
            db.execute(f"UPDATE transactions SET contract_key = ? WHERE id IN ({','.join('?' * len(ids))})", (key, *ids))
        for key, old in existing.items():
            if key in found or old["manual"]:
                continue
            touched = old["status"] in ("confirmed", "cancelled") or old["notes"] or old["customer_no"]
            if touched:
                db.update("contracts", "key", key, {"active": 0})
            else:
                db.execute("DELETE FROM contracts WHERE key = ?", (key,))
        _link_manual(db)
    return {"found": len(found)}


def _link_manual(db: Database) -> None:
    for c in db.query("SELECT * FROM contracts WHERE manual = 1"):
        pattern = norm(c["match_pattern"])
        if not pattern:
            continue
        rx = re.compile(r"(?<![a-z0-9])" + re.escape(pattern) + r"(?![a-z0-9])")
        sign = 1 if c["kind"] == "income" else -1
        rows = db.query("SELECT id, booking_date, amount_cents, counterparty, purpose FROM transactions WHERE amount_cents * ? > 0 "
                        "AND booking_date >= ?", (sign, (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()))
        hits = [r for r in rows if rx.search(norm(r["counterparty"])) or rx.search(norm(r["purpose"]))]
        if not hits:
            continue
        ids = [h["id"] for h in hits]
        db.execute(f"UPDATE transactions SET contract_key = ? WHERE id IN ({','.join('?' * len(ids))})", (c["key"], *ids))
        last = max(hits, key=lambda h: h["booking_date"])
        upd = {"last_date": last["booking_date"], "count": len(hits), "amount_cents": last["amount_cents"]}
        if c["interval"] in INTERVAL_BY_NAME:
            upd["next_due"] = next_after(date.fromisoformat(last["booking_date"]), c["interval"]).isoformat()
        db.update("contracts", "key", c["key"], upd)


def deadline_for(c: dict) -> str | None:
    if not c.get("contract_end") or not c.get("notice_months"):
        return None
    try:
        end = date.fromisoformat(c["contract_end"])
    except ValueError:
        return None
    return add_months(end, -int(c["notice_months"])).isoformat()


def enrich(c: dict) -> dict:
    c = dict(c)
    c["monthly_cents"] = int(round((c["amount_cents"] or 0) * monthly_factor(c["interval"])))
    c["price_change_cents"] = None
    if c.get("prev_amount_cents") is not None and c.get("price_change_ack") != c.get("amount_cents"):
        c["price_change_cents"] = c["amount_cents"] - c["prev_amount_cents"]
    c["deadline"] = deadline_for(c)
    c["days_to_deadline"] = (date.fromisoformat(c["deadline"]) - date.today()).days if c["deadline"] else None
    return c


def list_contracts(db: Database) -> list[dict]:
    rows = db.query(
        "SELECT k.*, c.name AS category_name, a.name AS account_name FROM contracts k LEFT JOIN categories c ON c.id = k.category_id "
        "LEFT JOIN accounts a ON a.id = k.account_id ORDER BY k.kind DESC, ABS(k.amount_cents) DESC"
    )
    return [enrich(r) for r in rows]


def is_running(c: dict, on: date) -> bool:
    """Ob der Vertrag an diesem Tag noch Zahlungen auslöst."""
    if c["status"] == "ignored" or not c["active"] and not c["manual"]:
        return False
    if c["status"] == "cancelled":
        eff = c.get("cancel_effective")
        if not eff or on > date.fromisoformat(eff):
            return False
    return True


def upcoming(db: Database, start: date, end: date, contracts: list[dict] | None = None) -> list[dict]:
    """Erwartete Zahlungen aus Verträgen zwischen start und end (inklusive)."""
    out = []
    for c in contracts if contracts is not None else list_contracts(db):
        if not c.get("next_due") or c["interval"] not in INTERVAL_BY_NAME:
            continue
        d = date.fromisoformat(c["next_due"])
        item = {"key": c["key"], "name": c["name"], "amount_cents": c["amount_cents"], "kind": c["kind"],
                "account_id": c["account_id"], "interval": c["interval"]}
        if d < start:
            # überfällig, aber noch aktiv: einmal als „demnächst" werten
            if (start - d).days <= 10 and is_running(c, start):
                out.append({**item, "date": start.isoformat(), "overdue": True})
            while d < start:
                d = next_after(d, c["interval"])
        guard = 0
        while d <= end and guard < 60:
            if is_running(c, d):
                out.append({**item, "date": d.isoformat(), "overdue": False})
            d = next_after(d, c["interval"])
            guard += 1
    out.sort(key=lambda x: (x["date"], x["amount_cents"]))
    return out
