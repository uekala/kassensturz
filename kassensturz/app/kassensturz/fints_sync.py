"""Bankabruf per FinTS/HBCI im Hintergrund, mit TAN-Rückfragen über die Oberfläche."""
from __future__ import annotations

import base64
import logging
import threading
import time
import uuid
from datetime import date, timedelta

from . import ledger, options, secrets_store
from .db import get_db, now_iso
from .importers import row_from_mt940

log = logging.getLogger("kassensturz.fints")

# FinTS-Kontoarten laut ZKA: 1–9 Giro, 10–19 Spar, 20–29 Festgeld, 50–59 Kreditkarte
def _kind_for(account_type) -> str:
    try:
        t = int(account_type or 1)
    except (TypeError, ValueError):
        return "giro"
    if 10 <= t <= 29:
        return "tagesgeld"
    if 50 <= t <= 59:
        return "kreditkarte"
    return "giro"


def _patch_mt940() -> None:
    """python-fints parst MT940 ohne die Optionen für deutsche Banken – hier nachrüsten."""
    import fints.client

    from .importers import mt940_transactions

    def mt940_to_array(data):
        return mt940_transactions(data.replace("@@", "\r\n").replace("-0000", "+0000"))

    fints.client.mt940_to_array = mt940_to_array


class JobCancelled(Exception):
    pass


class UserFacingError(Exception):
    pass


class Job:
    def __init__(self, connection_id: int, name: str):
        self.id = uuid.uuid4().hex[:12]
        self.connection_id = connection_id
        self.name = name
        self.state = "running"   # running | waiting | done | error | cancelled
        self.step = "Verbinde mit der Bank …"
        self.question: dict | None = None
        self.result: dict | None = None
        self.error: str | None = None
        self.created = time.time()
        self._event = threading.Event()
        self._answer = None
        self.cancelled = False

    def public(self) -> dict:
        return {"id": self.id, "connection_id": self.connection_id, "name": self.name, "state": self.state, "step": self.step,
                "question": self.question, "result": self.result, "error": self.error}

    def set_step(self, text: str) -> None:
        self.step = text

    def ask(self, kind: str, payload: dict, timeout: int = 300):
        self._event.clear()
        self.question = {"kind": kind, "qid": uuid.uuid4().hex[:8], **payload}
        self.state = "waiting"
        got = self._event.wait(timeout)
        self.question = None
        if self.cancelled:
            raise JobCancelled()
        if not got:
            raise UserFacingError("Keine Eingabe innerhalb von fünf Minuten – der Abruf wurde abgebrochen.")
        self.state = "running"
        return self._answer

    def wait_external(self, kind: str, payload: dict, seconds: float) -> None:
        """Zeigt einen Hinweis (z. B. „in der App bestätigen") und wartet, bis zu `seconds` oder bis zum Klick."""
        if not self.question or self.question.get("kind") != kind:
            self._event.clear()
            self.question = {"kind": kind, "qid": uuid.uuid4().hex[:8], **payload}
        self.state = "waiting"
        self._event.wait(seconds)
        self._event.clear()
        if self.cancelled:
            raise JobCancelled()

    def clear_question(self) -> None:
        self.question = None
        self.state = "running"

    def answer(self, value) -> None:
        self._answer = value
        self._event.set()

    def cancel(self) -> None:
        self.cancelled = True
        self._event.set()


JOBS: dict[str, Job] = {}
_running: dict[int, str] = {}
_lock = threading.Lock()


