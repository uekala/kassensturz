"""Umstieg von Finanzguru: Der Export bringt die Historie und die bisherigen Kategorien mit.

Finanzguru exportiert alle Konten in eine Excel- oder CSV-Datei. Jede Zeile nennt ihr Konto
(„Referenzkonto“) und die Kategorie, die Finanzguru vergeben hat. Übernommen wird in drei Schritten:

1. Buchungen je Konto. Hat ein Konto schon Buchungen aus Bankabruf oder Datei, wird nur die Zeit davor
   aufgefüllt: Für alles danach ist die Bank die Quelle, so entsteht nichts doppelt.
2. Kategorien. Wem du im Dialog eine Kategorie zuordnest, der behält sie – die Buchung gilt als gesetzt
   und wird nicht neu zugeordnet.
3. Lernen. Gegenstellen, die in Finanzguru verlässlich in derselben Kategorie lagen, merkt sich
   Kassensturz wie eine eigene Korrektur. Was du hier schon selbst korrigiert hast, bleibt.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import categorize, importers, ledger
from .db import Database, now_iso
from .util import clean_purpose, norm, parse_amount, parse_date

SOURCE = "finanzguru"
RULE_REF = "finanzguru"
HINT = ("Das ist ein Export aus Finanzguru mit mehreren Konten. Lade ihn unter Konten über „Datei importieren“ hoch; "
        "dort ordnest du Konten und Kategorien zu.")

MAX_SHEET_BYTES = 150 * 1024 * 1024
MAX_STRINGS_BYTES = 60 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 200
MAX_SHEETS = 5

# Kontoarten, die ein neues Konto aus dem Export haben kann: solche mit Buchungen.
KINDS = ("giro", "tagesgeld", "sparkonto", "kreditkarte", "paypal", "bargeld", "sonstiges")

# Gelernt wird nur, was in Finanzguru mehrfach und fast immer gleich zugeordnet war.
LEARN_MIN = 2
LEARN_PURITY = 0.8

COLUMNS = {
    "date": "buchungstag", "ref": "referenzkonto", "account_name": "name referenzkonto", "amount": "betrag",
    "balance": "kontostand", "currency": "waehrung", "counterparty": "beguenstigter auftraggeber",
    "iban": "iban beguenstigter auftraggeber", "purpose": "verwendungszweck", "end_to_end": "e ref",
    "mandate_ref": "mandatsreferenz", "creditor_id": "glaeubiger id", "main": "analyse hauptkategorie",
    "sub": "analyse unterkategorie", "transfer": "analyse umbuchung", "id": "buchungs id",
    "original": "referenz original id", "split": "split typ", "tags": "tags", "note": "notiz",
}
_MARKERS = {COLUMNS[k] for k in ("ref", "account_name", "main", "sub", "transfer")}
_TRUE = {"ja", "true", "wahr", "yes", "1", "x"}
_IBAN = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}")


# --- Excel lesen ----------------------------------------------------------------------------

class _Guard:
    """Liest einen Eintrag aus dem Archiv, aber höchstens ``limit`` Bytes und ohne DOCTYPE."""

    def __init__(self, raw, limit: int):
        self.raw, self.left, self.first = raw, limit, True

    def read(self, size: int = -1) -> bytes:
        block = self.raw.read(65536 if size is None or size < 0 else size)
        self.left -= len(block)
        if self.left < 0:
            raise ValueError("Die Excel-Datei ist entpackt zu groß.")
        if self.first:
            self.first = False
            if b"<!DOCTYPE" in block or b"<!ENTITY" in block:
                raise ValueError("Die Excel-Datei enthält unerwartete Angaben.")
        return block


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def is_workbook(data: bytes) -> bool:
    """Ob die Bytes eine Excel-Datei (.xlsx) sind."""
    if not zipfile.is_zipfile(io.BytesIO(data)):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return "xl/workbook.xml" in archive.namelist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError, NotImplementedError):
        return False


def _open(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> _Guard:
    if info.flag_bits & 0x1:
        raise ValueError("Verschlüsselte Excel-Dateien werden nicht unterstützt.")
    return _Guard(archive.open(info), limit)


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        info = archive.getinfo("xl/sharedStrings.xml")
    except KeyError:
        return []
    out: list[str] = []
    for _event, el in ET.iterparse(_open(archive, info, MAX_STRINGS_BYTES)):
        if _local(el.tag) != "si":
            continue
        parts = []
        for child in el:
            name = _local(child.tag)
            if name == "t":
                parts.append(child.text or "")
            elif name == "r":  # formatierter Text in Stücken; Lautschrift (rPh) bleibt außen vor
                parts += [t.text or "" for t in child if _local(t.tag) == "t"]
        out.append("".join(parts))
        el.clear()
    return out


def _column(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _sheet(archive: zipfile.ZipFile, info: zipfile.ZipInfo, shared: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for _event, el in ET.iterparse(_open(archive, info, MAX_SHEET_BYTES)):
        if _local(el.tag) != "row":
            continue
        cells: list[str] = []
        following = 0
        for cell in el:
            if _local(cell.tag) != "c":
                continue
            ref = cell.get("r") or ""
            index = _column(ref) if ref else following
            if not 0 <= index < MAX_COLUMNS:
                continue
            kind = cell.get("t") or "n"
            if kind == "inlineStr":
                value = "".join(t.text or "" for t in cell.iter() if _local(t.tag) == "t")
            else:
                raw = next(((v.text or "") for v in cell if _local(v.tag) == "v"), "")
                if kind == "s":
                    try:
                        value = shared[int(raw)]
                    except (ValueError, IndexError):
                        value = ""
                elif kind == "b":
                    value = "ja" if raw.strip() == "1" else "nein"
                else:
                    value = raw
            if len(cells) <= index:
                cells += [""] * (index + 1 - len(cells))
            cells[index] = value
            following = index + 1
        rows.append(cells)
        el.clear()
        if len(rows) > MAX_ROWS:
            raise ValueError(f"Die Excel-Datei hat mehr als {MAX_ROWS} Zeilen.")
    return rows


def read_workbook(data: bytes) -> list[list[list[str]]]:
    """Die Tabellenblätter einer .xlsx-Datei als Zeilen aus Text. Ohne Formeln, ohne Formate."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > importers.MAX_ZIP_ENTRIES:
            raise ValueError(f"Die Excel-Datei enthält mehr als {importers.MAX_ZIP_ENTRIES} Einträge.")
        sheets = sorted((i for i in infos if re.fullmatch(r"xl/worksheets/[^/]+\.xml", i.filename)),
                        key=lambda i: (len(i.filename), i.filename))
        try:
            shared = _shared_strings(archive)
            return [_sheet(archive, info, shared) for info in sheets[:MAX_SHEETS]]
        except (ET.ParseError, zipfile.BadZipFile, EOFError) as error:
            raise ValueError("Die Excel-Datei ist beschädigt.") from error


