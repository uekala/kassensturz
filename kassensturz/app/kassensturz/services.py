"""Neuberechnung nach Änderungen, HA-Abgleich, täglicher Abruf."""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta

from . import analytics, backup, contracts, fints_sync, ha, inbox, ledger, openbanking, options, secrets_store
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
    for a in db.query("SELECT id, name FROM accounts WHERE archived = 0"):
        drift = ledger.balance_drift(db, a["id"], today)
        if drift:
            since = date.fromisoformat(drift["since"]).strftime("%d.%m.")
            what = ("Die Bank zeigt {} mehr, als die abgerufenen Buchungen erklären" if drift["cents"] > 0
                    else "Die Bank zeigt {} weniger, als die abgerufenen Buchungen erklären").format(euro(abs(drift["cents"])))
            out.append({"key": f"drift:{a['id']}:{drift['cents']}", "level": "warning",
                        "title": f"Kontostand {a['name']} passt nicht",
                        "text": f"{what} (seit {since}). Vermutlich fehlt eine Buchung oder ist doppelt."})
    for a in db.query("SELECT id, name, kind, matures_on FROM accounts WHERE archived = 0 AND matures_on IS NOT NULL"):
        if a["kind"] not in ledger.MATURING_KINDS:
            continue
        try:
            due = date.fromisoformat(a["matures_on"])
        except ValueError:
            continue
        left = (due - today).days
        if 0 <= left <= 30:
            what = "Festgeld wird fällig" if a["kind"] == "festgeld" else "Kredit läuft aus"
            when = "heute" if left == 0 else "morgen" if left == 1 else f"in {left} Tagen"
            out.append({"key": f"maturity:{a['id']}:{a['matures_on']}", "level": "warning",
                        "title": f"{what}: {a['name']}", "text": f"Am {due.strftime('%d.%m.%Y')}, {when}."})
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
        if (dl is not None and c["kind"] == "expense" and contracts.is_running(c, today)
                and c["status"] != "cancelled"):
            # Jede Stufe wird genau einmal pro Vertrag und Frist gemeldet.
            # Der vorhandene notices-Speicher verhindert Wiederholungen bei jedem Refresh.
            if dl < 0:
                stage, level = "overdue", "critical"
                message = f"Die Kündigungsfrist endete am {date.fromisoformat(c['deadline']).strftime('%d.%m.%Y')}. Bitte Vertragsstatus prüfen."
            else:
                offsets = options.cancellation_reminder_days()
                threshold = next((value for value in offsets if dl <= value), None)
                if threshold is None:
                    stage = None
                else:
                    stage = f"{threshold}d"
                    level = "critical" if threshold == min(offsets) else "warning"
                    timing = "Noch" if threshold == max(offsets) else "Nur noch"
                    message = f"{timing} {dl} Tage. Spätestens kündigen bis {date.fromisoformat(c['deadline']).strftime('%d.%m.%Y')}."
            if stage:
                out.append({"key": f"deadline:{stage}:{c['key']}:{c['deadline']}", "level": level,
                            "contract": c["key"], "title": f"Kündigungsfrist {c['name']}", "text": message})
    # Remind about cancellation events that were not explicitly confirmed as sent.
    # The stable event key prevents repeats during the regular refresh cycle.
    pending_events = db.query(
        "SELECT e.id, e.contract_key, e.status, e.prepared_at, c.name "
        "FROM cancellation_events e JOIN contracts c ON c.key = e.contract_key "
        "WHERE e.status IN ('prepared', 'handed_off') AND c.status NOT IN ('cancelled', 'ignored')"
    )
    now = datetime.now()
    for event in pending_events:
        try:
            prepared_at = datetime.fromisoformat(event["prepared_at"])
        except (TypeError, ValueError):
            continue
        age = now - prepared_at
        if age < timedelta(hours=24):
            continue
        age_days = max(1, age.days)
        action = "an die Mail-App übergeben" if event["status"] == "handed_off" else "vorbereitet"
        out.append({
            "key": f"cancellation-pending:{event['id']}",
            "level": "warning",
            "contract": event["contract_key"],
            "title": f"Kündigung noch nicht bestätigt: {event['name']}",
            "text": f"Vor {age_days} Tagen {action}. Bitte prüfen, ob die Kündigung tatsächlich versendet wurde.",
        })
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