def start(connection_id: int, pin: str | None, save_pin: bool = False, history_days: int | None = None,
          on_done=None, background: bool = False) -> Job:
    db = get_db()
    conn = db.one("SELECT * FROM connections WHERE id = ?", (connection_id,))
    if not conn:
        raise UserFacingError("Bankzugang nicht gefunden.")
    with _lock:
        running = _running.get(connection_id)
        if running and JOBS.get(running) and JOBS[running].state in ("running", "waiting"):
            return JOBS[running]
        job = Job(connection_id, conn["name"])
        JOBS[job.id] = job
        _running[connection_id] = job.id
        for jid in [j for j, jb in JOBS.items() if time.time() - jb.created > 3600]:
            JOBS.pop(jid, None)
    pin = pin or secrets_store.get_pin(connection_id)

    def worker():
        try:
            if not pin:
                raise UserFacingError("Bitte gib deine Online-Banking-PIN ein.")
            job.result = _sync(job, conn, pin, history_days, background)
            if save_pin:
                secrets_store.set_pin(connection_id, pin)
            job.state = "done"
            job.step = "Fertig"
            db.update("connections", "id", connection_id, {"last_sync": now_iso(), "last_status": "ok"})
            if on_done:
                on_done()
        except JobCancelled:
            job.state = "cancelled"
            job.step = "Abgebrochen"
        except Exception as exc:  # noqa: BLE001 – alles in eine verständliche Meldung übersetzen
            job.state = "error"
            job.error = _explain(exc)
            log.warning("FinTS-Abruf fehlgeschlagen: %s", exc, exc_info=not isinstance(exc, UserFacingError))
            db.update("connections", "id", connection_id, {"last_status": job.error[:200]})
        finally:
            job.question = None

    threading.Thread(target=worker, name=f"fints-{job.id}", daemon=True).start()
    return job


def _explain(exc: Exception) -> str:
    from fints.exceptions import (FinTSClientPINError, FinTSClientTemporaryAuthError, FinTSConnectionError,
                                  FinTSDialogInitError, FinTSSCARequiredError)

    if isinstance(exc, UserFacingError):
        return str(exc)
    if isinstance(exc, FinTSClientPINError):
        return "Die Bank hat die PIN abgelehnt. Prüfe PIN und Anmeldenamen – nach mehreren Fehlversuchen sperrt die Bank den Zugang."
    if isinstance(exc, FinTSClientTemporaryAuthError):
        return "Der Zugang ist vorübergehend gesperrt. Entsperre ihn im Online-Banking und versuche es dann erneut."
    if isinstance(exc, FinTSSCARequiredError):
        return "Die Bank verlangt eine TAN-Freigabe. Starte den Abruf von Hand, um sie zu bestätigen."
    if isinstance(exc, FinTSConnectionError):
        return "Der FinTS-Server ist nicht erreichbar. Prüfe die Serveradresse in den Einstellungen des Bankzugangs."
    if isinstance(exc, FinTSDialogInitError):
        return "Die Bank hat die Anmeldung abgelehnt. Oft fehlt die Freischaltung für FinTS/HBCI im Online-Banking."
    text = str(exc) or exc.__class__.__name__
    return f"Abruf fehlgeschlagen: {text[:300]}"


def _challenge_payload(res) -> dict:
    payload = {"text": res.challenge or "Bitte TAN eingeben.", "html": getattr(res, "challenge_html", None)}
    matrix = getattr(res, "challenge_matrix", None)
    if matrix and len(matrix) == 2 and matrix[1]:
        payload["image"] = f"data:{matrix[0]};base64,{base64.b64encode(matrix[1]).decode()}"
    hhduc = getattr(res, "challenge_hhduc", None)
    if hhduc and "image" not in payload:
        try:
            from fints.hhd.flicker import code_to_bitstream

            payload["flicker"] = code_to_bitstream(hhduc)
        except Exception:  # noqa: BLE001
            try:
                from fints.utils import decode_phototan_image

                img = decode_phototan_image(hhduc if isinstance(hhduc, bytes) else hhduc.encode("iso-8859-1"))
                payload["image"] = f"data:{img['mime_type']};base64,{base64.b64encode(img['image']).decode()}"
            except Exception:  # noqa: BLE001
                pass
    return payload


