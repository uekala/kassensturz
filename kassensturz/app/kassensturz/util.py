"""Kleine Helfer für Beträge, Datumswerte und Text."""
from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e", "á": "a", "à": "a"})


def norm(text: str | None) -> str:
    """Kleinschreibung, Umlaute ausgeschrieben, Mehrfach-Leerzeichen entfernt."""
    if not text:
        return ""
    t = str(text).lower().translate(_UMLAUTS)
    return re.sub(r"\s+", " ", t).strip()


_LEGAL = re.compile(
    r"\b(gmbh|mbh|ag|se|kg|kgaa|ohg|ug|e\s?v|co|ltd|limited|inc|llc|sarl|s\.?a\.?r\.?l|b\.?v|n\.?v|plc|"
    r"deutschland|germany|europe|eu|sagt danke|vielen dank|online|services?|zweigniederlassung)\b"
)


def counterparty_key(name: str | None) -> str:
    """Normierter Name zum Gruppieren: ohne Rechtsform, Ziffern, Satzzeichen."""
    t = norm(name)
    t = re.sub(r"[0-9]+", " ", t)
    t = re.sub(r"[^a-z&+ ]", " ", t)
    t = _LEGAL.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:40]


def parse_amount(value) -> int | None:
    """'1.234,56', '-12,30 €', '1,234.56', '12.5', '(3,00)' → Cent als int."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return int((Decimal(str(value)) * 100).quantize(Decimal("1")))
    s = str(value).strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    s = s.replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "").replace("'", "")
    if s.endswith("-"):
        neg, s = True, s[:-1]
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-") or s.startswith("−"):
        neg, s = (not neg), s[1:]
    if s.upper().endswith("S") and s[:-1].replace(",", "").replace(".", "").isdigit():
        neg, s = True, s[:-1]  # Soll-Kennzeichen
    elif s.upper().endswith("H") and s[:-1].replace(",", "").replace(".", "").isdigit():
        s = s[:-1]
    if not re.fullmatch(r"[0-9.,]+", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        cents = int((Decimal(s) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None
    return -cents if neg else cents


_DATE_PATTERNS = [
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})"), "dmy"),
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)"), "dmy2"),
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})"), "ymd"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})"), "dmy"),
    (re.compile(r"^(\d{4})/(\d{2})/(\d{2})"), "ymd"),
    (re.compile(r"^(\d{2})(\d{2})(\d{4})$"), "dmy"),
]


def parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip().strip('"')
    if not s:
        return None
    for rx, kind in _DATE_PATTERNS:
        m = rx.match(s)
        if not m:
            continue
        try:
            if kind == "ymd":
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if kind == "dmy2":
                y += 2000 if y < 70 else 1900
            return date(y, mth, d)
        except ValueError:
            return None
    return None


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


_SEPA_KEYS = ["EREF", "KREF", "MREF", "CRED", "DEBT", "COAM", "OAMT", "SVWZ", "ABWA", "ABWE", "IBAN", "BIC"]
_SEPA_RX = re.compile(r"(?:(?<=\s)|^|(?<=[^A-Z]))(" + "|".join(_SEPA_KEYS) + r")\+")


def split_sepa_purpose(purpose: str | None) -> dict:
    """Zerlegt 'EREF+123 MREF+M1 CRED+DE98ZZZ09999999999 SVWZ+Miete Okt' in Felder."""
    out: dict = {}
    if not purpose:
        return out
    text = str(purpose)
    parts = list(_SEPA_RX.finditer(text))
    if not parts:
        return out
    for i, m in enumerate(parts):
        end = parts[i + 1].start() if i + 1 < len(parts) else len(text)
        out[m.group(1)] = text[m.end():end].strip()
    head = text[: parts[0].start()].strip()
    if head:
        out["_head"] = head
    return out


def clean_purpose(purpose: str | None) -> tuple[str, dict]:
    """Gibt den lesbaren Verwendungszweck und erkannte SEPA-Felder zurück."""
    fields = split_sepa_purpose(purpose)
    if not fields:
        return (re.sub(r"\s+", " ", purpose or "").strip(), {})
    readable = fields.get("SVWZ") or fields.get("_head") or ""
    return (re.sub(r"\s+", " ", readable).strip(), fields)


def tx_hash(account_id: int, booking_date: str, amount_cents: int, counterparty: str | None, purpose: str | None) -> str:
    raw = f"{account_id}|{booking_date}|{amount_cents}|{norm(counterparty)[:40]}|{norm(purpose)[:80]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def euro(cents: int | None) -> str:
    if cents is None:
        return "–"
    s = f"{abs(cents) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if cents < 0 else "") + s + " €"
