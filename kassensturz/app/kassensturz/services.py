"""Neuberechnung nach Änderungen, HA-Abgleich, täglicher Abruf."""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta

from . import analytics, contracts, fints_sync, ha, inbox, ledger, openbanking, options, secrets_store
from .db import Database, get_db
from .util import euro

log = logging.getLogger("kassensturz.services")


def build_summary(db: Database) -> dict:
    cons = contracts.list_contracts(db)
    fc = analytics.forecast(db)
    today = date.today()
    month = analytics.month_stats(db, today.strftime("%Y-%m"))
    running = [c for c in cons if c["status"] != "ignored" and contracts.is_running(c, today)]
    return {
        "forecast": fc,
        "accounts": ledger.accounts_with_balance(db),
        "budgets": analytics.budgets(db),
        "month": month,
        "fixed_monthly_cents": analytics.fixed_costs_monthly(running),
        "contract_count": sum(1 for c in running if c["kind"] == "expense"),
        "next_payment": next((u for u in fc["upcoming"] if u["amount_cents"] < 0), None),
        "contracts": cons,
    }


def alerts(db: Database, summary: dict) -> list[dict]:
    """Hinweise für die Übersicht (und Grundlage der Benachrichtigungen)."""
    out = []
    opts = options.load()
    fc = summary["forecast"]
    threshold = int(opts.get("warn_threshold") or 0) * 100
    today = date.today()
    if fc["accounts"] and fc["low_point"]["cents"] < threshold:
        d = date.fromisoformat(fc["low_point"]["date"])
        out.append({"key": f"low:{today.isocalendar()[0]}-{today.isocalendar()[1]}", "level": "critical",
                    "title": "Kontostand wird knapp",
                    "text": f"Die Prognose fällt am {d.strftime('%d.%m.')} auf {euro(fc['low_point']['cents'])}."})
    for c in summary["contracts"]:
        if c["status"] == "ignored":
            continue
        ch = c.get("price_change_cents")
        recent = c.get("last_date") and (today - date.fromisoformat(c["last_date"])).days <= 40
        if ch and recent and c["kind"] == "expense" and ch < 0:
            out.append({"key": f"price:{c['key']}:{c['amount_cents']}", "level": "warning", "contract": c["key"],
                        "title": f"{c['name']} wird teurer",
                        "text": f"Zuletzt {euro(-c['amount_cents'])} statt {euro(-c['prev_amount_cents'])} – "
                                f"{euro(-ch * round(12 * contracts.monthly_factor(c['interval'])))} mehr im Jahr."})
        dl = c.get("days_to_deadline")
        if dl is not None and 0 <= dl <= 21 and c["status"] != "cancelled":
            out.append({"key": f"deadline:{c['key']}:{c['deadline']}", "level": "warning", "contract": c["key"],
                        "title": f"Kündigungsfrist {c['name']}",
                        "text": f"Kündigen bis {date.fromisoformat(c['deadline']).strftime('%d.%m.%Y')} – noch {dl} Tage."})
    for b in summary["budgets"]:
        if b["state"] == "over":
            out.append({"key": f"budget:{b['category_id']}:{today:%Y-%m}", "level": "warning", "title": f"Budget {b['name']} überschritten",
                        "text": f"{euro(b['spent_cents'])} von {euro(b['budget_cents'])} ausgegeben."})
    for s in openbanking.list_sessions(db):
        if s["status"] == "expired" or (s["days_left"] is not None and s["days_left"] < 0):
            out.append({"key": f"eb-expired:{s['id']}:{s['valid_until']}", "level": "warning", "eb": s["id"],
                        "title": f"Freigabe für {s['aspsp_name']} abgelaufen",
                        "text": "Neue Umsätze kommen erst wieder, wenn du die Freigabe erneuerst."})
        elif s["days_left"] is not None and s["days_left"] <= 7:
            out.append({"key": f"eb-expiring:{s['id']}:{s['valid_until']}", "level": "warning", "eb": s["id"],
                        "title": f"Freigabe für {s['aspsp_name']} läuft ab",
                        "text": f"Noch {max(0, s['days_left'])} Tage. Erneuern dauert eine Minute in der Banking-App."})
    pending = db.scalar("SELECT COUNT(*) FROM inbox")
    if pending:
        out.append({"key": f"inbox:{pending}", "level": "info", "inbox": True,
                    "title": "Dateien im Eingangsordner warten",
                    "text": f"{pending} {'Datei braucht' if pending == 1 else 'Dateien brauchen'} eine Zuordnung zu einem Konto."})
    for a in summary["accounts"]:
        if a["in_forecast"] and not a["balance_known"] and a["tx_count"]:
            out.append({"key": f"balance:{a['id']}", "level": "info", "title": f"Kontostand für {a['name']} fehlt",
                        "text": "Trag den aktuellen Stand einmal ein, damit Prognose und Summe stimmen.", "account": a["id"]})
    return out