def _resolve(client, res, job: Job, background: bool):
    from fints.client import NeedTANResponse

    polls = 0
    while isinstance(res, NeedTANResponse):
        if background:
            raise UserFacingError("Die Bank verlangt eine TAN-Freigabe. Öffne Kassensturz und starte den Abruf von Hand.")
        if res.decoupled:
            polls += 1
            if polls > 60:
                raise UserFacingError("Die Freigabe in der Banking-App kam nicht innerhalb von fünf Minuten.")
            job.wait_external("decoupled", {"text": res.challenge or "Bitte bestätige den Zugriff in deiner Banking-App."},
                              5 if polls > 1 else 3)
            res = client.send_tan(res, "")
        else:
            tan = job.ask("tan", _challenge_payload(res))
            job.set_step("Prüfe TAN …")
            res = client.send_tan(res, str(tan or "").strip())
    job.clear_question()
    return res


def _sync(job: Job, conn: dict, pin: str, history_days: int | None, background: bool) -> dict:
    from fints.client import FinTS3PinTanClient, FinTSOperations

    _patch_mt940()
    db = get_db()
    product_id = (options.load().get("fints_product_id") or "").strip()
    if not product_id:
        raise UserFacingError("Für den Bankabruf fehlt die FinTS-Produkt-ID. Trage sie in der Konfiguration der App ein "
                              "(Registrierung kostenlos über fints.org).")
    client = FinTS3PinTanClient(
        conn["blz"].strip(), conn["login"].strip(), pin, conn["server"].strip(),
        customer_id=(conn["customer_id"] or None), product_id=product_id, product_version=options.VERSION[:5],
        from_data=conn["client_state"] or None,
    )

    if not client.get_current_tan_mechanism():
        job.set_step("Frage TAN-Verfahren ab …")
        client.fetch_tan_mechanisms()
        mechs = list(client.get_tan_mechanisms().items())
        if len(mechs) == 1:
            client.set_tan_mechanism(mechs[0][0])
        elif len(mechs) > 1:
            if background:
                raise UserFacingError("Das TAN-Verfahren ist noch nicht gewählt. Starte den Abruf einmal von Hand.")
            opts = [{"value": k, "label": str(getattr(m, "name", k)),
                     "hint": "App-Freigabe" if getattr(m, "decoupled_max_poll_number", None) is not None else ""} for k, m in mechs]
            choice = job.ask("choice", {"title": "Welches TAN-Verfahren nutzt du?", "options": opts})
            client.set_tan_mechanism(str(choice))
    try:
        media_needed = client.selected_tan_medium is None and client.is_tan_media_required()
    except KeyError:
        media_needed = False  # Verfahren stammt aus gespeichertem Zustand; Bank meldet erlaubte Verfahren erst im Dialog
    if media_needed:
        job.set_step("Frage TAN-Medien ab …")
        media = client.get_tan_media()[1]
        if len(media) == 1:
            client.set_tan_medium(media[0])
        elif not media:
            client.selected_tan_medium = ""
        else:
            if background:
                raise UserFacingError("Das TAN-Medium ist noch nicht gewählt. Starte den Abruf einmal von Hand.")
            opts = [{"value": str(i), "label": str(m.tan_medium_name), "hint": str(getattr(m, "mobile_number_masked", "") or "")}
                    for i, m in enumerate(media)]
            choice = job.ask("choice", {"title": "Welches Gerät soll die TAN bekommen?", "options": opts})
            client.set_tan_medium(media[int(choice)])

    summary = {"accounts": [], "added": 0, "skipped": 0}
    job.set_step("Melde an …")
    with client:
        if client.init_tan_response:
            client.init_tan_response = _resolve(client, client.init_tan_response, job, background)
        job.set_step("Lade Kontenliste …")
        sepa_accounts = _resolve(client, client.get_sepa_accounts(), job, background)
        info = client.get_information()
        by_iban = {a.get("iban"): a for a in info.get("accounts", []) if a.get("iban")}
        for sa in sepa_accounts:
            meta = by_iban.get(sa.iban, {})
            ops = meta.get("supported_operations") or {}
            if ops and not (ops.get(FinTSOperations.GET_TRANSACTIONS) or ops.get(FinTSOperations.GET_TRANSACTIONS_XML)):
                continue
            acc = _ensure_account(db, conn, sa, meta)
            if acc["archived"]:
                continue
            last = db.scalar("SELECT MAX(booking_date) FROM transactions WHERE account_id = ? AND source = 'fints'", (acc["id"],))
            if last:
                start = date.fromisoformat(last) - timedelta(days=10)
            else:
                start = date.today() - timedelta(days=int(history_days or conn["history_days"] or 365))
            job.set_step(f"Lade Umsätze für {acc['name']} …")
            txs = _resolve(client, client.get_transactions(sa, start, date.today()), job, background) or []
            rows = [r for r in (row_from_mt940(getattr(t, "data", t)) for t in txs) if r]
            res_meta = None
            if not ops or ops.get(FinTSOperations.GET_BALANCE, True):
                try:
                    job.set_step(f"Lade Kontostand für {acc['name']} …")
                    bal = _resolve(client, client.get_balance(sa), job, background)
                    if bal is not None and getattr(bal, "amount", None) is not None:
                        cents = int(round(bal.amount.amount * 100))
                        res_meta = {"balance_cents": cents, "balance_date": (bal.date or date.today()).isoformat()}
                except Exception as exc:  # noqa: BLE001 – Saldo ist optional
                    log.info("Saldo nicht verfügbar: %s", exc)
            r = ledger.import_rows(db, acc["id"], rows, "fints", f"FinTS {conn['name']}", res_meta)
            if res_meta:
                ledger.set_balance_anchor(db, acc["id"], res_meta["balance_cents"], res_meta["balance_date"])
                ledger.check_balance(db, acc["id"], res_meta["balance_cents"])
            summary["accounts"].append({"id": acc["id"], "name": acc["name"], "added": r["added"]})
            summary["added"] += r["added"]
            summary["skipped"] += r["skipped"]
    state = client.deconstruct(including_private=False)
    db.update("connections", "id", conn["id"], {"client_state": state, "tan_mechanism": client.get_current_tan_mechanism(),
                                                "tan_medium": client.selected_tan_medium})
    return summary