# --- Export erkennen und lesen --------------------------------------------------------------

def header_row(table: list[list[str]]) -> int:
    """Zeile mit den Spaltennamen des Finanzguru-Exports, oder -1."""
    for i, row in enumerate(table[:30]):
        cells = {importers.header_norm(c) for c in row if c and c.strip()}
        if {COLUMNS["date"], COLUMNS["amount"]} <= cells and len(cells & _MARKERS) >= 2:
            return i
    return -1


def _date(value: str) -> date | None:
    text = (value or "").strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", text):
        # Excel zählt Tage seit Ende 1899.
        return date(1899, 12, 30) + timedelta(days=int(float(text)))
    return parse_date(text)


def _amount(value: str) -> int | None:
    text = (value or "").strip()
    if re.fullmatch(r"-?\d+(\.\d+)?[eE][-+]?\d+", text):
        try:
            return round(float(text) * 100)
        except (ValueError, OverflowError):
            return None
    return parse_amount(text)


def parse(table: list[list[str]], start: int) -> dict:
    """Zeilen des Exports als Buchungen, in der Reihenfolge der Datei."""
    names = [importers.header_norm(c) for c in table[start]]
    col = {field: names.index(name) if name in names else None for field, name in COLUMNS.items()}

    def cell(row: list[str], field: str) -> str:
        i = col[field]
        return (row[i] or "").strip() if i is not None and i < len(row) else ""

    rows: list[dict] = []
    skipped: Counter = Counter()
    for row in table[start + 1:]:
        if not any((c or "").strip() for c in row):
            continue
        day = _date(cell(row, "date"))
        if not day:
            skipped["ohne Datum"] += 1
            continue
        amount = _amount(cell(row, "amount"))
        if amount is None:
            skipped["ohne Betrag"] += 1
            continue
        if cell(row, "currency").upper() not in ("", "EUR", "€"):
            skipped["Fremdwährung"] += 1
            continue
        if amount == 0:
            skipped["Betrag 0"] += 1
            continue
        ref = re.sub(r"\s+", "", cell(row, "ref"))
        name = " ".join(cell(row, "account_name").split())
        iban = re.sub(r"\s+", "", cell(row, "iban")).upper()
        if not _IBAN.fullmatch(iban) or not iban[4:].strip("0"):
            iban = ""
        purpose, sepa = clean_purpose(cell(row, "purpose"))
        end_to_end = cell(row, "end_to_end") or sepa.get("EREF") or ""
        iso = day.isoformat()
        rows.append({
            "ref": (ref.upper() if _IBAN.fullmatch(ref.upper()) else ref) or name or "?",
            "account_name": name,
            "booking_date": iso, "value_date": iso, "amount_cents": amount, "currency": "EUR",
            "counterparty": cell(row, "counterparty")[:140] or None, "counterparty_iban": iban or None,
            "purpose": purpose[:400] or None, "booking_text": None,
            "creditor_id": cell(row, "creditor_id") or sepa.get("CRED") or None,
            "mandate_ref": cell(row, "mandate_ref") or sepa.get("MREF") or None,
            "end_to_end": None if end_to_end.upper() in ("", "NOTPROVIDED", "NONREF") else end_to_end,
            "balance_cents": _amount(cell(row, "balance")) if col["balance"] is not None else None,
            "main": " ".join(cell(row, "main").split()), "sub": " ".join(cell(row, "sub").split()),
            "transfer": norm(cell(row, "transfer")) in _TRUE,
            "note": _note(cell(row, "note"), cell(row, "tags")),
            "id": cell(row, "id"), "original": cell(row, "original"), "split": cell(row, "split"),
            "parts": [], "rest": None,
        })
    rows, splits = _fold_splits(rows)
    return {"rows": rows, "skipped": dict(skipped), "splits": splits}


