"""Monatsabrechnung der Advanzia-Kreditkarte (gebührenfrei.de) als PDF lesen.

Advanzia bietet keinen CSV-Export. Die Abrechnung als PDF enthält aber jeden Umsatz als Zeile mit Datum, Text und
Betrag. Kassensturz liest den Text der PDF, nimmt die Zeilen, die so aussehen, und prüft das Ergebnis an den
Salden der Abrechnung: Alter Saldo plus Umsätze muss den neuen Saldo ergeben. Welches Vorzeichen eine Abbuchung
hat, entscheidet diese Prüfung; ohne Salden gilt, was die Mehrheit der Zeilen nahelegt (Einkäufe überwiegen).

Der Aufbau der Abrechnung ist nicht dokumentiert. Darum ist der Leser bewusst großzügig bei Spalten und streng
bei dem, was als Umsatz zählt, und sagt im Ergebnis, ob die Summe zur Abrechnung passt.
"""
from __future__ import annotations

import contextlib
import io
import re
from datetime import date

MAX_PAGES = 40

_MARKERS = ("advanzia", "gebührenfrei", "gebuhrenfrei", "gebuehrenfrei")
_DATE = r"(\d{2})\.(\d{2})\.(\d{4}|\d{2})?"
# Datum, wahlweise ein zweites Datum, Text, Betrag am Ende mit wahlweise Vorzeichen oder Kennung danach
_LINE = re.compile(
    rf"^\s*{_DATE}\s+(?:{_DATE}\s+)?(?P<text>.*?\S)\s+(?P<sign>[-+])?\s?(?P<amount>\d{{1,3}}(?:\.\d{{3}})*,\d{{2}})"
    r"\s*(?:EUR|€)?\s*(?P<mark>-|\+|CR|Cr|H|S|Haben|Soll)?\s*$")
_SKIP = re.compile(r"saldo|summe|übertrag|uebertrag|rechnungsbetrag|mindest|kreditrahmen|verfügungsrahmen|"
                   r"verfuegungsrahmen|zahlungsziel|zinssatz|seite \d", re.I)
_BALANCE = re.compile(
    r"(?P<label>alter saldo|saldo vormonat|saldo der letzten rechnung|vorheriger saldo|letzter saldo|saldovortrag|"
    r"neuer saldo|aktueller saldo|saldo neu|rechnungsbetrag|neuer kontostand)\D{0,40}?"
    r"(?P<sign>[-+])?\s?(?P<amount>\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:EUR|€)?\s*(?P<mark>-|\+|CR|Cr|H|S)?", re.I)
_STATEMENT_DATE = re.compile(r"(?:rechnungsdatum|abrechnungsdatum|datum der rechnung|stichtag)\D{0,20}"
                             r"(\d{2})\.(\d{2})\.(\d{4})", re.I)


def is_pdf(data: bytes) -> bool:
    return data[:1024].lstrip().startswith(b"%PDF")


