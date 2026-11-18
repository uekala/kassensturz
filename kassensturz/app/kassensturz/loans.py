"""Kredite mit Tilgungsplan: Restschuld heute, Enddatum, Zinsen und was eine Sondertilgung bringt.

Ein Kredit ist ein Konto der Art „Kredit“ mit einer von Hand eingetragenen Restschuld. Kommen
Sollzins und Monatsrate dazu, rechnet Kassensturz von der letzten eingetragenen Restschuld aus
weiter: jeden Monat Zinsen auf den Rest, die Rate tilgt, was übrig bleibt (Annuitätendarlehen
mit monatlicher Verrechnung, wie bei Raten- und Baukrediten üblich).

Das ist eine Schätzung. Die Bank rechnet taggenau, rundet anders und kennt Sondertilgungen,
Zinsbindungen und Gebühren, die hier nicht vorkommen. Verbindlich ist ihr Kontoauszug; die
geschätzte Restschuld ersetzt den eingetragenen Wert nur, wenn du sie übernimmst.
"""
from __future__ import annotations

from datetime import date

from .db import Database
from .util import add_months

# Sollzins in Tausendstel Prozent pro Jahr: 3,49 % sind 3490.
MAX_RATE_MILLI = 30_000
MAX_CENTS = 1_000_000_000
# Länger rechnet der Plan nicht; wer dann noch nicht fertig ist, tilgt zu wenig.
MAX_MONTHS = 720