def _note(note: str, tags: str) -> str | None:
    """Notiz und Tags aus Finanzguru als Notiz der Buchung; die Tags bleiben als Text erhalten."""
    parts = [" ".join(note.split()), f"Tags: {' '.join(tags.split())}" if tags.strip() else ""]
    return " · ".join(p for p in parts if p)[:500] or None


# So kennzeichnet Finanzguru eine aufgeteilte Buchung in der Spalte „Split-Typ“: die Buchung der Bank,
# darunter ihre Teile und, wenn die Teile nicht alles abdecken, der Rest.
_SPLIT_ORIGINAL = "original"
_SPLIT_PART = "teilbuchung"
_SPLIT_REST = "restbetrag"


def _fold_splits(rows: list[dict]) -> tuple[list[dict], dict]:
    """Aufgeteilte Buchungen: Übrig bleibt die Buchung der Bank, die Teile hängen an ihr.

    Im Export stehen das „Original“ und darunter seine „Teilbuchungen“ samt „Restbetrag“. Übernähme
    man alle Zeilen, zählte derselbe Betrag doppelt. Deshalb wird nur das Original zur Buchung. Die
    Teile werden zu ihrer Aufteilung, wenn sie zusammen genau den Betrag ergeben; sonst kommt die
    Buchung ohne Aufteilung. Zu welchem Original ein Teil gehört, sagt seine „Referenz-Original-ID“,
    ersatzweise die Reihenfolge der Zeilen. Teile ohne erkennbares Original bleiben eigene Zeilen
    und werden im Dialog genannt."""
    by_id = {r["id"]: r for r in rows if r["id"]}
    groups: dict[int, tuple[dict, list[dict]]] = {}
    stats = {"taken": 0, "plain": 0, "unclear": 0}
    above = None  # das Original, unter dem die gerade gelesenen Zeilen stehen
    for r in rows:
        kind = norm(r["split"])
        if kind not in (_SPLIT_PART, _SPLIT_REST):
            above = r if kind == _SPLIT_ORIGINAL else None
            continue
        parent = by_id.get(r["original"]) if r["original"] and r["original"] != r["id"] else None
        if parent is None and above is not None and above["ref"] == r["ref"]:
            parent = above
        if parent is None or parent["ref"] != r["ref"]:
            stats["unclear"] += 1
            continue
        groups.setdefault(id(parent), (parent, []))[1].append(r)
    folded: set[int] = set()
    for parent, members in groups.values():
        folded.update(id(m) for m in members)
        fits = (all(m["amount_cents"] * parent["amount_cents"] > 0 for m in members)
                and sum(m["amount_cents"] for m in members) == parent["amount_cents"])
        if not fits:
            stats["plain"] += 1
            continue
        parent["parts"] = [m for m in members if norm(m["split"]) == _SPLIT_PART]
        parent["rest"] = next((m for m in members if norm(m["split"]) == _SPLIT_REST), None)
        stats["taken"] += 1
    return [r for r in rows if id(r) not in folded], stats


def from_workbook(data: bytes) -> dict:
    """Liest eine Excel-Datei; alles außer dem Finanzguru-Export wird abgelehnt."""
    for table in read_workbook(data):
        start = header_row(table)
        if start >= 0:
            return parse(table, start)
    raise ValueError("Excel-Dateien liest Kassensturz nur als Export aus Finanzguru. "
                     "Exportiere die Umsätze bei deiner Bank als CSV.")


# --- Kategorien zuordnen --------------------------------------------------------------------

# Namen, die nichts sagen: Hier ordnet Kassensturz lieber selbst zu.
_VAGUE = re.compile(r"sonstig|unkategorisiert|unbekannt|divers|nicht zugeordnet|ohne kategorie|allgemein")

