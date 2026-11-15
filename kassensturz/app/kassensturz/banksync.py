"""Stand des Bankabrufs und Abruf auf Wunsch, für die Mobile-App.

Der Abruf von hier läuft wie der tägliche im Hintergrund: Enable Banking mit
laufender Freigabe und FinTS-Zugänge mit gespeicherter PIN. Verlangt eine Bank
eine TAN, endet der Auftrag mit einem Hinweis; die Eingabe bleibt der
Oberfläche in Home Assistant vorbehalten.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from . import fints_sync, openbanking, options, secrets_store
from .db import Database

# Banken erlauben nur wenige Abrufe am Tag. Aus der App höchstens einer in diesem Abstand.
COOLDOWN_MINUTES = 30
LAST_START_KEY = "mobile_sync_started"

_jobs: list = []
_lock = threading.Lock()


def _next_daily(now: datetime, sync_time: str) -> str:
    try:
        hour, minute = (int(p) for p in sync_time.split(":"))
    except ValueError:
        hour, minute = 6, 30
    planned = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if planned <= now:
        planned += timedelta(days=1)
    return planned.isoformat()


def sources(db: Database) -> list[dict]:
    """Alle Wege, auf denen Umsätze ohne Zutun ankommen, ohne Zugangsdaten."""
    out = []
    if openbanking.is_configured(db):
        for s in openbanking.list_sessions(db):
            if not s["accounts"]:
                state = "no_accounts"
            elif s["status"] != "active":
                state = "expired"
            elif (s["last_status"] or "ok") != "ok":
                state = "error"
            else:
                state = "ok"
            out.append({"id": f"eb:{s['id']}", "name": s["aspsp_name"], "last_sync": s["last_sync"], "state": state,
                        "days_left": s["days_left"], "accounts": len(s["accounts"]), "automatic": state in ("ok", "error")})
    for c in db.query("SELECT id, name, last_sync, last_status FROM connections ORDER BY id"):
        has_pin = secrets_store.has_pin(c["id"])
        accounts = int(db.scalar("SELECT COUNT(*) FROM accounts WHERE connection_id = ?", (c["id"],)) or 0)
        state = "needs_pin" if not has_pin else "error" if (c["last_status"] or "ok") != "ok" else "ok"
        out.append({"id": f"fints:{c['id']}", "name": c["name"], "last_sync": c["last_sync"], "state": state,
                    "days_left": None, "accounts": accounts, "automatic": has_pin})
    return out


def _run_state() -> dict:
    with _lock:
        jobs = list(_jobs)
    if not jobs:
        return {"state": "idle", "added": 0, "errors": []}
    running = any(j.state in ("running", "waiting") for j in jobs)
    errors = [{"name": j.name, "message": j.error or "Der Abruf wurde abgebrochen."}
              for j in jobs if j.state in ("error", "cancelled")]
    added = sum(int((j.result or {}).get("added") or 0) for j in jobs if j.state == "done")
    return {"state": "running" if running else "error" if errors and len(errors) == len(jobs) else "done",
            "added": added, "errors": errors}


def status(db: Database, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    items = sources(db)
    synced = sorted(s["last_sync"] for s in items if s["last_sync"])
    started = db.get_setting(LAST_START_KEY)
    wait = 0
    if started:
        try:
            left = COOLDOWN_MINUTES * 60 - (now - datetime.fromisoformat(started)).total_seconds()
            wait = max(0, int(left // 60) + (1 if left % 60 else 0)) if left > 0 else 0
        except (TypeError, ValueError):
            wait = 0
    run = _run_state()
    automatic = [s for s in items if s["automatic"]]
    return {
        "sources": items,
        # Der älteste Stand zählt: Erst wenn alle Banken abgerufen sind, ist alles aktuell.
        "last_sync": synced[0] if synced and len(synced) == len(items) else None,
        "newest_sync": synced[-1] if synced else None,
        "next_sync": _next_daily(now, options.load().get("sync_time") or "06:30") if automatic else None,
        "run": run,
        "can_start": bool(automatic) and run["state"] != "running" and wait == 0,
        "wait_minutes": wait,
    }


class SyncRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def start(db: Database, psu: dict | None = None, on_done=None, now: datetime | None = None) -> dict:
    """Stößt den Abruf aller Quellen an, die ohne Eingabe laufen."""
    now = now or datetime.now()
    current = status(db, now)
    if current["run"]["state"] == "running":
        return current
    if not any(s["automatic"] for s in current["sources"]):
        raise SyncRefused("nothing_to_sync", "Es ist keine Bank eingerichtet, die sich ohne Eingabe abrufen lässt.")
    if current["wait_minutes"]:
        minutes = current["wait_minutes"]
        raise SyncRefused("too_soon", f"Der letzte Abruf aus der App ist noch keine {COOLDOWN_MINUTES} Minuten her. "
                                      f"In {minutes} {'Minute' if minutes == 1 else 'Minuten'} geht es wieder.")
    db.set_setting(LAST_START_KEY, now.replace(microsecond=0).isoformat())
    jobs = []
    for s in current["sources"]:
        if not s["automatic"]:
            continue
        kind, _, raw = s["id"].partition(":")
        try:
            if kind == "eb":
                # Der Mensch hat den Abruf gerade selbst angestoßen; das darf die Bank wissen.
                jobs.append(openbanking.start_sync(int(raw), psu=psu, on_done=on_done))
            else:
                jobs.append(fints_sync.start(int(raw), None, background=True, on_done=on_done))
        except fints_sync.UserFacingError:
            continue
    with _lock:
        _jobs[:] = jobs
    return status(db, now)


def wait_for_tests(timeout: float = 5.0) -> None:
    end = time.time() + timeout
    while time.time() < end and _run_state()["state"] == "running":
        time.sleep(0.01)