def _ensure_account(db, conn: dict, sa, meta: dict) -> dict:
    acc = db.one("SELECT * FROM accounts WHERE connection_id = ? AND iban = ?", (conn["id"], sa.iban))
    if acc:
        return acc
    acc = db.one("SELECT * FROM accounts WHERE iban = ? AND connection_id IS NULL", (sa.iban,))
    kind = _kind_for(meta.get("type"))
    if acc:
        db.update("accounts", "id", acc["id"], {"connection_id": conn["id"]})
        return db.one("SELECT * FROM accounts WHERE id = ?", (acc["id"],))
    name = (meta.get("product_name") or "").strip() or ("Kreditkarte" if kind == "kreditkarte" else "Girokonto")
    aid = db.insert("accounts", {
        "name": f"{name} {conn['name']}".strip() if conn["name"] not in name else name,
        "kind": kind, "iban": sa.iban, "bank": conn["name"], "connection_id": conn["id"], "currency": meta.get("currency") or "EUR",
        "in_forecast": 0 if kind == "tagesgeld" else 1, "created": now_iso(),
    })
    return db.one("SELECT * FROM accounts WHERE id = ?", (aid,))


def answer(job_id: str, value) -> Job | None:
    job = JOBS.get(job_id)
    if job:
        job.answer(value)
    return job


def cancel(job_id: str) -> Job | None:
    job = JOBS.get(job_id)
    if job:
        job.cancel()
    return job


# Vorbelegte FinTS-Server (bitte im Zweifel bei der Bank prüfen)
BANK_PRESETS = [
    {"name": "ING", "blz": "50010517", "server": "https://fints.ing.de/fints/"},
    {"name": "DKB", "blz": "12030000", "server": "https://fints.dkb.de/fints"},
    {"name": "comdirect", "blz": "", "server": "https://fints.comdirect.de/fints"},
    {"name": "1822direkt", "blz": "50050222", "server": "https://fints.1822direkt.com/fints/hbci"},
    {"name": "Volksbank / Raiffeisenbank (Atruvia)", "blz": "", "server": "https://fints1.atruvia.de/cgi-bin/hbciservlet"},
    {"name": "Sparkasse", "blz": "", "server": ""},
]