# (Kategorie, Suchwörter) in der Reihenfolge, in der geprüft wird. Wörter bis drei Buchstaben müssen
# allein stehen, vier Buchstaben am Wortanfang, längere irgendwo im Namen.
_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("umbuchung", ("umbuchung", "uebertrag", "eigene konten")),
    ("auto", ("kfz-steuer", "kfz steuer", "kraftfahrzeugsteuer")),
    ("gehalt", ("gehalt", "lohn", "rente", "pension", "kindergeld", "elterngeld", "arbeitslosengeld", "buergergeld")),
    ("erstattungen", ("erstattung", "rueckzahlung", "cashback")),
    ("sparen", ("altersvorsorge", "sparplan", "sparen", "invest", "wertpapier", "depot", "geldanlage", "bauspar",
                "vermoegensaufbau", "aktien", "etf")),
    ("kredite", ("kredit", "darlehen", "tilgung", "finanzierung", "leasing", "rate")),
    ("versicherungen", ("versicherung", "krankenkasse", "haftpflicht", "hausrat", "rechtsschutz")),
    ("steuern", ("steuer", "abgaben", "finanzamt")),
    ("gebuehren", ("gebuehr", "zinsen", "kontofuehrung")),
    ("bargeld", ("bargeld", "geldautomat", "abhebung", "bar")),
    ("spenden", ("spende", "geschenk")),
    ("miete", ("miete", "nebenkosten", "hausgeld")),
    ("energie", ("strom", "heizung", "energie", "wasser", "fernwaerme", "gas")),
    ("internet", ("internet", "telefon", "mobilfunk", "handy", "telekommunikation", "festnetz", "dsl")),
    ("rundfunk", ("rundfunk", "gez")),
    ("haushalt", ("moebel", "einrichtung", "haushalt", "garten", "heimwerk", "baumarkt", "haustier", "tierbedarf",
                  "renovier")),
    ("supermarkt", ("lebensmittel", "supermarkt", "getraenke", "baecker")),
    ("drogerie", ("drogerie", "kosmetik", "koerperpflege", "friseur")),
    ("restaurant", ("restaurant", "gastronomie", "lieferdienst", "essen gehen", "fast food", "fastfood", "kneipe",
                    "ausgehen", "imbiss", "cafe", "bars")),
    ("laden", ("kraftstoff", "benzin", "ladestrom", "tank")),
    ("parken", ("parken", "parkgebuehr", "maut")),
    ("oepnv", ("oepnv", "nahverkehr", "oeffentliche verkehrsmittel", "carsharing", "fahrkarte", "bahn", "taxi", "bus")),
    ("auto", ("werkstatt", "fahrzeug", "motorrad", "auto", "kfz")),
    ("streaming", ("streaming", "musik", "video", "fernsehen", "gaming", "tv")),
    ("software", ("software", "cloud", "digital", "hosting", "apps")),
    ("presse", ("zeitung", "zeitschrift", "magazin", "presse")),
    ("kleidung", ("kleidung", "schuhe", "schmuck", "accessoires", "mode")),
    ("elektronik", ("elektronik", "technik", "computer", "hardware")),
    ("online", ("online", "versandhandel", "marktplatz")),
    ("shopping", ("shopping", "kaufhaus")),
    ("reisen", ("reise", "urlaub", "hotel", "fluege", "unterkunft", "mietwagen", "flug")),
    ("hobby", ("hobby", "sport", "fitness", "verein", "kultur", "unterhaltung", "veranstaltung", "konzert", "buecher",
               "kino")),
    ("freizeit", ("freizeit",)),
    ("gesundheit", ("gesundheit", "aerzt", "apotheke", "medizin", "medikament", "therapie", "optiker", "pflege",
                    "arzt")),
    ("bildung", ("bildung", "schule", "studium", "kinderbetreuung", "nachhilfe", "kita", "kurs")),
    ("wohnen", ("wohnen", "wohnung")),
    ("mobilitaet", ("mobilitaet", "verkehr", "transport")),
    ("abos", ("abonnement", "mitgliedschaft", "abos", "abo")),
    ("finanzen", ("finanzen",)),
    ("sonstige_einnahmen", ("einnahme", "einkommen", "einkuenfte")),
]


def _hint(text: str) -> str | None:
    words = re.findall(r"[a-z0-9]+", text)
    for key, terms in _HINTS:
        for term in terms:
            if len(term) <= 3:
                hit = term in words
            elif len(term) == 4:
                hit = any(w.startswith(term) for w in words)
            else:
                hit = term in text
            if hit:
                return key
    return None


def suggest_category(categories: list[dict], main: str, sub: str) -> int | None:
    """Vorschlag für eine Finanzguru-Kategorie: gleicher Name, sonst ein passendes Stichwort."""
    by_name: dict[str, int] = {}
    for c in categories:
        by_name.setdefault(norm(c["name"]), c["id"])
    by_key = {c["builtin_key"]: c["id"] for c in categories if c.get("builtin_key")}
    for text in (norm(sub), norm(main)):
        if not text or _VAGUE.search(text):
            continue
        if text in by_name:
            return by_name[text]
        key = _hint(text)
        if key in by_key:
            return by_key[key]
    return None


# --- Vorschau -------------------------------------------------------------------------------

def _entries(rows: list[dict]):
    """Buchungen und, wo eine aufgeteilt ist, statt ihrer die Teile und der Rest."""
    for r in rows:
        if r.get("parts"):
            yield from r["parts"]
            if r.get("rest"):
                yield r["rest"]
        else:
            yield r


def _by_account(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["ref"], []).append(r)
    return out


def _guess_kind(name: str, ref: str) -> str:
    text = norm(name)
    if "paypal" in text or "@" in ref:
        return "paypal"
    if re.search(r"kreditkarte|visa|mastercard|american express|amex|credit", text):
        return "kreditkarte"
    if "tagesgeld" in text:
        return "tagesgeld"
    if "spar" in text:
        return "sparkonto"
    return "giro"


def _label(ref: str) -> str:
    if _IBAN.fullmatch(ref):
        return f"{ref[:4]} … {ref[-4:]}"
    return ref if len(ref) <= 28 else ref[:27] + "…"


def first_bank_date(db: Database, account_id: int) -> str | None:
    """Erster Buchungstag, der nicht aus Finanzguru stammt. Davor füllt der Export auf."""
    return db.scalar("SELECT MIN(booking_date) FROM transactions WHERE account_id = ? AND COALESCE(source, '') != ?",
                     (account_id, SOURCE))


def _match_account(accounts: list[dict], ref: str, name: str) -> int | None:
    for a in accounts:
        if a["iban"] and re.sub(r"\s+", "", a["iban"]).upper() == ref:
            return a["id"]
    same = [a for a in accounts if name and norm(a["name"]) == norm(name)]
    return same[0]["id"] if len(same) == 1 else None