def refresh(db: Database | None = None, notify: bool = True) -> dict:
    db = db or get_db()
    contracts.detect(db)
    summary = build_summary(db)
    opts = options.load()
    if opts.get("sensors", True):
        ha.push_sensors(summary)
    if notify:
        for a in alerts(db, summary):
            if a["level"] in ("critical", "warning"):
                ha.notify(db, a["key"], f"Kassensturz: {a['title']}", a["text"], opts.get("notify_service"))
    return summary


# --- Entprellte Neuberechnung ------------------------------------------------------
_pending = threading.Event()


def schedule_refresh() -> None:
    _pending.set()


def _refresh_loop() -> None:
    while True:
        _pending.wait()
        time.sleep(1.5)
        _pending.clear()
        try:
            refresh()
        except Exception:  # noqa: BLE001
            log.exception("Neuberechnung fehlgeschlagen")


def _scheduler_loop() -> None:
    last_sync_day = None
    last_push = 0.0
    while True:
        try:
            opts = options.load()
            now = datetime.now()
            if now.strftime("%H:%M") >= (opts.get("sync_time") or "06:30") and last_sync_day != now.date():
                last_sync_day = now.date()
                run_daily_sync()
            if inbox.folder():
                res = inbox.scan(get_db())
                if res["imported"]:
                    schedule_refresh()
            if time.time() - last_push > 900:
                last_push = time.time()
                schedule_refresh()
        except Exception:  # noqa: BLE001
            log.exception("Zeitplan-Fehler")
        time.sleep(30)


def run_daily_sync() -> None:
    db = get_db()
    for conn in db.query("SELECT * FROM connections"):
        if not secrets_store.has_pin(conn["id"]):
            continue
        last = conn["last_sync"]
        if last and last[:10] == date.today().isoformat():
            continue
        job = fints_sync.start(conn["id"], None, background=True, on_done=schedule_refresh)
        threading.Thread(target=_watch_background_job, args=(job,), daemon=True).start()
    if openbanking.is_configured(db):
        for s in openbanking.list_sessions(db):
            if s["status"] != "active" or (s["last_sync"] or "")[:10] == date.today().isoformat():
                continue
            job = openbanking.start_sync(s["id"], background=True, on_done=schedule_refresh)
            threading.Thread(target=_watch_background_job, args=(job,), daemon=True).start()


def _watch_background_job(job) -> None:
    while job.state in ("running", "waiting"):
        time.sleep(5)
    if job.state == "error":
        db = get_db()
        ha.notify(db, f"sync:{job.connection_id}:{date.today()}", "Kassensturz: Abruf braucht dich",
                  f"{job.name}: {job.error}", options.load().get("notify_service"))


def start_background() -> None:
    threading.Thread(target=_refresh_loop, name="refresh", daemon=True).start()
    threading.Thread(target=_scheduler_loop, name="scheduler", daemon=True).start()


def tomorrow() -> date:
    return date.today() + timedelta(days=1)