class LoanError(ValueError):
    """Die Angaben passen nicht; ``status`` ist der HTTP-Status dazu."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def clean_terms(data: dict) -> dict:
    """Prüft Sollzins und Monatsrate eines Kontos; leer heißt „nicht angegeben“."""
    out = {}
    if "loan_rate_milli" in data:
        value = data["loan_rate_milli"]
        if value in (None, ""):
            out["loan_rate_milli"] = None
        elif isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_RATE_MILLI:
            raise LoanError(400, "Der Sollzins ist ungültig. Erlaubt sind 0 bis 30 Prozent.")
        else:
            out["loan_rate_milli"] = value
    if "loan_payment_cents" in data:
        value = data["loan_payment_cents"]
        if value in (None, "", 0):
            out["loan_payment_cents"] = None
        elif isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_CENTS:
            raise LoanError(400, "Die Monatsrate ist ungültig.")
        else:
            out["loan_payment_cents"] = value
    return out


def _interest(rest: int, rate_milli: int) -> int:
    """Zinsen eines Monats auf die Restschuld, kaufmännisch gerundet."""
    return (rest * rate_milli + 600_000) // 1_200_000


def _step(rest: int, rate_milli: int, payment: int) -> tuple[int, int, int]:
    """Ein Monat: (Zinsen, gezahlt, neuer Rest). Die letzte Rate ist nur so hoch wie nötig."""
    interest = _interest(rest, rate_milli)
    paid = min(payment, rest + interest)
    return interest, paid, rest + interest - paid


def schedule(rest: int, start: date, rate_milli: int, payment: int) -> dict:
    """Tilgt ``rest`` ab dem Monat nach ``start`` mit ``payment`` je Monat.

    Gibt Monate, Enddatum, Summe der Zinsen und die Zeilen je Monat zurück. ``done`` ist falsch,
    wenn der Kredit nach MAX_MONTHS nicht getilgt ist."""
    rows, interest_sum, paid_sum, month = [], 0, 0, 0
    while rest > 0 and month < MAX_MONTHS:
        month += 1
        interest, paid, rest = _step(rest, rate_milli, payment)
        interest_sum += interest
        paid_sum += paid
        rows.append({"date": add_months(start, month).isoformat(), "interest_cents": interest,
                     "principal_cents": paid - interest, "paid_cents": paid, "rest_cents": rest})
    return {"months": month, "end_date": rows[-1]["date"] if rows else start.isoformat(), "interest_cents": interest_sum,
            "paid_cents": paid_sum, "done": rest == 0, "rows": rows}


def _years(rows: list[dict]) -> list[dict]:
    """Der Plan je Kalenderjahr: gezahlt, davon Zinsen, Restschuld am Jahresende."""
    out: dict[str, dict] = {}
    for r in rows:
        y = out.setdefault(r["date"][:4], {"year": int(r["date"][:4]), "paid_cents": 0, "interest_cents": 0, "rest_cents": 0})
        y["paid_cents"] += r["paid_cents"]
        y["interest_cents"] += r["interest_cents"]
        y["rest_cents"] = r["rest_cents"]
    return list(out.values())


def overview(db: Database, account_id: int, extra_cents: int = 0, today: date | None = None) -> dict:
    """Der Tilgungsplan eines Kredits ab heute, auf Wunsch mit einer Sondertilgung heute."""
    today = today or date.today()
    acc = db.one("SELECT id, name, kind, matures_on, loan_rate_milli, loan_payment_cents FROM accounts WHERE id = ?", (account_id,))
    if not acc:
        raise LoanError(404, "Konto nicht gefunden.")
    if acc["kind"] != "kredit":
        raise LoanError(409, "Einen Tilgungsplan gibt es nur für Kredite.")
    if isinstance(extra_cents, bool) or not isinstance(extra_cents, int) or not 0 <= extra_cents <= MAX_CENTS:
        raise LoanError(400, "Die Sondertilgung ist ungültig.")
    last = db.one("SELECT value_cents, on_date FROM valuations WHERE account_id = ? AND on_date <= ? ORDER BY on_date DESC LIMIT 1",
                  (account_id, today.isoformat()))
    out = {"account_id": acc["id"], "name": acc["name"], "matures_on": acc["matures_on"], "rate_milli": acc["loan_rate_milli"],
           "payment_cents": acc["loan_payment_cents"], "entered_cents": abs(last["value_cents"]) if last else None,
           "entered_on": last["on_date"] if last else None, "ready": False, "missing": []}
    if acc["loan_rate_milli"] is None:
        out["missing"].append("rate")
    if not acc["loan_payment_cents"]:
        out["missing"].append("payment")
    if not last:
        out["missing"].append("balance")
    if out["missing"]:
        return out
    rate, payment = acc["loan_rate_milli"], acc["loan_payment_cents"]
    # Von der eingetragenen Restschuld in vollen Monaten bis heute weiterrechnen.
    start, rest = date.fromisoformat(last["on_date"]), abs(last["value_cents"])
    elapsed = 0
    while rest > 0 and add_months(start, elapsed + 1) <= today:
        elapsed += 1
        rest = _step(rest, rate, payment)[2]
    base = add_months(start, elapsed)
    out.update({"ready": True, "today_cents": rest, "months_since_entry": elapsed,
                "first_interest_cents": _interest(rest, rate)})
    if rest and payment <= _interest(rest, rate):
        # Die Rate deckt nicht einmal die Zinsen: Die Schuld wächst, es gibt kein Ende.
        out.update({"covers_interest": False, "months": None, "end_date": None, "interest_cents": None, "years": []})
        return out
    plan = schedule(rest, base, rate, payment)
    out.update({"covers_interest": True, "months": plan["months"], "end_date": plan["end_date"] if plan["done"] else None,
                "interest_cents": plan["interest_cents"], "total_cents": plan["paid_cents"], "done": plan["done"],
                "years": _years(plan["rows"]),
                "end_differs": bool(plan["done"] and acc["matures_on"] and plan["end_date"][:7] != acc["matures_on"][:7])})
    if extra_cents:
        if extra_cents > rest:
            raise LoanError(400, "Die Sondertilgung ist höher als die Restschuld.")
        faster = schedule(rest - extra_cents, base, rate, payment)
        out["extra"] = {"cents": extra_cents, "months": faster["months"], "end_date": faster["end_date"],
                        "interest_cents": faster["interest_cents"], "months_saved": plan["months"] - faster["months"],
                        "interest_saved_cents": plan["interest_cents"] - faster["interest_cents"]}
    return out