def preview(db: Database, parsed: dict, choices: dict | None = None) -> dict:
    """Was im Dialog steht: die Konten des Exports mit Ziel und die Kategorien mit Vorschlag."""
    choices = choices or {}
    accounts = db.query("SELECT id, name, iban FROM accounts WHERE archived = 0 ORDER BY sort, id")
    known = {a["id"] for a in accounts}
    out_accounts = []
    for ref, rows in _by_account(parsed["rows"]).items():
        name = next((r["account_name"] for r in rows if r["account_name"]), "")
        target = choices.get(ref)
        if target not in ("new", "skip") and target not in known:
            target = _match_account(accounts, ref, name) or "new"
        cutoff = first_bank_date(db, target) if isinstance(target, int) else None
        days = [r["booking_date"] for r in rows]
        out_accounts.append({
            "ref": ref, "name": name or "Konto ohne Namen", "label": _label(ref) if ref != name else "",
            "count": len(rows), "first": min(days), "last": max(days), "target": target, "cutoff": cutoff,
            "will_add": 0 if target == "skip" else sum(1 for d in days if not cutoff or d < cutoff),
            "suggest": {"name": (name or f"Konto {ref[-4:]}")[:60], "kind": _guess_kind(name, ref)},
        })
    categories = db.query("SELECT id, name, builtin_key FROM categories ORDER BY sort, id")
    pairs: dict[tuple[str, str], list[int]] = {}
    for r in _entries(parsed["rows"]):
        if not r["transfer"] and (r["main"] or r["sub"]):
            pairs.setdefault((r["main"], r["sub"]), []).append(r["amount_cents"])
    out_categories = [{
        "main": main, "sub": sub, "count": len(amounts),
        "sign": "in" if sum(1 for a in amounts if a > 0) * 2 > len(amounts) else "out",
        "suggest": suggest_category(categories, main, sub),
    } for (main, sub), amounts in sorted(pairs.items(), key=lambda item: (-len(item[1]), item[0]))]
    days = [r["booking_date"] for r in parsed["rows"]]
    return {
        "format": "Finanzguru", "count": len(parsed["rows"]), "first": min(days) if days else None,
        "last": max(days) if days else None, "skipped": parsed["skipped"], "accounts": out_accounts,
        "categories": out_categories, "transfers": sum(1 for r in parsed["rows"] if r["transfer"]),
        "splits": parsed.get("splits") or {"taken": 0, "plain": 0, "unclear": 0},
    }


# --- Übernehmen -----------------------------------------------------------------------------

def _closing_balance(rows: list[dict]) -> tuple[int, str] | None:
    """Der letzte Kontostand aus dem Export – aber nur, wenn die Spalte nachweislich mitläuft.

    Geprüft wird an den Daten selbst: Der Stand muss sich von Zeile zu Zeile um den Betrag ändern,
    vorwärts oder rückwärts sortiert. Passt das nicht, bleibt der Kontostand offen."""
    seq = [r for r in rows if r.get("balance_cents") is not None]
    if len(seq) < 4 or len(seq) < 0.9 * len(rows):
        return None
    pairs = len(seq) - 1
    forward = sum(1 for a, b in zip(seq, seq[1:]) if b["balance_cents"] - a["balance_cents"] == b["amount_cents"])
    backward = sum(1 for a, b in zip(seq, seq[1:]) if a["balance_cents"] - b["balance_cents"] == a["amount_cents"])
    if forward >= 0.9 * pairs and seq[-1]["booking_date"] >= seq[0]["booking_date"]:
        last = seq[-1]
    elif backward >= 0.9 * pairs and seq[0]["booking_date"] >= seq[-1]["booking_date"]:
        last = seq[0]
    else:
        return None
    return last["balance_cents"], last["booking_date"]


def _category_for_new(db: Database, main: str, sub: str, sign: str) -> int:
    """Legt eine Kategorie aus Finanzguru an oder nimmt die mit gleichem Namen."""
    def find(name: str) -> dict | None:
        wanted = norm(name)
        return next((c for c in db.query("SELECT id, name, parent_id, kind FROM categories ORDER BY sort, id")
                     if norm(c["name"]) == wanted), None)

    def create(name: str, parent: dict | None) -> dict:
        kind = parent["kind"] if parent else ("income" if sign == "in" else "expense")
        sort = (db.scalar("SELECT MAX(sort) FROM categories") or 0) + 10
        cid = db.insert("categories", {"name": name[:60], "parent_id": parent["id"] if parent else None, "kind": kind,
                                       "sort": sort})
        return {"id": cid, "name": name, "parent_id": parent["id"] if parent else None, "kind": kind}

    if not sub or not main:
        name = sub or main
        return (find(name) or create(name, None))["id"]
    existing = find(sub)
    if existing:
        return existing["id"]
    parent = find(main) or create(main, None)
    if parent["parent_id"]:  # Kategorien sind höchstens zwei Ebenen tief
        parent = db.one("SELECT id, name, parent_id, kind FROM categories WHERE id = ?", (parent["parent_id"],)) or parent
    return create(sub, parent)["id"]