def text_of(data: bytes) -> str:
    """Der Text aller Seiten, mit Zeilen wie im Layout."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                raise ValueError("Die PDF ist mit einem Passwort geschützt. Speichere sie ohne Passwort.")
        except Exception as exc:
            raise ValueError("Die PDF ist mit einem Passwort geschützt. Speichere sie ohne Passwort.") from exc
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(f"Die PDF hat mehr als {MAX_PAGES} Seiten. Lade eine einzelne Abrechnung hoch.")
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text(extraction_mode="layout") or "")
        except Exception:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def looks_like_advanzia(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _MARKERS)


def _cents(amount: str) -> int:
    return int(amount.replace(".", "").replace(",", ""))


def _negative(sign: str | None, mark: str | None) -> bool | None:
    """True, wenn als Minus oder Haben gekennzeichnet; False bei Plus oder Soll; None ohne Kennung."""
    m = (mark or "").lower()
    if sign == "-" or m in ("-", "cr", "h", "haben"):
        return True
    if sign == "+" or m in ("+", "s", "soll"):
        return False
    return None


def _year(day: str, month: str, year: str | None, ref: date) -> date | None:
    try:
        if year:
            y = int(year)
            return date(y + 2000 if y < 100 else y, int(month), int(day))
        d = date(ref.year, int(month), int(day))
        # Ohne Jahr: ein Datum nach dem Rechnungsdatum gehört ins Vorjahr (Dezember auf der Januar-Rechnung)
        return date(ref.year - 1, int(month), int(day)) if d > ref else d
    except ValueError:
        return None


def parse(text: str, today: date | None = None) -> dict:
    """Umsätze und Salden aus dem Text einer Abrechnung."""
    today = today or date.today()
    found = _STATEMENT_DATE.search(text)
    ref = today
    if found:
        with contextlib.suppress(ValueError):
            ref = date(int(found.group(3)), int(found.group(2)), int(found.group(1)))
    raw, skipped = [], 0
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        body = " ".join(m.group("text").split())
        if _SKIP.search(body) or not re.search(r"[A-Za-zÄÖÜäöü]", body):
            skipped += 1
            continue
        day = _year(m.group(1), m.group(2), m.group(3), ref)
        value_day = _year(m.group(4), m.group(5), m.group(6), ref) if m.group(4) else None
        if not day:
            skipped += 1
            continue
        raw.append({"day": day, "value_day": value_day, "text": body[:140], "cents": _cents(m.group("amount")),
                    "negative": _negative(m.group("sign"), m.group("mark"))})
    balances = {}
    for m in _BALANCE.finditer(text):
        label = m.group("label").lower()
        key = "new" if any(w in label for w in ("neu", "aktuell", "rechnungsbetrag", "kontostand")) else "old"
        if key in balances:
            continue
        cents = _cents(m.group("amount"))
        balances[key] = -cents if _negative(m.group("sign"), m.group("mark")) else cents
    return {"lines": raw, "skipped": skipped, "balances": balances, "statement_date": ref.isoformat()}


def _signed(lines: list[dict], plain_is_expense: bool) -> list[int]:
    """Beträge aus Sicht des Kontos: Einkäufe negativ, Gutschriften positiv."""
    out = []
    for r in lines:
        marked = r["negative"]
        if marked is None:
            out.append(-r["cents"] if plain_is_expense else r["cents"])
        else:
            # Gekennzeichnet ist immer das Gegenteil der üblichen Zeile
            expense = not marked if plain_is_expense else marked
            out.append(-r["cents"] if expense else r["cents"])
    return out


def rows_from(parsed: dict) -> tuple[list[dict], dict]:
    """Buchungen für den Import und was die Prüfung an den Salden ergab."""
    lines = parsed["lines"]
    check = {"balances_found": len(parsed["balances"]) == 2, "matches": None, "difference_cents": None}
    plain = [r for r in lines if r["negative"] is None]
    # Ohne Salden: Bei einer Kreditkarte überwiegen Einkäufe.
    plain_is_expense = True
    if check["balances_found"]:
        old, new = parsed["balances"]["old"], parsed["balances"]["new"]
        # Salden einer Kreditkarte stehen meist als offene Schuld da (positiv); geprüft wird beides.
        best = None
        for expense in (True, False):
            total = sum(_signed(lines, expense))
            for debt in (True, False):
                diff = (new - old) - (-total if debt else total)
                if best is None or abs(diff) < abs(best[0]):
                    best = (diff, expense)
        check["difference_cents"], plain_is_expense = best
        check["matches"] = best[0] == 0
    elif not plain:
        plain_is_expense = True
    amounts = _signed(lines, plain_is_expense)
    rows = []
    for r, cents in zip(lines, amounts, strict=False):
        if not cents:
            continue
        day = r["day"].isoformat()
        rows.append({
            "booking_date": day, "value_date": (r["value_day"] or r["day"]).isoformat(), "amount_cents": cents,
            "currency": "EUR", "counterparty": r["text"], "counterparty_iban": None, "purpose": None,
            "booking_text": None, "creditor_id": None, "mandate_ref": None, "end_to_end": None,
            "balance_cents": None, "own_iban": None,
        })
    return rows, check
