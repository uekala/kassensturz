"""Datei-Import: CSV aller gängigen Banken, CAMT.052/.053 (auch als ZIP) und MT940/STA."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date

from .util import clean_purpose, norm, parse_amount, parse_date


# Resource limits apply to uploads and watched-folder imports alike.
MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_ZIP_ENTRIES = 100
MAX_ZIP_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_XML_FILE_BYTES = 20 * 1024 * 1024

FIELDS = [
    "date", "value_date", "amount", "debit", "credit", "fee", "counterparty", "counterparty_in",
    "counterparty_out", "purpose", "booking_text", "iban", "currency", "balance", "status",
    "creditor_id", "mandate_ref", "end_to_end", "own_iban", "product",
]

FIELD_LABELS = {
    "date": "Buchungstag", "value_date": "Wertstellung", "amount": "Betrag", "debit": "Soll / Ausgang",
    "credit": "Haben / Eingang", "fee": "Gebühr", "counterparty": "Gegenseite", "counterparty_in": "Gegenseite (Eingang)",
    "counterparty_out": "Gegenseite (Ausgang)", "purpose": "Verwendungszweck", "booking_text": "Buchungsart",
    "iban": "IBAN Gegenseite", "currency": "Währung", "balance": "Saldo", "status": "Status",
    "creditor_id": "Gläubiger-ID", "mandate_ref": "Mandatsreferenz", "end_to_end": "End-to-End-Referenz",
    "own_iban": "Eigene IBAN", "product": "Produkt",
}

SYNONYMS: dict[str, list[str]] = {
    "date": ["buchungstag", "buchungsdatum", "buchung", "booking date", "completed date", "abschlussdatum", "datum", "date",
             "transaktionsdatum", "transaction date", "umsatztag", "belegdatum", "started date", "startdatum"],
    "value_date": ["valutadatum", "valuta", "wertstellung", "wertstellungsdatum", "wertstellung valuta", "value date", "wertstellungstag"],
    "amount": ["betrag", "betrag eur", "betrag in eur", "umsatz in eur", "umsatz", "umsatzbetrag", "amount", "amount eur", "netto", "wert", "summe"],
    "debit": ["soll", "belastung", "ausgang", "debit", "abgang", "lastschrift betrag"],
    "credit": ["haben", "gutschrift", "eingang", "credit", "zugang"],
    "fee": ["fee"],
    "counterparty": ["beguenstigter zahlungspflichtiger", "name zahlungsbeteiligter", "auftraggeber empfaenger", "empfaenger auftraggeber",
                     "partner name", "payee", "name", "zahlungsempfaenger", "empfaenger", "auftraggeber", "gegenpartei", "counterparty",
                     "haendler", "merchant", "beschreibung", "description"],
    "counterparty_out": ["zahlungsempfaenger in"],
    "counterparty_in": ["zahlungspflichtige r"],
    "purpose": ["verwendungszweck", "payment reference", "zahlungsreferenz", "reference", "betreff", "artikelbezeichnung", "buchungsdetails", "hinweis"],
    "booking_text": ["buchungstext", "umsatzart", "umsatztyp", "vorgang", "typ", "type", "transaction type", "buchungsart", "art"],
    "iban": ["kontonummer iban", "iban zahlungsbeteiligter", "partner iban", "iban", "account number", "kontonummer", "iban gegenkonto"],
    "currency": ["waehrung", "currency", "whrg"],
    "balance": ["saldo nach buchung", "saldo", "kontostand", "balance"],
    "status": ["status", "state", "info"],
    "creditor_id": ["glaeubiger id", "glaeubigerid", "creditor id"],
    "mandate_ref": ["mandatsreferenz", "mandate reference"],
    "end_to_end": ["kundenreferenz end to end", "end to end reference", "kundenreferenz"],
    "own_iban": ["auftragskonto", "iban auftragskonto"],
    "product": ["product", "produkt"],
}

SKIP_STATUS = re.compile(r"vorgemerkt|pending|revert|declin|fail|storniert|abgelehnt|fehlgeschlagen|zurueckgesetzt|ausstehend|offen|cancel")

# Bekannte Formate: Erkennung über Spaltennamen, Vorbelegung für neue Konten
PRESETS = [
    {"id": "paypal", "label": "PayPal", "needs": {"brutto", "netto"}, "kind": "paypal", "name": "PayPal", "settlement": "paypal",
     "map": {"amount": "netto", "counterparty": "name", "booking_text": "typ", "purpose": ["artikelbezeichnung", "betreff", "hinweis"]}},
    {"id": "amex", "label": "American Express", "any": {"karteninhaber", "erscheint auf ihrer abrechnung als"}, "kind": "kreditkarte",
     "name": "American Express", "settlement": "american express,amex", "invert": True,
     "map": {"counterparty": "beschreibung", "purpose": ["weitere details"]}},
    {"id": "revolut", "label": "Revolut", "needs": {"started date", "completed date"}, "kind": "giro", "name": "Revolut", "settlement": "revolut",
     "fee_subtract": True, "map": {"date": "completed date", "counterparty": "description", "booking_text": "type", "fee": "fee"}},
    {"id": "revolut_de", "label": "Revolut", "needs": {"startdatum", "abschlussdatum"}, "kind": "giro", "name": "Revolut", "settlement": "revolut",
     "fee_subtract": True, "map": {"date": "abschlussdatum", "counterparty": "beschreibung", "booking_text": "art", "fee": "gebuehr"}},
    {"id": "n26", "label": "N26", "needs": {"partner name", "payment reference"}, "kind": "giro", "name": "N26", "settlement": "n26"},
    {"id": "n26_alt", "label": "N26", "needs": {"payee", "payment reference"}, "kind": "giro", "name": "N26", "settlement": "n26"},
    {"id": "dkb", "label": "DKB", "needs": {"zahlungspflichtige r", "zahlungsempfaenger in"}, "kind": "giro", "name": "DKB Girokonto"},
    {"id": "comdirect", "label": "comdirect", "needs": {"umsatz in eur", "vorgang"}, "kind": "giro", "name": "comdirect Girokonto",
     "map": {"booking_text": "vorgang", "purpose": ["buchungstext"]}},
    {"id": "ing", "label": "ING", "needs": {"auftraggeber empfaenger", "buchung"}, "kind": "giro", "name": "ING Girokonto"},
    {"id": "volksbank", "label": "Volksbank / Raiffeisenbank", "needs": {"name zahlungsbeteiligter", "iban zahlungsbeteiligter"}, "kind": "giro",
     "name": "Volksbank Girokonto"},
    {"id": "sparkasse", "label": "Sparkasse", "needs": {"beguenstigter zahlungspflichtiger", "auftragskonto"}, "kind": "giro", "name": "Sparkasse Girokonto",
     "map": {"purpose": ["verwendungszweck"]}},
    {"id": "klarna", "label": "Klarna", "any_name": "klarna", "kind": "sonstiges", "name": "Klarna", "settlement": "klarna"},
    {"id": "advanzia", "label": "Advanzia", "any_name": "advanzia", "kind": "kreditkarte", "name": "Advanzia Mastercard", "settlement": "advanzia"},
]


def header_norm(h: str) -> str:
    t = norm(h)
    t = re.sub(r"[€$]", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def sniff_delimiter(text: str) -> str:
    lines = [ln for ln in text.splitlines()[:60] if ln.strip()]
    best, best_score = ";", -1
    for d in (";", ",", "\t", "|"):
        counts = [ln.count(d) for ln in lines]
        if not counts:
            continue
        common, freq = Counter(c for c in counts if c > 0).most_common(1)[0] if any(counts) else (0, 0)
        score = freq * min(common, 12)
        if score > best_score:
            best, best_score = d, score
    return best


def _find_header(rows: list[list[str]]) -> int:
    date_syn = set(SYNONYMS["date"])
    amount_syn = set(SYNONYMS["amount"]) | set(SYNONYMS["debit"]) | set(SYNONYMS["credit"])
    all_syn = {s for v in SYNONYMS.values() for s in v}
    for i, row in enumerate(rows[:60]):
        cells = {header_norm(c) for c in row if c.strip()}
        if len(cells) < 3:
            continue
        if cells & date_syn and cells & amount_syn and len(cells & all_syn) >= 3:
            return i
    return -1


def auto_mapping(headers: list[str]) -> tuple[dict, dict | None]:
    normed = [header_norm(h) for h in headers]
    hset = set(normed)
    preset = None
    for p in PRESETS:
        if "needs" in p and p["needs"] <= hset:
            preset = p
            break
        if "any" in p and p["any"] & hset:
            preset = p
            break
    used: set[int] = set()
    mapping: dict = {f: None for f in FIELDS}
    mapping["purpose"] = []

    def idx(name: str) -> int | None:
        for i, h in enumerate(normed):
            if h == name and i not in used:
                return i
        return None

    if preset:
        for field, names in preset.get("map", {}).items():
            if isinstance(names, list):
                cols = [i for i in (idx(n) for n in names) if i is not None]
                mapping[field] = cols
                used.update(cols)
            else:
                i = idx(names)
                if i is not None:
                    mapping[field] = i
                    used.add(i)
    order = ["date", "value_date", "own_iban", "counterparty_in", "counterparty_out", "counterparty", "amount", "debit", "credit",
             "fee", "iban", "currency", "balance", "status", "creditor_id", "mandate_ref", "end_to_end", "booking_text", "product"]
    for field in order:
        if mapping.get(field) not in (None, []):
            continue
        if field == "counterparty" and (mapping["counterparty_in"] is not None or mapping["counterparty_out"] is not None):
            continue
        if field in ("debit", "credit") and mapping["amount"] is not None:
            continue
        if field == "fee" and not (preset and preset.get("fee_subtract")):
            continue
        for syn in SYNONYMS[field]:
            i = idx(syn)
            if i is not None:
                mapping[field] = i
                used.add(i)
                break
    if not mapping["purpose"]:
        cols = []
        for syn in SYNONYMS["purpose"]:
            i = idx(syn)
            if i is not None:
                cols.append(i)
                used.add(i)
        for syn in ("beschreibung", "description"):
            i = idx(syn)
            if i is not None:
                cols.append(i)
                used.add(i)
        mapping["purpose"] = cols
    mapping["invert"] = bool(preset and preset.get("invert"))
    mapping["fee_subtract"] = bool(preset and preset.get("fee_subtract"))
    return mapping, preset


_COMDIRECT_RX = re.compile(r"(?:Auftraggeber|Empf(?:ä|ae)nger)\s*:\s*(.+?)\s+(?:Kto/IBAN|Buchungstext|BLZ/BIC|$)", re.I)
_COMDIRECT_IBAN = re.compile(r"Kto/IBAN\s*:\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30})", re.I)


def _cell(row: list[str], i) -> str:
    if i is None or i >= len(row):
        return ""
    return (row[i] or "").strip()


def convert_rows(table: list[list[str]], mapping: dict) -> tuple[list[dict], Counter]:
    out: list[dict] = []
    skipped: Counter = Counter()
    product_col = mapping.get("product")
    only_current = False
    if product_col is not None:
        values = {norm(_cell(r, product_col)) for r in table}
        only_current = "current" in values
    for row in table:
        if not any(c.strip() for c in row):
            continue
        d = parse_date(_cell(row, mapping.get("date")))
        if not d:
            skipped["ohne Datum"] += 1
            continue
        status = norm(_cell(row, mapping.get("status")))
        if status and SKIP_STATUS.search(status):
            skipped["vorgemerkt/abgebrochen"] += 1
            continue
        if only_current and norm(_cell(row, product_col)) not in ("current", ""):
            skipped["Unterkonto"] += 1
            continue
        if mapping.get("amount") is not None:
            amount = parse_amount(_cell(row, mapping["amount"]))
        else:
            debit = parse_amount(_cell(row, mapping.get("debit"))) or 0
            credit = parse_amount(_cell(row, mapping.get("credit"))) or 0
            amount = (abs(credit) - abs(debit)) if (debit or credit) else None
        if amount is None:
            skipped["ohne Betrag"] += 1
            continue
        if mapping.get("fee_subtract") and mapping.get("fee") is not None:
            fee = parse_amount(_cell(row, mapping["fee"])) or 0
            amount -= abs(fee)
        if mapping.get("invert"):
            amount = -amount
        currency = _cell(row, mapping.get("currency")).upper() or "EUR"
        if currency not in ("EUR", "€"):
            skipped["Fremdwährung"] += 1
            continue
        if amount == 0:
            skipped["Betrag 0"] += 1
            continue
        if mapping.get("counterparty_in") is not None or mapping.get("counterparty_out") is not None:
            cp = _cell(row, mapping.get("counterparty_in")) if amount > 0 else _cell(row, mapping.get("counterparty_out"))
        else:
            cp = _cell(row, mapping.get("counterparty"))
        purpose_raw = " ".join(_cell(row, i) for i in (mapping.get("purpose") or []) if _cell(row, i))
        iban = _cell(row, mapping.get("iban")).replace(" ", "").upper()
        if not cp:
            m = _COMDIRECT_RX.search(purpose_raw)
            if m:
                cp = m.group(1).strip()
                mi = _COMDIRECT_IBAN.search(purpose_raw)
                if mi and not iban:
                    iban = mi.group(1).upper()
                mt = re.search(r"Buchungstext\s*:\s*(.*)$", purpose_raw, re.I)
                if mt:
                    purpose_raw = mt.group(1)
        if purpose_raw.strip() in ("-", "--", "."):
            purpose_raw = ""
        purpose, sepa = clean_purpose(purpose_raw)
        if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", iban or "") or not iban[4:].strip("0"):
            iban = ""
        out.append({
            "booking_date": d.isoformat(),
            "value_date": (parse_date(_cell(row, mapping.get("value_date"))) or d).isoformat(),
            "amount_cents": amount,
            "currency": "EUR",
            "counterparty": cp[:140] or None,
            "counterparty_iban": iban or None,
            "purpose": purpose[:400] or None,
            "booking_text": _cell(row, mapping.get("booking_text"))[:80] or None,
            "creditor_id": _cell(row, mapping.get("creditor_id")) or sepa.get("CRED") or None,
            "mandate_ref": _cell(row, mapping.get("mandate_ref")) or sepa.get("MREF") or None,
            "end_to_end": (_cell(row, mapping.get("end_to_end")) or sepa.get("EREF") or None),
            "balance_cents": parse_amount(_cell(row, mapping.get("balance"))) if mapping.get("balance") is not None else None,
            "own_iban": _cell(row, mapping.get("own_iban")).replace(" ", "").upper() or None,
        })
    for r in out:
        if r["end_to_end"] and r["end_to_end"].upper() in ("NOTPROVIDED", "NONREF"):
            r["end_to_end"] = None
    return out, skipped


_IBAN_RX = re.compile(r"\b([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?)\b")


def _preamble_meta(rows: list[list[str]]) -> dict:
    meta: dict = {}
    for row in rows:
        joined = " ".join(c.strip() for c in row if c.strip())
        if not joined:
            continue
        m = _IBAN_RX.search(joined.upper())
        if m and "iban" not in meta:
            meta["iban"] = m.group(1).replace(" ", "")
        low = norm(joined)
        if re.search(r"(neuer )?kontostand|^saldo|aktueller saldo", low):
            for c in row[1:]:
                cents = parse_amount(c)
                if cents is not None:
                    meta["balance_cents"] = cents
                    md = re.search(r"(\d{2}\.\d{2}\.\d{4})", joined)
                    if md:
                        meta["balance_date"] = parse_date(md.group(1)).isoformat()
                    break
    return meta


def _balance_from_rows(rows: list[dict]) -> tuple[int, str] | None:
    with_bal = [r for r in rows if r.get("balance_cents") is not None]
    if not with_bal:
        return None
    latest = max(r["booking_date"] for r in with_bal)
    cands = [r for r in with_bal if r["booking_date"] == latest]
    if len(cands) == 1:
        return cands[0]["balance_cents"], latest
    prev = {r["balance_cents"] - r["amount_cents"] for r in cands}
    finals = [r for r in cands if r["balance_cents"] not in prev]
    pick = finals[0] if finals else cands[0]
    return pick["balance_cents"], latest


# --- CAMT ---------------------------------------------------------------------

def _strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _t(el: ET.Element | None, path: str) -> str:
    if el is None:
        return ""
    found = el.find(path)
    return (found.text or "").strip() if found is not None and found.text else ""


def parse_camt(xml_bytes: bytes) -> tuple[list[dict], dict]:
    root = _strip_ns(ET.fromstring(xml_bytes))
    rows: list[dict] = []
    meta: dict = {}
    for stmt in root.iter():
        if stmt.tag not in ("Stmt", "Rpt", "Ntfctn"):
            continue
        iban = _t(stmt, "Acct/Id/IBAN")
        if iban:
            meta.setdefault("iban", iban)
        for bal in stmt.findall("Bal"):
            code = _t(bal, "Tp/CdOrPrtry/Cd")
            if code in ("CLBD", "ITBD"):
                cents = parse_amount(_t(bal, "Amt"))
                if cents is not None:
                    if _t(bal, "CdtDbtInd") == "DBIT":
                        cents = -cents
                    d = _t(bal, "Dt/Dt") or _t(bal, "Dt/DtTm")[:10]
                    if code == "CLBD" or "balance_cents" not in meta:
                        meta["balance_cents"], meta["balance_date"] = cents, d
        for ntry in stmt.findall("Ntry"):
            sts = _t(ntry, "Sts") or _t(ntry, "Sts/Cd")
            if sts and sts not in ("BOOK",):
                continue
            amount = parse_amount(_t(ntry, "Amt"))
            if amount is None:
                continue
            debit = _t(ntry, "CdtDbtInd") == "DBIT"
            if _t(ntry, "RvslInd") == "true":
                debit = not debit
            amount = -abs(amount) if debit else abs(amount)
            bdate = parse_date(_t(ntry, "BookgDt/Dt") or _t(ntry, "BookgDt/DtTm")[:10])
            vdate = parse_date(_t(ntry, "ValDt/Dt") or _t(ntry, "ValDt/DtTm")[:10]) or bdate
            if not bdate:
                continue
            txd = ntry.find("NtryDtls/TxDtls")
            party = "Cdtr" if debit else "Dbtr"
            cp = (_t(txd, f"RltdPties/{party}/Nm") or _t(txd, f"RltdPties/{party}/Pty/Nm")
                  or _t(txd, "RltdPties/Ultmt" + party + "/Nm"))
            cp_iban = _t(txd, f"RltdPties/{party}Acct/Id/IBAN")
            purpose = " ".join((u.text or "").strip() for u in (txd.findall("RmtInf/Ustrd") if txd is not None else []) if u.text)
            cred = ""
            if txd is not None:
                for el in txd.iter("CdtrSchmeId"):
                    cred = _t(el, "Id/PrvtId/Othr/Id")
                if not cred:
                    cred = _t(txd, "RltdPties/Cdtr/Id/PrvtId/Othr/Id")
            clean, sepa = clean_purpose(purpose)
            e2e = _t(txd, "Refs/EndToEndId")
            rows.append({
                "booking_date": bdate.isoformat(), "value_date": vdate.isoformat(), "amount_cents": amount, "currency": "EUR",
                "counterparty": cp or None, "counterparty_iban": cp_iban or None, "purpose": clean or None,
                "booking_text": _t(ntry, "AddtlNtryInf")[:80] or None,
                "creditor_id": cred or sepa.get("CRED") or None, "mandate_ref": _t(txd, "Refs/MndtId") or sepa.get("MREF") or None,
                "end_to_end": None if e2e.upper() in ("", "NOTPROVIDED") else e2e, "balance_cents": None, "own_iban": iban or None,
            })
    return rows, meta


# --- MT940 --------------------------------------------------------------------

def row_from_mt940(data: dict) -> dict | None:
    """Wandelt ein Transaktions-dict aus mt-940 bzw. python-fints in eine Buchungszeile."""
    amt = data.get("amount")
    if amt is None:
        return None
    value = getattr(amt, "amount", amt)
    currency = getattr(amt, "currency", None) or data.get("currency") or "EUR"
    cents = parse_amount(value)
    if cents is None:
        return None
    bdate = data.get("entry_date") or data.get("guessed_entry_date") or data.get("date")
    vdate = data.get("date") or bdate
    if isinstance(bdate, str):
        bdate = parse_date(bdate)
    if isinstance(vdate, str):
        vdate = parse_date(vdate)
    if not bdate:
        return None
    purpose_raw = data.get("purpose") or ""
    if isinstance(purpose_raw, (list, tuple)):
        purpose_raw = " ".join(purpose_raw)
    clean, sepa = clean_purpose(purpose_raw)
    e2e = data.get("end_to_end_reference") or sepa.get("EREF")
    if e2e and str(e2e).upper() in ("NOTPROVIDED", "NONREF"):
        e2e = None
    return {
        "booking_date": bdate.isoformat(),
        "value_date": (vdate or bdate).isoformat(),
        "amount_cents": cents,
        "currency": str(currency),
        "counterparty": (data.get("applicant_name") or "").strip() or None,
        "counterparty_iban": (data.get("applicant_iban") or "").replace(" ", "").upper() or None,
        "purpose": clean or None,
        "booking_text": (data.get("posting_text") or "").strip()[:80] or None,
        "creditor_id": data.get("creditor_id") or data.get("applicant_creditor_id") or sepa.get("CRED") or None,
        "mandate_ref": data.get("mandate_reference") or data.get("additional_position_reference") or sepa.get("MREF") or None,
        "end_to_end": e2e or None,
        "balance_cents": None,
        "own_iban": None,
    }


def mt940_transactions(text: str):
    """MT940 mit den Optionen, die deutsche Banken brauchen (?31 = IBAN, SEPA-Felder vollständig)."""
    import mt940

    opts = mt940.processors.Options(applicant_iban=True, merge_keeps_values=True, reversal_sign=True,
                                    case_insensitive_marks=True, unbounded_details=True, strip_bom=True)
    transactions = mt940.models.Transactions(options=opts)
    transactions.parse(text.lstrip("\ufeff"))
    return transactions


def parse_mt940(text: str) -> tuple[list[dict], dict]:
    text = text.replace("\r\n", "\n")
    transactions = mt940_transactions(text)
    rows = [r for r in (row_from_mt940(t.data) for t in transactions) if r]
    meta: dict = {}
    closing = transactions.data.get("final_closing_balance")
    if closing is not None:
        meta["balance_cents"] = parse_amount(closing.amount.amount)
        meta["balance_date"] = closing.date.isoformat() if closing.date else None
    acc = transactions.data.get("account_identification")
    if acc and re.match(r"^[A-Z]{2}\d{2}", acc):
        meta["iban"] = acc
    return rows, meta


# --- Einstieg -------------------------------------------------------------------

def _guess_preset_by_filename(filename: str, preset):
    if preset:
        return preset
    low = (filename or "").lower()
    for p in PRESETS:
        if p.get("any_name") and p["any_name"] in low:
            return p
    return None


def analyze(data: bytes, filename: str, mapping_override: dict | None = None) -> dict:
    """Liest eine Datei und liefert erkannte Buchungen samt Zuordnung."""
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError(f"Die Datei überschreitet das Importlimit von {MAX_IMPORT_BYTES // (1024 * 1024)} MB.")
    name = (filename or "").lower()
    if zipfile.is_zipfile(io.BytesIO(data)):
        rows, meta = [], {}
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError(f"Das ZIP-Archiv enthält mehr als {MAX_ZIP_ENTRIES} Einträge.")
            expanded_size = sum(info.file_size for info in infos if not info.is_dir())
            if expanded_size > MAX_ZIP_EXPANDED_BYTES:
                raise ValueError("Das ZIP-Archiv überschreitet die zulässige entpackte Gesamtgröße.")
            for info in infos:
                if info.is_dir() or not info.filename.lower().endswith(".xml"):
                    continue
                if info.flag_bits & 0x1:
                    raise ValueError("Verschlüsselte ZIP-Einträge werden nicht unterstützt.")
                if info.file_size > MAX_XML_FILE_BYTES:
                    raise ValueError("Eine XML-Datei im ZIP-Archiv ist zu groß.")
                # Read at most one byte beyond the limit, even if ZIP metadata is misleading.
                with zf.open(info) as member:
                    xml_bytes = member.read(MAX_XML_FILE_BYTES + 1)
                if len(xml_bytes) > MAX_XML_FILE_BYTES:
                    raise ValueError("Eine XML-Datei im ZIP-Archiv überschreitet das Größenlimit.")
                r, m = parse_camt(xml_bytes)
                rows += r
                for k, v in m.items():
                    if k == "balance_date" and meta.get("balance_date") and v and v < meta["balance_date"]:
                        continue
                    meta[k] = v if k != "iban" or "iban" not in meta else meta[k]
        return _result("camt", "CAMT (ZIP)", rows, meta, None)
    head = data[:2048].lstrip()
    if head.startswith(b"<") or name.endswith(".xml"):
        rows, meta = parse_camt(data)
        return _result("camt", "CAMT", rows, meta, None)
    text = decode(data)
    if re.search(r"^:20:", text, re.M) and re.search(r"^:61:", text, re.M):
        rows, meta = parse_mt940(text)
        return _result("mt940", "MT940", rows, meta, None)

    delim = sniff_delimiter(text)
    table = list(csv.reader(io.StringIO(text), delimiter=delim))
    hidx = _find_header(table)
    if hidx < 0:
        return {"kind": "csv", "error": "Keine Kopfzeile mit Datum und Betrag gefunden. Prüfe, ob du den Umsatz-Export als CSV gewählt hast.",
                "headers": [], "rows": [], "meta": {}}
    headers = [h.strip() for h in table[hidx]]
    body = table[hidx + 1:]
    mapping, preset = auto_mapping(headers)
    preset = _guess_preset_by_filename(filename, preset)
    if mapping_override:
        for k, v in mapping_override.items():
            if k in FIELDS or k in ("invert", "fee_subtract"):
                mapping[k] = v
    rows, skipped = convert_rows(body, mapping)
    meta = _preamble_meta(table[:hidx])
    if meta.get("balance_cents") is not None and not meta.get("balance_date") and rows:
        meta["balance_date"] = max(r["booking_date"] for r in rows)
    bal = _balance_from_rows(rows)
    if bal:
        meta["balance_cents"], meta["balance_date"] = bal
    own = [r["own_iban"] for r in rows if r.get("own_iban")]
    if own and "iban" not in meta:
        meta["iban"] = Counter(own).most_common(1)[0][0]
    res = _result("csv", preset["label"] if preset else "CSV", rows, meta, preset)
    res.update({
        "headers": headers,
        "mapping": mapping,
        "signature": hashlib.sha1("|".join(header_norm(h) for h in headers).encode()).hexdigest()[:16],
        "skipped": dict(skipped),
        "sample_raw": body[:5],
        "delimiter": delim,
    })
    positives = sum(1 for r in rows if r["amount_cents"] > 0)
    res["invert_suggested"] = len(rows) >= 5 and positives / len(rows) > 0.75 and not mapping.get("invert")
    return res


def _result(kind: str, label: str, rows: list[dict], meta: dict, preset) -> dict:
    rows.sort(key=lambda r: r["booking_date"])
    first = rows[0]["booking_date"] if rows else None
    last = rows[-1]["booking_date"] if rows else None
    suggest = {
        "kind": (preset or {}).get("kind", "giro"),
        "name": (preset or {}).get("name") or ("Konto " + meta["iban"][-4:] if meta.get("iban") else "Neues Konto"),
        "settlement": (preset or {}).get("settlement", ""),
    }
    return {"kind": kind, "format": label, "rows": rows, "meta": meta, "count": len(rows), "first": first, "last": last,
            "suggest": suggest, "headers": [], "mapping": None, "skipped": {}, "invert_suggested": False}


def today_iso() -> str:
    return date.today().isoformat()