def _learn(db: Database, rows: list[dict], target: dict) -> int:
    """Merkt sich Gegenstellen, die in Finanzguru verlässlich in einer Kategorie lagen. Vorhandenes bleibt."""
    kinds = {c["id"]: c["kind"] for c in db.query("SELECT id, kind FROM categories")}
    groups: dict[tuple[str, str], Counter] = defaultdict(Counter)
    sample: dict[tuple[str, str, int], dict] = {}
    for r in rows:
        category = None if r["transfer"] or r.get("parts") else target.get((r["main"], r["sub"]))
        if not category or kinds.get(category) == "transfer":
            continue
        keys = categorize.learn_keys(r)
        if not keys:
            continue
        sign = "in" if r["amount_cents"] > 0 else "out"
        groups[(keys[0], sign)][category] += 1
        sample[(keys[0], sign, category)] = r
    learned = 0
    for (key, sign), counts in groups.items():
        category, hits = counts.most_common(1)[0]
        total = sum(counts.values())
        if total < LEARN_MIN or hits / total < LEARN_PURITY:
            continue
        if db.one("SELECT 1 FROM learned_categories WHERE key = ? AND sign = ?", (key, sign)):
            continue
        row = sample[(key, sign, category)]
        label = " ".join((row.get("counterparty") or "").split())[:60]
        if key.startswith("via:"):
            label = f"{label}: {key[4:]}"[:60]
        parent = db.insert("learned_categories", {"key": key, "sign": sign, "label": label, "category_id": category,
                                                  "updated": now_iso()})
        for other in categorize.learn_keys(row)[1:]:
            db.execute("INSERT INTO learned_categories(key, sign, label, category_id, updated, parent_id) "
                       "VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(key, sign) DO NOTHING",
                       (other, sign, label, category, now_iso(), parent))
        learned += 1
    return learned


def commit(db: Database, parsed: dict, accounts: list[dict], categories: list[dict], learn: bool = True,
           filename: str | None = None) -> dict:
    """Übernimmt den Export. Alles oder nichts: Schlägt ein Schritt fehl, bleibt die Datenbank, wie sie war."""
    by_account = _by_account(parsed["rows"])
    wanted = {str(a.get("ref")): a for a in accounts if isinstance(a, dict)}
    transfer_id = db.scalar("SELECT id FROM categories WHERE builtin_key = 'umbuchung'")
    result = {"accounts": [], "added": 0, "skipped": 0, "learned": 0, "categories_created": 0}
    with db.tx(immediate=True):
        before = db.scalar("SELECT COUNT(*) FROM categories")
        signs = {(c["main"], c["sub"]): c["sign"] for c in preview(db, parsed)["categories"]}
        target: dict[tuple[str, str], int] = {}
        for entry in categories:
            if not isinstance(entry, dict):
                continue
            pair = (str(entry.get("main") or ""), str(entry.get("sub") or ""))
            choice = entry.get("target")
            if pair not in signs or choice in (None, "", "auto"):
                continue
            if choice == "new":
                target[pair] = _category_for_new(db, pair[0], pair[1], signs[pair])
            elif db.one("SELECT 1 FROM categories WHERE id = ?", (choice,)):
                target[pair] = int(choice)
            else:
                raise ValueError("Eine gewählte Kategorie gibt es nicht mehr. Bitte den Dialog neu öffnen.")
        result["categories_created"] = db.scalar("SELECT COUNT(*) FROM categories") - before
        kinds = {c["id"]: c["kind"] for c in db.query("SELECT id, kind FROM categories")}
        taken: list[dict] = []
        for ref, rows in by_account.items():
            choice = wanted.get(ref) or {}
            where = choice.get("target")
            if where in (None, "", "skip"):
                continue
            created = where == "new"
            if created:
                name = " ".join(str(choice.get("name") or "").split()) or next(
                    (r["account_name"] for r in rows if r["account_name"]), "") or f"Konto {ref[-4:]}"
                kind = choice.get("kind") if choice.get("kind") in KINDS else _guess_kind(name, ref)
                account_id = db.insert("accounts", {
                    "name": name[:60], "kind": kind, "iban": ref if _IBAN.fullmatch(ref) else None,
                    "in_forecast": 0 if kind in ledger.SAVINGS_KINDS else 1,
                    "sort": int(db.scalar("SELECT COALESCE(MAX(sort), 0) FROM accounts") or 0) + 1, "created": now_iso(),
                })
            else:
                account = db.one("SELECT id FROM accounts WHERE id = ? AND archived = 0", (where,))
                if not account:
                    raise ValueError("Ein gewähltes Konto gibt es nicht mehr. Bitte den Dialog neu öffnen.")
                account_id = account["id"]
            cutoff = first_bank_date(db, account_id)
            fresh = [dict(r) for r in rows if not cutoff or r["booking_date"] < cutoff]
            done = ledger.import_rows(db, account_id, fresh, SOURCE, filename)
            _apply_extras(db, done["ids"], fresh, target, kinds, transfer_id)
            if done["ids"]:
                added_sum = db.scalar(f"SELECT COALESCE(SUM(amount_cents), 0) FROM transactions WHERE id IN "
                                      f"({','.join('?' * len(done['ids']))})", tuple(done["ids"]))
                ledger.note_backfill(db, account_id, int(added_sum))
            if created:
                closing = _closing_balance(rows)
                if closing:
                    ledger.set_balance_anchor(db, account_id, closing[0], closing[1])
            taken += rows
            acc = db.one("SELECT name, balance_date FROM accounts WHERE id = ?", (account_id,))
            result["accounts"].append({
                "account_id": account_id, "name": acc["name"], "created": created, "added": done["added"],
                "skipped": done["skipped"], "held_back": len(rows) - len(fresh), "cutoff": cutoff,
                "balance_known": acc["balance_date"] is not None,
            })
            result["added"] += done["added"]
            result["skipped"] += done["skipped"]
        if not result["accounts"]:
            raise ValueError("Kein Konto gewählt.")
        if learn:
            result["learned"] = _learn(db, taken, target)
        # Neue Konten und Gelerntes wirken auf den Bestand: Umbuchungen zwischen eigenen Konten, Kategorien.
        categorize.recategorize(db)
    return result