# Quellen, die ohne dein Zutun Buchungen liefern. Was du selbst importierst oder anlegst,
# kennst du schon und wird nicht gemeldet.
AUTO_SOURCES = ("fints", "openbanking", "ordner")
TX_NOTICE_KEY = "notified_tx_id"
TX_NOTICE_LIST = 5
TX_NOTICE_MAX_LISTED = 20


def _tx_label(row: dict) -> str:
    text = (row.get("counterparty") or row.get("booking_text") or row.get("purpose") or "Buchung").strip()
    text = " ".join(text.split())
    return text if len(text) <= 40 else text[:39] + "…"


def new_transactions_notice(db: Database) -> dict | None:
    """Neue Buchungen aus dem automatischen Abruf seit der letzten Meldung.

    Merkt sich die höchste gemeldete Buchungs-ID. Beim ersten Lauf wird nur der Stand
    festgehalten, damit ein Update keine Meldung über den ganzen Bestand auslöst."""
    max_id = int(db.scalar("SELECT COALESCE(MAX(id), 0) FROM transactions") or 0)
    seen = db.get_setting(TX_NOTICE_KEY)
    if seen is None:
        db.set_setting(TX_NOTICE_KEY, max_id)
        return None
    seen = int(seen)
    if max_id <= seen:
        if max_id < seen:  # Buchungen gelöscht: Stand zurücksetzen
            db.set_setting(TX_NOTICE_KEY, max_id)
        return None
    marks = ",".join("?" for _ in AUTO_SOURCES)
    rows = db.query(
        f"""SELECT t.id, t.booking_date, t.amount_cents, t.counterparty, t.booking_text, t.purpose, a.name AS account
            FROM transactions t JOIN accounts a ON a.id = t.account_id
            WHERE t.id > ? AND t.source IN ({marks})
            ORDER BY t.booking_date DESC, t.id DESC""",
        (seen, *AUTO_SOURCES),
    )
    db.set_setting(TX_NOTICE_KEY, max_id)
    if not rows:
        return None
    count = len(rows)
    title = "Kassensturz: neue Buchung" if count == 1 else f"Kassensturz: {count} neue Buchungen"
    if count > TX_NOTICE_MAX_LISTED:
        accounts = sorted({r["account"] for r in rows})
        message = f"{count} Buchungen auf {', '.join(accounts)} abgerufen."
    else:
        lines = [f"{'+' if r['amount_cents'] > 0 else ''}{euro(r['amount_cents'])} {_tx_label(r)} ({r['account']})" for r in rows[:TX_NOTICE_LIST]]
        if count > TX_NOTICE_LIST:
            rest = count - TX_NOTICE_LIST
            lines.append(f"und {rest} {'weitere' if rest > 1 else 'weitere Buchung'}")
        message = "\n".join(lines)
    return {"key": f"tx:{max_id}", "title": title, "message": message, "count": count}


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
        notice = new_transactions_notice(db)
        if notice and opts.get("notify_new_transactions", True):
            ha.notify(db, notice["key"], notice["title"], notice["message"], opts.get("notify_service"))
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


# Zeitpunkt des letzten Durchlaufs; /healthz meldet, wenn der Zeitplan steht.
_last_tick = time.monotonic()


def scheduler_age_seconds() -> float:
    return time.monotonic() - _last_tick


def _scheduler_loop() -> None:
    global _last_tick
    last_sync_day = None
    last_push = 0.0
    backup_retry_at = 0.0
    while True:
        _last_tick = time.monotonic()
        if time.monotonic() >= backup_retry_at:
            try:
                backup.run_if_due(get_db())
            except Exception:  # noqa: BLE001
                # Nicht alle 30 Sekunden erneut versuchen und protokollieren.
                backup_retry_at = time.monotonic() + 3600
                log.exception("Sicherungskopie fehlgeschlagen, nächster Versuch in einer Stunde")
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
    global _last_tick
    _last_tick = time.monotonic()
    threading.Thread(target=_refresh_loop, name="refresh", daemon=True).start()
    threading.Thread(target=_scheduler_loop, name="scheduler", daemon=True).start()


def tomorrow() -> date:
    return date.today() + timedelta(days=1)
