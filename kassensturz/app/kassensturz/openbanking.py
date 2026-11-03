"""Open Banking über Enable Banking (PSD2-Kontoinformationsdienst).

Im „eingeschränkten Produktivmodus“ ist Enable Banking für eigene Konten kostenlos: Man legt dort eine App an,
verknüpft die eigenen Konten im Control Panel und kann sie danach über die API lesen."""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import requests

from . import ledger, secrets_store
from .db import Database, get_db, now_iso
from .fints_sync import JOBS, Job, UserFacingError
from .util import clean_purpose, parse_amount

log = logging.getLogger("kassensturz.openbanking")

API = os.environ.get("KASSENSTURZ_EB_API", "https://api.enablebanking.com")
DEFAULT_REDIRECT = "https://enablebanking.com/"
MAX_CONSENT_DAYS = 180
KEY_NAME = "eb_private_key"


class EBError(UserFacingError):
    def __init__(self, message: str, status: int = 0, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code

    @property
    def session_gone(self) -> bool:
        c = (self.code or "").upper()
        return "SESSION" in c and any(w in c for w in ("EXPIRED", "CLOSED", "INVALID", "NOT_FOUND", "DOES_NOT_EXIST", "REVOKED"))


# --- Zugangsdaten und Anfragen -----------------------------------------------------------

def get_config(db: Database) -> dict:
    return {
        "app_id": db.get_setting("eb_app_id", "") or "",
        "redirect_url": db.get_setting("eb_redirect_url", "") or DEFAULT_REDIRECT,
        "has_key": bool(secrets_store.get_secret(KEY_NAME)),
    }


def is_configured(db: Database) -> bool:
    c = get_config(db)
    return bool(c["app_id"] and c["has_key"])


_token_cache: dict = {}


def _token(app_id: str, pem: str) -> str:
    import jwt

    cached = _token_cache.get(app_id)
    if cached and cached[1] > time.time() + 60 and cached[2] == hash(pem):
        return cached[0]
    iat = int(time.time())
    try:
        token = jwt.encode({"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": iat, "exp": iat + 3600},
                           pem, algorithm="RS256", headers={"kid": app_id, "typ": "JWT"})
    except Exception as exc:  # noqa: BLE001
        raise EBError("Der private Schlüssel ließ sich nicht lesen. Lade die .pem-Datei hoch, die Enable Banking beim "
                      "Anlegen der App heruntergeladen hat.") from exc
    _token_cache[app_id] = (token, iat + 3600, hash(pem))
    return token


def _explain(status: int, data: dict | None, text: str) -> EBError:
    data = data or {}
    code = str(data.get("error") or data.get("code") or "")
    msg = str(data.get("message") or data.get("detail") or text or "")[:300]
    if status == 401:
        return EBError("Enable Banking lehnt die Anmeldung ab. Prüfe App-ID und Schlüssel.", status, code)
    if status == 429:
        return EBError("Die Bank erlaubt ohne dich nur wenige Abrufe pro Tag. Versuch es später noch einmal.", status, code)
    err = EBError(f"Enable Banking meldet einen Fehler ({status}): {msg}", status, code)
    if err.session_gone:
        return EBError("Die Freigabe bei der Bank ist abgelaufen oder wurde widerrufen. Erneuere sie unter Konten.", status, code)
    return err


def call(method: str, path: str, *, db: Database | None = None, params=None, body=None, psu: dict | None = None,
         app_id: str | None = None, pem: str | None = None):
    db = db or get_db()
    app_id = app_id or get_config(db)["app_id"]
    pem = pem or secrets_store.get_secret(KEY_NAME)
    if not app_id or not pem:
        raise EBError("Open Banking ist noch nicht eingerichtet.")
    headers = {"Authorization": f"Bearer {_token(app_id, pem)}", "Accept": "application/json"}
    if psu:
        if psu.get("ip"):
            headers["Psu-Ip-Address"] = psu["ip"]
        if psu.get("ua"):
            headers["Psu-User-Agent"] = psu["ua"][:200]
    try:
        r = requests.request(method, f"{API}{path}", params=params, json=body, headers=headers, timeout=40)
    except requests.RequestException as exc:
        raise EBError(f"Enable Banking ist nicht erreichbar: {exc}") from exc
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = None
    if r.status_code >= 400:
        raise _explain(r.status_code, data if isinstance(data, dict) else None, r.text)
    return data


def save_config(db: Database, app_id: str, pem: str | None, redirect_url: str | None) -> dict:
    app_id = (app_id or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", app_id):
        raise EBError("Die App-ID ist eine UUID wie aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.")
    pem = (pem or "").strip() or secrets_store.get_secret(KEY_NAME)
    if not pem or "PRIVATE KEY" not in pem:
        raise EBError("Bitte die .pem-Datei mit dem privaten Schlüssel hochladen.")
    info = call("GET", "/application", db=db, app_id=app_id, pem=pem)
    secrets_store.set_secret(KEY_NAME, pem)
    db.set_setting("eb_app_id", app_id)
    db.set_setting("eb_redirect_url", (redirect_url or "").strip() or DEFAULT_REDIRECT)
    _token_cache.clear()
    _aspsp_cache.clear()
    return info or {}


def remove_config(db: Database) -> None:
    secrets_store.delete_secret(KEY_NAME)
    db.set_setting("eb_app_id", "")
    _token_cache.clear()


# --- Banken und Freigabe --------------------------------------------------------------------

_aspsp_cache: dict = {}


def aspsps(db: Database, country: str = "DE") -> list[dict]:
    country = (country or "DE").upper()
    cached = _aspsp_cache.get(country)
    if cached and cached[0] > time.time():
        return cached[1]
    data = call("GET", "/aspsps", db=db, params={"country": country, "psu_type": "personal", "service": "AIS"})
    out = []
    for a in (data or {}).get("aspsps", []):
        out.append({"name": a.get("name"), "country": a.get("country") or country, "logo": a.get("logo"),
                    "max_consent_seconds": a.get("maximum_consent_validity"), "psu_types": a.get("psu_types") or [],
                    "beta": bool(a.get("beta"))})
    out.sort(key=lambda a: (a["name"] or "").lower())
    _aspsp_cache[country] = (time.time() + 12 * 3600, out)
    return out


_pending: dict[str, dict] = {}


def start_auth(db: Database, aspsp_name: str, country: str, renew_id: int | None = None, psu: dict | None = None) -> dict:
    if not aspsp_name:
        raise EBError("Bitte eine Bank auswählen.")
    max_secs = None
    try:
        for a in aspsps(db, country):
            if a["name"] == aspsp_name:
                max_secs = a["max_consent_seconds"]
                break
    except EBError:
        pass
    days = MAX_CONSENT_DAYS
    if max_secs:
        days = max(1, min(days, int(max_secs) // 86400))
    valid_until = (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()
    state = uuid.uuid4().hex
    body = {"access": {"valid_until": valid_until}, "aspsp": {"name": aspsp_name, "country": country.upper()},
            "state": state, "redirect_url": get_config(db)["redirect_url"], "psu_type": "personal"}
    data = call("POST", "/auth", db=db, body=body, psu=psu)
    url = (data or {}).get("url")
    if not url:
        raise EBError("Enable Banking hat keinen Freigabe-Link geliefert.")
    for s in [k for k, v in _pending.items() if time.time() - v["created"] > 3600]:
        _pending.pop(s, None)
    _pending[state] = {"aspsp": aspsp_name, "country": country.upper(), "renew": renew_id, "created": time.time(), "days": days}
    return {"url": url, "state": state, "days": days}


def parse_return(text: str) -> tuple[str | None, str | None]:
    """Liest Code und State aus der Rückkehr-Adresse (oder nimmt den reinen Code)."""
    t = (text or "").strip()
    if not t:
        raise EBError("Bitte die Adresse einfügen, auf der du nach der Freigabe gelandet bist.")
    if "?" in t or "=" in t:
        q = parse_qs(urlparse(t if "://" in t else "https://x/?" + t.split("?", 1)[-1]).query)
        if q.get("error"):
            desc = (q.get("error_description") or q.get("error"))[0]
            raise EBError(f"Die Bank hat die Freigabe nicht erteilt: {desc}")
        code = (q.get("code") or [None])[0]
        state = (q.get("state") or [None])[0]
        if not code:
            raise EBError("In der Adresse steht kein Freigabe-Code. Kopiere die komplette Adresse aus der Adresszeile.")
        return code, state
    return t, None


def complete_auth(db: Database, text: str, psu: dict | None = None) -> dict:
    code, state = parse_return(text)
    pend = _pending.pop(state, None) if state else None
    if not pend and not state and len(_pending) == 1:
        state, pend = _pending.popitem()
    if not pend:
        raise EBError("Diese Freigabe gehört zu keinem offenen Vorgang. Starte „Bank verbinden“ bitte noch einmal.")
    data = call("POST", "/sessions", db=db, body={"code": code}, psu=psu) or {}
    session_id = data.get("session_id")
    if not session_id:
        raise EBError("Enable Banking hat keine Sitzung angelegt.")
    accounts = data.get("accounts") or []
    if accounts and isinstance(accounts[0], str):
        accounts = [dict(call("GET", f"/accounts/{uid}/details", db=db) or {}, uid=uid) for uid in accounts]
    valid_until = ((data.get("access") or {}).get("valid_until")
                   or (datetime.now(timezone.utc) + timedelta(days=pend["days"])).isoformat())
    aspsp = (data.get("aspsp") or {}).get("name") or pend["aspsp"]
    with db.tx():
        if pend.get("renew"):
            eb_id = pend["renew"]
            old = db.one("SELECT session_id FROM eb_sessions WHERE id = ?", (eb_id,))
            db.update("eb_sessions", "id", eb_id, {"session_id": session_id, "valid_until": valid_until, "status": "active",
                                                   "last_status": None})
        else:
            old = None
            eb_id = db.insert("eb_sessions", {"session_id": session_id, "aspsp_name": aspsp, "aspsp_country": pend["country"],
                                              "valid_until": valid_until, "status": "active", "created": now_iso()})
        linked = link_accounts(db, eb_id, aspsp, accounts)
    if old and old.get("session_id") and old["session_id"] != session_id:
        try:
            call("DELETE", f"/sessions/{old['session_id']}", db=db)
        except EBError:
            pass
    return {"id": eb_id, "aspsp": aspsp, "valid_until": valid_until, "accounts": linked}


SETTLEMENT_BY_BANK = [("paypal", "paypal", "paypal"), ("american express", "kreditkarte", "american express,amex"),
                      ("amex", "kreditkarte", "american express,amex"), ("revolut", "giro", "revolut"), ("n26", "giro", "n26"),
                      ("klarna", "sonstiges", "klarna"), ("advanzia", "kreditkarte", "advanzia")]


def _kind_for(account: dict, aspsp: str) -> tuple[str, str | None]:
    low = (aspsp or "").lower()
    for word, kind, settle in SETTLEMENT_BY_BANK:
        if word in low:
            if account.get("cash_account_type") == "CARD":
                kind = "kreditkarte"
            return kind, settle
    t = account.get("cash_account_type")
    if t == "CARD":
        return "kreditkarte", None
    if t in ("SVGS", "MOMA", "ONDP"):
        return "tagesgeld", None
    return "giro", None


def link_accounts(db: Database, eb_id: int, aspsp: str, accounts: list[dict]) -> list[dict]:
    out = []
    for a in accounts:
        uid = a.get("uid")
        if not uid:
            continue
        ident = a.get("identification_hash")
        acc_id = a.get("account_id") or {}
        iban = (acc_id.get("iban") or "").replace(" ", "").upper() or None
        other = ((acc_id.get("other") or {}).get("identification") or "").strip()
        row = None
        if ident:
            row = db.one("SELECT * FROM accounts WHERE eb_ident = ?", (ident,))
        if not row and iban:
            row = db.one("SELECT * FROM accounts WHERE iban = ? ORDER BY archived, id LIMIT 1", (iban,))
        if row:
            db.update("accounts", "id", row["id"], {"eb_session_id": eb_id, "eb_uid": uid, "eb_ident": ident or row.get("eb_ident")})
            out.append({"id": row["id"], "name": row["name"], "new": False})
            continue
        kind, settle = _kind_for(a, aspsp)
        label = (a.get("name") or a.get("product") or "").strip()
        suffix = (iban or other)[-4:] if (iban or other) else ""
        name = aspsp if not label or label.lower() in aspsp.lower() else f"{aspsp} {label}"
        if suffix and db.one("SELECT id FROM accounts WHERE name = ?", (name,)):
            name = f"{name} …{suffix}"
        aid = db.insert("accounts", {
            "name": name[:60], "kind": kind, "iban": iban, "bank": aspsp, "currency": a.get("currency") or "EUR",
            "settlement_pattern": settle, "in_forecast": 0 if kind == "tagesgeld" else 1, "created": now_iso(),
            "eb_session_id": eb_id, "eb_uid": uid, "eb_ident": ident,
        })
        out.append({"id": aid, "name": name, "new": True})
    if out:
        from . import categorize
        categorize.recategorize(db)
    return out


def delete_session(db: Database, eb_id: int) -> None:
    row = db.one("SELECT * FROM eb_sessions WHERE id = ?", (eb_id,))
    if not row:
        return
    if row["session_id"] and row["status"] == "active":
        try:
            call("DELETE", f"/sessions/{row['session_id']}", db=db)
        except EBError as exc:
            log.info("Sitzung ließ sich nicht löschen: %s", exc)
    with db.tx():
        db.execute("UPDATE accounts SET eb_session_id = NULL, eb_uid = NULL WHERE eb_session_id = ?", (eb_id,))
        db.execute("DELETE FROM eb_sessions WHERE id = ?", (eb_id,))


def list_sessions(db: Database) -> list[dict]:
    out = []
    now = datetime.now(timezone.utc)
    for s in db.query("SELECT * FROM eb_sessions ORDER BY id"):
        s.pop("session_id", None)
        s["accounts"] = db.query("SELECT id, name FROM accounts WHERE eb_session_id = ?", (s["id"],))
        s["days_left"] = None
        if s["valid_until"]:
            try:
                vu = datetime.fromisoformat(s["valid_until"].replace("Z", "+00:00"))
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                s["days_left"] = (vu - now).days
                if vu < now and s["status"] == "active":
                    s["status"] = "expired"
            except ValueError:
                pass
        out.append(s)
    return out


# --- Umsätze --------------------------------------------------------------------------------

def row_from_eb(t: dict) -> dict | None:
    status = t.get("status")
    if status and status != "BOOK":
        return None
    amt = t.get("transaction_amount") or {}
    if (amt.get("currency") or "EUR") != "EUR":
        return None
    cents = parse_amount(amt.get("amount"))
    if cents is None or cents == 0:
        return None
    debit = (t.get("credit_debit_indicator") or ("DBIT" if cents < 0 else "CRDT")) == "DBIT"
    cents = -abs(cents) if debit else abs(cents)
    bdate = t.get("booking_date") or t.get("value_date") or t.get("transaction_date")
    if not bdate:
        return None
    party = (t.get("creditor") if debit else t.get("debtor")) or {}
    acct = (t.get("creditor_account") if debit else t.get("debtor_account")) or {}
    lines = [str(x).strip() for x in (t.get("remittance_information") or []) if str(x).strip()]
    name = (party.get("name") or "").strip()
    if not name and lines:
        name, lines = lines[0], lines[1:]
    purpose, sepa = clean_purpose(" ".join(lines))
    btc = t.get("bank_transaction_code") or {}
    iban = (acct.get("iban") or "").replace(" ", "").upper()
    return {
        "booking_date": str(bdate)[:10], "value_date": str(t.get("value_date") or bdate)[:10], "amount_cents": cents,
        "currency": "EUR", "counterparty": name[:140] or None, "counterparty_iban": iban or None, "purpose": purpose[:400] or None,
        "booking_text": (btc.get("description") or btc.get("code") or "")[:80] or None,
        "creditor_id": sepa.get("CRED") or None, "mandate_ref": sepa.get("MREF") or None,
        "end_to_end": sepa.get("EREF") or None, "balance_cents": None, "own_iban": None,
    }


BALANCE_ORDER = ["CLBD", "ITBD", "XPCD", "ITAV", "CLAV", "OPBD", "PRCD", "FWAV", "OTHR", "INFO"]


def pick_balance(balances: list[dict]) -> tuple[int, str] | None:
    best = None
    for b in balances or []:
        typ = b.get("balance_type") or "OTHR"
        rank = BALANCE_ORDER.index(typ) if typ in BALANCE_ORDER else len(BALANCE_ORDER)
        amt = b.get("balance_amount") or {}
        cents = parse_amount(amt.get("amount"))
        if cents is None:
            continue
        if b.get("credit_debit_indicator") == "DBIT" and cents > 0:
            cents = -cents
        day = (b.get("reference_date") or (b.get("last_change_date_time") or "")[:10] or date.today().isoformat())
        if best is None or rank < best[0]:
            best = (rank, cents, day)
    return (best[1], best[2]) if best else None


def fetch_transactions(db: Database, uid: str, date_from: date, psu: dict | None) -> list[dict]:
    params = {"date_from": date_from.isoformat()}
    out: list[dict] = []
    for _ in range(300):
        data = call("GET", f"/accounts/{uid}/transactions", db=db, params=params, psu=psu) or {}
        out.extend(data.get("transactions") or [])
        key = data.get("continuation_key")
        if not key:
            break
        params = {"date_from": date_from.isoformat(), "continuation_key": key}
    return out


def _sync(job: Job, eb_id: int, psu: dict | None) -> dict:
    db = get_db()
    sess = db.one("SELECT * FROM eb_sessions WHERE id = ?", (eb_id,))
    if not sess:
        raise EBError("Bankverbindung nicht gefunden.")
    vu = sess["valid_until"]
    if vu:
        try:
            end = datetime.fromisoformat(vu.replace("Z", "+00:00"))
            if (end.tzinfo and end < datetime.now(timezone.utc)) or (not end.tzinfo and end < datetime.now()):
                db.update("eb_sessions", "id", eb_id, {"status": "expired"})
                raise EBError("Die Freigabe bei der Bank ist abgelaufen. Erneuere sie unter Konten.")
        except ValueError:
            pass
    summary = {"accounts": [], "added": 0, "skipped": 0}
    accounts = db.query("SELECT * FROM accounts WHERE eb_session_id = ? AND eb_uid IS NOT NULL AND archived = 0", (eb_id,))
    if not accounts:
        raise EBError("Mit dieser Freigabe sind keine Konten verknüpft.")
    try:
        for acc in accounts:
            job.set_step(f"Lade Umsätze für {acc['name']} …")
            last = db.scalar("SELECT MAX(booking_date) FROM transactions WHERE account_id = ? AND source = 'openbanking'", (acc["id"],))
            if last:
                start = date.fromisoformat(last) - timedelta(days=7)
                txs = fetch_transactions(db, acc["eb_uid"], start, psu)
            else:
                start = date.today() - timedelta(days=int(sess["history_days"] or 365))
                try:
                    txs = fetch_transactions(db, acc["eb_uid"], start, psu)
                except EBError as exc:
                    if exc.status in (400, 422) and not exc.session_gone:
                        # Viele Banken liefern ältere Umsätze nur kurz nach der Freigabe – dann eben 89 Tage
                        txs = fetch_transactions(db, acc["eb_uid"], date.today() - timedelta(days=89), psu)
                    else:
                        raise
            rows = [r for r in (row_from_eb(t) for t in txs) if r]
            meta = None
            try:
                job.set_step(f"Lade Kontostand für {acc['name']} …")
                bal = pick_balance(((call("GET", f"/accounts/{acc['eb_uid']}/balances", db=db, psu=psu)) or {}).get("balances"))
                if bal:
                    meta = {"balance_cents": bal[0], "balance_date": bal[1]}
            except EBError as exc:
                if exc.session_gone or exc.status == 429:
                    raise
                log.info("Kontostand nicht verfügbar: %s", exc)
            r = ledger.import_rows(db, acc["id"], rows, "openbanking", f"Open Banking {sess['aspsp_name']}", meta)
            if meta:
                ledger.set_balance_anchor(db, acc["id"], meta["balance_cents"], meta["balance_date"])
            summary["accounts"].append({"id": acc["id"], "name": acc["name"], "added": r["added"]})
            summary["added"] += r["added"]
            summary["skipped"] += r["skipped"]
    except EBError as exc:
        if exc.session_gone:
            db.update("eb_sessions", "id", eb_id, {"status": "expired"})
        raise
    return summary


_running: dict[int, str] = {}
_lock = threading.Lock()


def start_sync(eb_id: int, psu: dict | None = None, on_done=None, background: bool = False) -> Job:
    db = get_db()
    sess = db.one("SELECT * FROM eb_sessions WHERE id = ?", (eb_id,))
    if not sess:
        raise EBError("Bankverbindung nicht gefunden.")
    with _lock:
        jid = _running.get(eb_id)
        if jid and JOBS.get(jid) and JOBS[jid].state in ("running", "waiting"):
            return JOBS[jid]
        job = Job(-eb_id, sess["aspsp_name"])
        job.step = "Verbinde mit Enable Banking …"
        JOBS[job.id] = job
        _running[eb_id] = job.id

    def worker():
        try:
            job.result = _sync(job, eb_id, None if background else psu)
            job.state = "done"
            job.step = "Fertig"
            db.update("eb_sessions", "id", eb_id, {"last_sync": now_iso(), "last_status": "ok"})
            if on_done:
                on_done()
        except Exception as exc:  # noqa: BLE001
            job.state = "error"
            job.error = str(exc) if isinstance(exc, UserFacingError) else f"Abruf fehlgeschlagen: {exc}"
            log.warning("Open-Banking-Abruf fehlgeschlagen: %s", exc, exc_info=not isinstance(exc, UserFacingError))
            db.update("eb_sessions", "id", eb_id, {"last_status": job.error[:200]})

    threading.Thread(target=worker, name=f"eb-{job.id}", daemon=True).start()
    return job