def _apply_extras(db: Database, ids: list[int], rows: list[dict], target: dict, kinds: dict,
                  transfer_id: int | None) -> None:
    """Gibt den neu gespeicherten Buchungen mit, was Finanzguru dazu wusste: Kategorie, Notiz, Aufteilung."""
    if not ids:
        return
    pool: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        pool[r["hash"]].append(r)

    def category_of(row: dict) -> int | None:
        return transfer_id if row["transfer"] and transfer_id else target.get((row["main"], row["sub"]))

    updates, notes, splits = [], [], []
    for tx in db.query(f"SELECT id, hash FROM transactions WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)):
        candidates = pool.get(tx["hash"])
        if not candidates:
            continue
        row = candidates.pop() if len(candidates) > 1 else candidates[0]
        if row.get("note"):
            notes.append((row["note"], tx["id"]))
        parts = [(p, category_of(p)) for p in row.get("parts") or []]
        if parts:
            # Teile mit Kategorie werden zur Aufteilung. Was übrig bleibt – der Rest aus Finanzguru und
            # Teile ohne Kategorie –, zählt in Kassensturz zur Kategorie der Buchung selbst.
            splits += [(tx["id"], p["amount_cents"], category, p.get("note")) for p, category in parts if category]
            rest = row.get("rest")
            if rest is not None:
                own = category_of(rest) or category_of(row)
            elif all(category for _, category in parts):
                own = max(parts, key=lambda item: abs(item[0]["amount_cents"]))[1]
            else:
                own = None
            if own:
                updates.append((own, 1 if kinds.get(own) == "transfer" else 0, RULE_REF, tx["id"]))
            continue
        category = category_of(row)
        if category:
            updates.append((category, 1 if kinds.get(category) == "transfer" else 0, RULE_REF, tx["id"]))
    db.executemany("UPDATE transactions SET category_id = ?, is_transfer = ?, rule_ref = ?, category_locked = 1 "
                   "WHERE id = ?", updates)
    db.executemany("UPDATE transactions SET note = ? WHERE id = ?", notes)
    db.executemany("INSERT INTO splits(tx_id, amount_cents, category_id, note) VALUES(?, ?, ?, ?)", splits)


# --- Abgleich vor dem Kündigen -----------------------------------------------------------------

# So weit dürfen Buchungstage zwischen Finanzguru und der Bank auseinanderliegen.
MATCH_DAYS = 3
# Was Finanzguru in den letzten Tagen gebucht hat, darf in Kassensturz noch fehlen: Banken liefern verschieden schnell.
LAG_DAYS = 2
# Konten, die in Finanzguru von Hand geführt werden (Bargeld, eigene Konten), haben eine UUID statt IBAN.
_MANUAL_REF = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _pair(fg: list[dict], ks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Ordnet Buchungen nach Betrag und nächstem Tag (höchstens MATCH_DAYS) einander zu.

    Gibt zurück, was auf jeder Seite übrig bleibt."""
    pool: dict[int, list[dict]] = defaultdict(list)
    for r in ks:
        pool[r["amount_cents"]].append(r)
    missing = []
    for r in sorted(fg, key=lambda x: x["booking_date"]):
        day = date.fromisoformat(r["booking_date"])
        best, gap = None, None
        for cand in pool.get(r["amount_cents"], []):
            d = abs((date.fromisoformat(cand["booking_date"]) - day).days)
            if d <= MATCH_DAYS and (gap is None or d < gap):
                best, gap = cand, d
        if best is None:
            missing.append(r)
        else:
            pool[r["amount_cents"]].remove(best)
    extra = [r for rows in pool.values() for r in rows]
    extra.sort(key=lambda x: x["booking_date"])
    return missing, extra


def _short(r: dict) -> dict:
    return {"date": r["booking_date"], "amount_cents": r["amount_cents"],
            "counterparty": (r.get("counterparty") or r.get("purpose") or "")[:80] or None}


def compare(db: Database, parsed: dict, choices: dict | None = None, today: date | None = None) -> dict:
    """Prüft, ob Kassensturz alles hat, was Finanzguru hat – ohne etwas zu ändern.

    Je Konto im Export: das Konto in Kassensturz, ob es selbst abruft, wann zuletzt, und für die Zeit,
    in der beide Buchungen haben, was auf der einen oder anderen Seite fehlt. Dazu der letzte Kontostand
    aus dem Export gegen den Stand in Kassensturz am selben Tag."""
    today = today or date.today()
    choices = choices or {}
    accounts = db.query("SELECT id, name, kind, iban, eb_uid, connection_id, fints_ref FROM accounts "
                        "WHERE archived = 0 ORDER BY sort, id")
    by_id = {a["id"]: a for a in accounts}
    # Finanzguru Plus schreibt auch erwartete Buchungen in den Export. Sie sind noch nicht geschehen.
    future = sum(1 for r in parsed["rows"] if r["booking_date"] > today.isoformat())
    past = [r for r in parsed["rows"] if r["booking_date"] <= today.isoformat()]
    settled = (today - timedelta(days=LAG_DAYS)).isoformat()
    out = []
    for ref, rows in _by_account(past).items():
        name = next((r["account_name"] for r in rows if r["account_name"]), "") or "Konto ohne Namen"
        manual = bool(_MANUAL_REF.fullmatch(ref))
        target = choices.get(ref)
        if target != "skip" and target not in by_id:
            target = _match_account(accounts, ref, name)
            if target is None and "@" in ref:
                paypal = [a["id"] for a in accounts if a["kind"] == "paypal"]
                target = paypal[0] if len(paypal) == 1 else None
        days = sorted(r["booking_date"] for r in rows)
        item = {"ref": ref, "name": name, "label": "" if manual or ref == name else _label(ref), "count": len(rows),
                "first": days[0], "last": days[-1], "target": target, "account": None, "automatic": False,
                "manual": manual, "last_own": None, "window": None, "missing": [], "missing_count": 0, "extra": [],
                "extra_count": 0, "balance": None, "problems": []}
        out.append(item)
        if target == "skip":
            continue
        if target is None:
            item["problems"].append("Dieses Konto gibt es in Kassensturz noch nicht."
                                    + (" In Finanzguru führst du es von Hand; brauchst du es nicht mehr, stell es auf "
                                       "„Nicht übernehmen“." if manual else ""))
            continue
        acc = by_id[target]
        item["account"] = acc["name"]
        item["automatic"] = bool(acc["eb_uid"] or (acc["connection_id"] and acc["fints_ref"]))
        own = db.query("SELECT booking_date, amount_cents, counterparty, purpose, source FROM transactions "
                       "WHERE account_id = ? AND COALESCE(source, '') != ? ORDER BY booking_date", (target, SOURCE))
        # Gepflegt per Datei (etwa die Advanzia-Abrechnung als PDF): kein eigener Abruf, aber auch kein Hindernis.
        # Ob etwas fehlt, zeigt der Vergleich der Buchungen.
        item["file"] = bool(own) and not item["automatic"] and all(r["source"] in ("datei", "ordner") for r in own)
        # Ein Konto, das Finanzguru selbst nur von Hand kennt, muss Kassensturz nicht abrufen.
        if not item["automatic"] and not manual and not item["file"]:
            item["problems"].append("Kassensturz ruft dieses Konto nicht selbst bei der Bank ab.")
        if not own:
            if not manual:
                item["problems"].append("In Kassensturz gibt es für dieses Konto keine eigenen Buchungen, "
                                        "nur aus Finanzguru.")
            continue
        item["last_own"] = own[-1]["booking_date"]
        start = max(days[0], own[0]["booking_date"])
        # Verglichen wird bis zur jüngsten Buchung in Finanzguru, die nicht mehr ganz frisch ist: Was Finanzguru
        # danach hat und Kassensturz nicht, zeigt einen hängenden Abruf.
        end = max([d for d in days if d <= settled] or [days[0]])
        if item["file"]:
            # Eine Abrechnung reicht nur bis zu ihrem Stichtag; was danach kam, bringt die nächste.
            end = min(end, own[-1]["booking_date"])
        if start > end:
            if days[-1] > own[-1]["booking_date"]:
                item["problems"].append("Finanzguru und Kassensturz haben keinen gemeinsamen Zeitraum.")
            continue
        item["window"] = {"from": start, "to": end}
        # Am Rand des Zeitraums darf eine Buchung ein paar Tage früher oder später auf der anderen Seite liegen.
        lo = (date.fromisoformat(start) - timedelta(days=MATCH_DAYS)).isoformat()
        hi = (date.fromisoformat(end) + timedelta(days=MATCH_DAYS)).isoformat()
        fg_in = [r for r in rows if start <= r["booking_date"] <= end]
        ks_near = [r for r in own if lo <= r["booking_date"] <= hi]
        missing, extra = _pair(fg_in, ks_near)
        # Was Kassensturz nur am Rand mehr hat, gehört zur Zeit außerhalb des Exports
        extra = [r for r in extra if start <= r["booking_date"] <= end]
        item["missing_count"], item["extra_count"] = len(missing), len(extra)
        item["missing"] = [_short(r) for r in missing[:20]]
        item["extra"] = [_short(r) for r in extra[:10]]
        if missing:
            item["problems"].append(f"{len(missing)} {'Buchung' if len(missing) == 1 else 'Buchungen'} aus Finanzguru "
                                    f"{'fehlt' if len(missing) == 1 else 'fehlen'} in Kassensturz.")
            if any(r["booking_date"] > item["last_own"] for r in missing):
                last = item["last_own"]
                item["problems"].append(f"Seit dem {last[8:10]}.{last[5:7]}.{last[:4]} kam für dieses Konto nichts Neues "
                                        "bei Kassensturz an. Prüf den Bankabruf.")
        closing = _closing_balance(rows)
        if closing:
            cents, day = closing
            series = ledger.balance_series(db, [target], date.fromisoformat(day), date.fromisoformat(day))
            mine = series[-1][1] if series else None
            item["balance"] = {"date": day, "finanzguru_cents": cents, "kassensturz_cents": mine,
                               "difference_cents": None if mine is None else mine - cents}
            if mine is not None and mine != cents:
                item["problems"].append("Der Kontostand weicht von Finanzguru ab.")
    checked = [i for i in out if i["target"] != "skip"]
    return {
        "count": len(past),
        "first": min((i["first"] for i in out), default=None),
        "last": max((i["last"] for i in out), default=None),
        "accounts": out,
        "ready": bool(checked) and not any(i["problems"] for i in checked),
        "open": sum(1 for i in checked if i["problems"]),
        "future": future,
    }
