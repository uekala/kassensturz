"""Umstieg von Finanzguru – nur erfundene Daten."""
import io
import os
import time
import zipfile
from datetime import date

import pytest

from kassensturz import finanzguru, importers, ledger, services

HEADERS = [
    "Buchungstag", "Referenzkonto", "Name Referenzkonto", "Betrag", "Kontostand", "Waehrung", "Beguenstigter/Auftraggeber",
    "IBAN Beguenstigter/Auftraggeber", "Verwendungszweck", "E-Ref", "Mandatsreferenz", "Glaeubiger-ID",
    "Analyse-Hauptkategorie", "Analyse-Unterkategorie", "Analyse-Vertrag", "Analyse-Vertragsturnus", "Analyse-Vertrags-ID",
    "Analyse-Umbuchung", "Analyse-Vom frei verfuegbaren Einkommen ausgeschlossen", "Analyse-Umsatzart", "Analyse-Betrag",
    "Analyse-Woche", "Analyse-Monat", "Analyse-Quartal", "Analyse-Jahr", "Buchungs-ID", "Referenz-Original-ID", "Split-Typ",
    "Tags", "Notiz",
]
GIRO = "DE02120300000000202051"
PAYPAL = "erfunden@example.org"


def row(day, account, amount, who, purpose="", main="", sub="", transfer="nein", balance=None, currency="EUR",
        iban="", creditor="", id="", original="", split="", tags="", note=""):
    ref, name = account
    return [day, ref, name, amount, balance, currency, who, iban, purpose, "", "", creditor, main, sub, "", "", "",
            transfer, "nein", "", amount, "", "", "", "", id, original, split, tags, note]


GIRO_ACC = (GIRO, "Erfundenes Girokonto")
PAYPAL_ACC = (PAYPAL, "PayPal")


def _letters(index: int) -> str:
    out = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        out = chr(65 + rest) + out
    return out


def workbook(rows, headers=HEADERS, doctype=False) -> bytes:
    """Eine kleine .xlsx-Datei, wie Excel sie schreibt: Texte in sharedStrings, Zahlen direkt."""
    strings: list[str] = []
    index: dict[str, int] = {}
    lines = []
    for number, cells in enumerate([headers, *rows], start=1):
        parts = []
        for col, value in enumerate(cells):
            if value is None or value == "":
                continue
            ref = f"{_letters(col)}{number}"
            if isinstance(value, (int, float)):
                parts.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                if value not in index:
                    index[value] = len(strings)
                    strings.append(value)
                parts.append(f'<c r="{ref}" t="s"><v>{index[value]}</v></c>')
        lines.append(f'<row r="{number}">{"".join(parts)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    head = '<?xml version="1.0" encoding="UTF-8"?>' + ('<!DOCTYPE x [<!ENTITY a "b">]>' if doctype else "")
    escape = lambda s: s.replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", f"{head}<Types/>")
        archive.writestr("xl/workbook.xml", f'{head}<workbook {ns}><sheets><sheet name="Umsaetze" sheetId="1"/></sheets></workbook>')
        archive.writestr("xl/sharedStrings.xml",
                         f'{head}<sst {ns}>{"".join(f"<si><t>{escape(s)}</t></si>" for s in strings)}</sst>')
        archive.writestr("xl/worksheets/sheet1.xml", f'{head}<worksheet {ns}><sheetData>{"".join(lines)}</sheetData></worksheet>')
    return buf.getvalue()


def export() -> bytes:
    return workbook([
        row(45901, GIRO_ACC, -42.5, "Erfundener Supermarkt", "Einkauf 1", "Lebenshaltung", "Lebensmittel"),       # 2025-09-01
        row(45915, GIRO_ACC, -38.2, "Erfundener Supermarkt", "Einkauf 2", "Lebenshaltung", "Lebensmittel"),       # 2025-09-15
        row(45931, GIRO_ACC, 2500, "Erfundene Firma GmbH", "Lohn 09", "Einnahmen", "Gehalt"),                    # 2025-10-01
        row(45931, GIRO_ACC, -100, "PayPal", "Aufladung", "Sonstiges", "Sonstiges", transfer="ja"),
        row("2025-10-05", GIRO_ACC, -19.99, "Erfundener Kletterpark", "Eintritt", "Freizeit", "Klettern"),
        row("2025-10-20", GIRO_ACC, -24.99, "Erfundener Kletterpark", "Eintritt", "Freizeit", "Klettern"),
        row("2025-10-21", GIRO_ACC, -12, "Laden in Fremdwaehrung", "Reise", "Reisen", "", currency="USD"),
        row("2025-10-02", PAYPAL_ACC, 100, "", "Bankgutschrift", "Sonstiges", "Sonstiges", transfer="ja"),
        row("2025-10-03", PAYPAL_ACC, -15, "Erfundener Buchladen", "Bestellung", "Freizeit", "Hobby"),
    ])


def _upload(client, data=None, name="finanzguru.xlsx"):
    res = client.post("/api/import/analyze", files={"file": (name, data or export(), "application/octet-stream")})
    assert res.status_code == 200, res.text
    return res.json()


def _take(client, preview, accounts=None, categories=None, learn=True):
    body = {
        "token": preview["token"], "learn": learn,
        "accounts": accounts if accounts is not None else [
            {"ref": a["ref"], "target": a["target"], "name": a["suggest"]["name"], "kind": a["suggest"]["kind"]}
            for a in preview["accounts"]],
        "categories": categories if categories is not None else [
            {"main": c["main"], "sub": c["sub"], "target": c["suggest"]} for c in preview["categories"]],
    }
    return client.post("/api/import/finanzguru/commit", json=body)


def _cat(db, key):
    return db.scalar("SELECT id FROM categories WHERE builtin_key = ?", (key,))


def _tx(db, who):
    return db.query("SELECT t.*, c.builtin_key AS cat FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
                    "WHERE t.counterparty = ? ORDER BY t.booking_date, t.id", (who,))


# --- Lesen --------------------------------------------------------------------------------

def test_workbook_is_read_with_excel_dates_numbers_and_flags():
    res = importers.analyze(export(), "export.xlsx")
    assert res["kind"] == "finanzguru" and res["rows"] == [] and "Finanzguru" in res["error"]
    rows = res["finanzguru"]["rows"]
    assert len(rows) == 8 and res["finanzguru"]["skipped"] == {"Fremdwährung": 1}
    first = rows[0]
    assert (first["booking_date"], first["amount_cents"], first["ref"]) == ("2025-09-01", -4250, GIRO)
    assert (first["main"], first["sub"], first["transfer"]) == ("Lebenshaltung", "Lebensmittel", False)
    assert rows[3]["transfer"] is True and rows[4]["booking_date"] == "2025-10-05"
    assert rows[6]["ref"] == PAYPAL and rows[6]["counterparty"] is None


def test_csv_export_with_german_numbers_is_read():
    lines = [";".join(HEADERS),
             ";".join(["01.09.2025", GIRO, "Erfundenes Girokonto", "-1.042,50", "", "EUR", "Erfundener Vermieter", "", "Miete 09",
                       "", "", "", "Wohnen", "Miete", "", "", "", "nein", "nein", "", "", "", "", "", "", ""])]
    res = importers.analyze("\n".join(lines).encode("utf-8"), "export.csv")
    assert res["kind"] == "finanzguru"
    only = res["finanzguru"]["rows"][0]
    assert (only["booking_date"], only["amount_cents"], only["sub"]) == ("2025-09-01", -104250, "Miete")


def test_header_of_a_real_export_is_recognised():
    # Die Kopfzeile eines echten Exports, wie sie aus Excel kopiert ankommt: 30 Spalten, mit Tabulator getrennt.
    assert len(HEADERS) == 30
    line = ["03.11.2025", GIRO, "Erfundenes Girokonto", "-12,50", "", "EUR", "Erfundener Laden", "", "Kauf", "", "", "",
            "Freizeit", "Hobby", "", "", "", "nein", "nein", "", "-12,50", "", "", "", "", "b-1", "", "", "Urlaub, Rad", "Für  Mia"]
    res = importers.analyze(("\t".join(HEADERS) + "\n" + "\t".join(line)).encode("utf-8"), "export.csv")
    assert res["kind"] == "finanzguru"
    only = res["finanzguru"]["rows"][0]
    assert (only["booking_date"], only["amount_cents"], only["sub"], only["id"]) == ("2025-11-03", -1250, "Hobby", "b-1")
    assert only["note"] == "Für Mia · Tags: Urlaub, Rad"
    assert set(finanzguru.COLUMNS.values()) <= {importers.header_norm(h) for h in HEADERS}


def test_cells_without_reference_and_inline_strings_are_read():
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    header = "".join(f'<c t="inlineStr"><is><t>{h}</t></is></c>' for h in HEADERS[:4])
    body = ('<c t="inlineStr"><is><t>2025-09-01</t></is></c><c t="inlineStr"><is><r><t>DE021203</t></r><r><t>00000000202051</t></r></is></c>'
            '<c t="inlineStr"><is><t>Giro</t></is></c><c><v>-1.2E1</v></c>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("xl/workbook.xml", f"<workbook {ns}/>")
        archive.writestr("xl/worksheets/sheet1.xml",
                         f"<worksheet {ns}><sheetData><row>{header}</row><row>{body}</row></sheetData></worksheet>")
    only = importers.analyze(buf.getvalue(), "x.xlsx")["finanzguru"]["rows"][0]
    assert (only["ref"], only["amount_cents"], only["booking_date"]) == (GIRO, -1200, "2025-09-01")


def test_other_workbooks_are_refused():
    with pytest.raises(ValueError, match="nur als Export aus Finanzguru"):
        importers.analyze(workbook([["01.09.2025", "Miete", -500]], headers=["Datum", "Text", "Betrag"]), "bank.xlsx")


def test_workbook_with_doctype_is_refused():
    with pytest.raises(ValueError, match="unerwartete Angaben"):
        importers.analyze(workbook([], doctype=True), "export.xlsx")


def test_workbook_limits(monkeypatch):
    monkeypatch.setattr(finanzguru, "MAX_ROWS", 3)
    with pytest.raises(ValueError, match="mehr als 3 Zeilen"):
        importers.analyze(export(), "export.xlsx")
    monkeypatch.setattr(finanzguru, "MAX_ROWS", 1000)
    monkeypatch.setattr(finanzguru, "MAX_SHEET_BYTES", 200)
    with pytest.raises(ValueError, match="entpackt zu groß"):
        importers.analyze(export(), "export.xlsx")


def test_damaged_workbook_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/sharedStrings.xml", "<sst><si><t>offen")
        archive.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
    with pytest.raises(ValueError, match="beschädigt"):
        importers.analyze(buf.getvalue(), "kaputt.xlsx")


def test_bank_csv_is_not_mistaken_for_finanzguru():
    from conftest import fixture_bytes

    assert importers.analyze(fixture_bytes("ing.csv"), "ing.csv")["kind"] == "csv"


# --- Vorschau -----------------------------------------------------------------------------

def test_preview_finds_accounts_and_suggests_categories(client, db):
    giro = client.post("/api/accounts", json={"name": "Mein Giro", "kind": "giro", "iban": GIRO}).json()["id"]
    pre = _upload(client)
    assert pre["kind"] == "finanzguru" and pre["count"] == 8 and pre["transfers"] == 2
    assert "rows" not in pre and "finanzguru" not in pre
    by_ref = {a["ref"]: a for a in pre["accounts"]}
    assert by_ref[GIRO]["target"] == giro and by_ref[GIRO]["count"] == 6 and by_ref[GIRO]["will_add"] == 6
    assert by_ref[PAYPAL]["target"] == "new" and by_ref[PAYPAL]["suggest"] == {"name": "PayPal", "kind": "paypal"}
    suggest = {(c["main"], c["sub"]): c["suggest"] for c in pre["categories"]}
    assert suggest[("Lebenshaltung", "Lebensmittel")] == _cat(db, "supermarkt")
    assert suggest[("Einnahmen", "Gehalt")] == _cat(db, "gehalt")
    assert suggest[("Freizeit", "Hobby")] == _cat(db, "hobby")
    # Unbekannte Unterkategorie: die Hauptkategorie gibt den Ausschlag.
    assert suggest[("Freizeit", "Klettern")] == _cat(db, "freizeit")
    assert ("Sonstiges", "Sonstiges") not in suggest  # nur Umbuchungen, keine eigene Zeile
    assert pre["categories"][0]["count"] == 2


@pytest.mark.parametrize("main, sub, key", [
    ("Mobilität", "Kfz-Versicherung", "versicherungen"), ("Mobilität", "Kfz-Steuer", "auto"),
    ("Mobilität", "Tanken", "laden"), ("Mobilität", "ÖPNV", "oepnv"), ("Wohnen", "Strom & Gas", "energie"),
    ("Freizeit", "Gastronomie", "restaurant"), ("Finanzen", "Bargeldabhebung", "bargeld"),
    ("Finanzen", "Ratenkredit", "kredite"), ("Sparen", "Altersvorsorge", "sparen"), ("Wohnen", "", "wohnen"),
    ("Sonstiges", "Sonstiges", None), ("Lebenshaltung", "Unkategorisiert", None), ("Geschäft", "Büro", None),
])
def test_category_suggestions(db, main, sub, key):
    cats = db.query("SELECT id, name, builtin_key FROM categories")
    assert finanzguru.suggest_category(cats, main, sub) == (_cat(db, key) if key else None)


def test_generic_commit_refuses_the_export(client, db):
    pre = _upload(client)
    res = client.post("/api/import/commit", json={"token": pre["token"], "new_account": {"name": "Alles in einem"}})
    assert res.status_code == 400
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 0 and db.scalar("SELECT COUNT(*) FROM accounts") == 0


# --- Übernehmen ---------------------------------------------------------------------------

def test_new_accounts_get_history_and_categories(client, db):
    done = _take(client, _upload(client))
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["added"] == 8 and result["skipped"] == 0
    accounts = {a["name"]: a for a in db.query("SELECT * FROM accounts")}
    assert accounts["Erfundenes Girokonto"]["iban"] == GIRO and accounts["Erfundenes Girokonto"]["kind"] == "giro"
    assert accounts["PayPal"]["kind"] == "paypal" and accounts["PayPal"]["iban"] is None
    market = _tx(db, "Erfundener Supermarkt")
    assert [t["cat"] for t in market] == ["supermarkt", "supermarkt"]
    assert all(t["category_locked"] == 1 and t["rule_ref"] == "finanzguru" and t["source"] == "finanzguru" for t in market)
    transfer = _tx(db, "PayPal")[0]
    assert (transfer["cat"], transfer["is_transfer"], transfer["category_locked"]) == ("umbuchung", 1, 1)
    assert db.scalar("SELECT COUNT(*) FROM transactions WHERE is_transfer = 1") == 2


def test_importing_twice_adds_nothing(client, db):
    _take(client, _upload(client))
    again = _upload(client)
    assert {a["target"] for a in again["accounts"]} == set(r["id"] for r in db.query("SELECT id FROM accounts"))
    result = _take(client, again).json()
    assert result["added"] == 0 and result["skipped"] == 8
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 8 and db.scalar("SELECT COUNT(*) FROM accounts") == 2


def test_account_with_bank_history_is_only_filled_backwards(client, db):
    giro = client.post("/api/accounts", json={"name": "Mein Giro", "kind": "giro", "iban": GIRO}).json()["id"]
    # Die Bank liefert ab 5. Oktober – mit etwas anderem Text und einen Tag später gebucht.
    ledger.import_rows(db, giro, [
        {"booking_date": "2025-10-06", "amount_cents": -1999, "counterparty": "ERFUNDENER KLETTERPARK 0815", "purpose": "Kartenzahlung"},
        {"booking_date": "2025-10-20", "amount_cents": -2499, "counterparty": "ERFUNDENER KLETTERPARK 0815", "purpose": "Kartenzahlung"},
    ], "openbanking")
    pre = _upload(client)
    giro_pre = next(a for a in pre["accounts"] if a["ref"] == GIRO)
    assert giro_pre["cutoff"] == "2025-10-06" and giro_pre["will_add"] == 5
    result = _take(client, pre).json()
    taken = next(a for a in result["accounts"] if a["account_id"] == giro)
    assert (taken["added"], taken["held_back"], taken["cutoff"]) == (5, 1, "2025-10-06")
    park = db.query("SELECT booking_date, source FROM transactions WHERE account_id = ? AND amount_cents IN (-1999, -2499) "
                    "ORDER BY booking_date", (giro,))
    # Die Buchung vom 5. Oktober liegt vor dem ersten Bankumsatz und kommt aus dem Export; ab dann gilt die Bank.
    assert [(p["booking_date"], p["source"]) for p in park] == [
        ("2025-10-05", "finanzguru"), ("2025-10-06", "openbanking"), ("2025-10-20", "openbanking")]


def test_skipped_account_and_unmapped_category_are_left_alone(client, db):
    pre = _upload(client)
    accounts = [{"ref": GIRO, "target": "new", "name": "Giro", "kind": "giro"}, {"ref": PAYPAL, "target": "skip"}]
    categories = [{"main": "Lebenshaltung", "sub": "Lebensmittel", "target": None}]
    result = _take(client, pre, accounts, categories).json()
    assert result["added"] == 6 and [a["name"] for a in result["accounts"]] == ["Giro"]
    market = _tx(db, "Erfundener Supermarkt")
    # Ohne Zuordnung entscheidet Kassensturz selbst und darf später neu zuordnen.
    assert all(t["category_locked"] == 0 and t["rule_ref"] != "finanzguru" for t in market)
    assert db.scalar("SELECT COUNT(*) FROM transactions WHERE counterparty = 'Erfundener Buchladen'") == 0


def test_new_category_is_created_below_its_main_category(client, db):
    pre = _upload(client)
    categories = [{"main": "Freizeit", "sub": "Klettern", "target": "new"},
                  {"main": "Lebenshaltung", "sub": "Lebensmittel", "target": "new"}]
    result = _take(client, pre, categories=categories).json()
    assert result["categories_created"] == 3  # Klettern, Lebenshaltung, Lebensmittel
    climbing = db.one("SELECT * FROM categories WHERE name = 'Klettern'")
    assert climbing["parent_id"] == _cat(db, "freizeit") and climbing["kind"] == "expense"
    food = db.one("SELECT c.*, p.name AS parent FROM categories c JOIN categories p ON p.id = c.parent_id WHERE c.name = 'Lebensmittel'")
    assert food["parent"] == "Lebenshaltung"
    assert {t["category_id"] for t in _tx(db, "Erfundener Kletterpark")} == {climbing["id"]}


def test_nothing_is_written_when_a_choice_is_invalid(client, db):
    pre = _upload(client)
    accounts = [{"ref": GIRO, "target": "new", "name": "Giro", "kind": "giro"}, {"ref": PAYPAL, "target": 4711}]
    res = _take(client, pre, accounts, [{"main": "Freizeit", "sub": "Klettern", "target": "new"}])
    assert res.status_code == 400
    assert db.scalar("SELECT COUNT(*) FROM accounts") == 0 and db.scalar("SELECT COUNT(*) FROM transactions") == 0
    assert db.scalar("SELECT COUNT(*) FROM categories WHERE name = 'Klettern'") == 0
    # Die Datei liegt noch bereit; ein zweiter Versuch mit gültiger Auswahl geht durch.
    assert _take(client, pre).status_code == 200


def test_commit_needs_an_account_and_a_known_token(client, db):
    pre = _upload(client)
    skip = [{"ref": a["ref"], "target": "skip"} for a in pre["accounts"]]
    assert _take(client, pre, skip).status_code == 400
    assert client.post("/api/import/finanzguru/commit", json={"token": "gibt-es-nicht"}).status_code == 400
    bank = client.post("/api/import/analyze", files={"file": ("ing.csv", (__import__("conftest").FIXTURES / "ing.csv").read_bytes(), "text/csv")}).json()
    assert client.post("/api/import/finanzguru/preview", json={"token": bank["token"]}).status_code == 400


def test_preview_follows_the_chosen_target(client, db):
    other = client.post("/api/accounts", json={"name": "Anderes Konto", "kind": "giro"}).json()["id"]
    ledger.import_rows(db, other, [{"booking_date": "2025-09-10", "amount_cents": -100, "counterparty": "X", "purpose": "Y"}], "datei")
    pre = _upload(client)
    again = client.post("/api/import/finanzguru/preview", json={
        "token": pre["token"], "accounts": [{"ref": GIRO, "target": other}, {"ref": PAYPAL, "target": "skip"}]}).json()
    by_ref = {a["ref"]: a for a in again["accounts"]}
    assert (by_ref[GIRO]["target"], by_ref[GIRO]["cutoff"], by_ref[GIRO]["will_add"]) == (other, "2025-09-10", 1)
    assert (by_ref[PAYPAL]["target"], by_ref[PAYPAL]["will_add"]) == ("skip", 0)


# --- Notiz, Tags, aufgeteilte Buchungen ---------------------------------------------------

def test_note_and_tags_become_the_note(client, db):
    data = workbook([row("2025-09-01", GIRO_ACC, -20, "Erfundener Laden", "Kauf 1", "Freizeit", "Hobby", note="Geschenk", tags="Geburtstag"),
                     row("2025-09-02", GIRO_ACC, -30, "Erfundener Laden", "Kauf 2", "Freizeit", "Hobby")])
    _take(client, _upload(client, data))
    assert [t["note"] for t in _tx(db, "Erfundener Laden")] == ["Geschenk · Tags: Geburtstag", None]


def _split_export(members, ids=True):
    """Ein Original über 100 € mit seinen Teilen, wie Finanzguru sie untereinander schreibt."""
    below = [row("2025-09-03", GIRO_ACC, amount, "Erfundenes Kaufhaus", "Einkauf", main, sub, id=f"t-{i}" if ids else "",
                 original="b-1" if ids else "", split=kind, note=f"Teil {i}" if kind == "Teilbuchung" else "")
             for i, (kind, amount, main, sub) in enumerate(members, start=1)]
    return workbook([row("2025-09-02", GIRO_ACC, -7, "Erfundener Bäcker", "Brot", "Lebenshaltung", "Lebensmittel", id="b-0"),
                     row("2025-09-03", GIRO_ACC, -100, "Erfundenes Kaufhaus", "Einkauf", "Shopping", "", id="b-1" if ids else "",
                         split="Original", note="Großeinkauf"),
                     *below, row("2025-09-04", GIRO_ACC, -5, "Erfundener Kiosk", "Zeitung", "Freizeit", "Hobby", id="b-2")])


def _store(db):
    store = _tx(db, "Erfundenes Kaufhaus")
    assert len(store) == 1 and store[0]["amount_cents"] == -10000  # nur die Buchung der Bank, nichts doppelt
    parts = db.query("SELECT s.amount_cents, s.note, c.builtin_key AS cat FROM splits s JOIN categories c ON c.id = s.category_id "
                     "WHERE s.tx_id = ? ORDER BY s.amount_cents", (store[0]["id"],))
    counted = sorted(e["amount_cents"] for e in ledger.entries(db) if e["id"] == store[0]["id"])
    return store[0], [(p["amount_cents"], p["cat"], p["note"]) for p in parts], counted


@pytest.mark.parametrize("ids", [True, False])
def test_split_with_rest_becomes_one_booking_with_parts(client, db, ids):
    members = [("Teilbuchung", -60, "Lebenshaltung", "Lebensmittel"), ("Restbetrag", -40, "Freizeit", "Hobby")]
    pre = _upload(client, _split_export(members, ids))
    assert pre["count"] == 3 and pre["splits"] == {"taken": 1, "plain": 0, "unclear": 0}
    # Gezählt werden die Kategorien der Teile und des Rests, nicht die des Originals.
    assert {(c["main"], c["sub"]): c["count"] for c in pre["categories"]} == {
        ("Lebenshaltung", "Lebensmittel"): 2, ("Freizeit", "Hobby"): 2}
    assert _take(client, pre).json()["added"] == 3
    tx, parts, counted = _store(db)
    # Der Teil ist die Aufteilung; der Rest zählt zur Kategorie der Buchung, die vom Restbetrag kommt.
    assert parts == [(-6000, "supermarkt", "Teil 1")] and counted == [-6000, -4000]
    assert (tx["cat"], tx["category_locked"], tx["note"]) == ("hobby", 1, "Großeinkauf")
    assert db.scalar("SELECT COUNT(*) FROM learned_categories WHERE key LIKE '%kaufhaus%'") == 0


def test_split_without_rest_is_covered_by_its_parts(client, db):
    members = [("Teilbuchung", -70, "Lebenshaltung", "Lebensmittel"), ("Teilbuchung", -20, "Freizeit", "Hobby"),
               ("Teilbuchung", -10, "Lebenshaltung", "Drogerie")]
    pre = _upload(client, _split_export(members))
    assert pre["splits"]["taken"] == 1
    _take(client, pre)
    tx, parts, counted = _store(db)
    assert [p[:2] for p in parts] == [(-7000, "supermarkt"), (-2000, "hobby"), (-1000, "drogerie")]
    assert counted == [-7000, -2000, -1000] and tx["cat"] == "supermarkt"


def test_part_without_category_is_left_to_kassensturz(client, db):
    members = [("Teilbuchung", -60, "Lebenshaltung", "Lebensmittel"), ("Teilbuchung", -40, "Geschäft", "Büro")]
    _take(client, _upload(client, _split_export(members)))
    tx, parts, counted = _store(db)
    # Der zugeordnete Teil bleibt aufgeteilt; den Rest ordnet Kassensturz mit der Buchung selbst zu.
    assert [p[0] for p in parts] == [-6000] and counted == [-6000, -4000]
    assert tx["category_locked"] == 0 and tx["rule_ref"] != "finanzguru"


def test_parts_that_do_not_add_up_are_dropped_and_the_booking_stays(client, db):
    members = [("Teilbuchung", -60, "Lebenshaltung", "Lebensmittel"), ("Restbetrag", -30, "Freizeit", "Hobby")]
    pre = _upload(client, _split_export(members))
    assert pre["count"] == 3 and pre["splits"] == {"taken": 0, "plain": 1, "unclear": 0}
    _take(client, pre)
    tx, parts, counted = _store(db)
    assert parts == [] and counted == [-10000] and tx["cat"] == "shopping"


def test_part_without_its_booking_is_kept_and_named(client, db):
    # Eine Erstattung, die auf den Kauf verweist, ist kein Teil des Kaufs. Eine Teilbuchung ohne Original bleibt stehen.
    data = workbook([row("2025-09-03", GIRO_ACC, -100, "Erfundenes Kaufhaus", "Einkauf", "Shopping", "", id="b-1"),
                     row("2025-09-10", GIRO_ACC, 100, "Erfundenes Kaufhaus", "Erstattung", "Shopping", "", id="b-2", original="b-1"),
                     row("2025-09-11", GIRO_ACC, -40, "Erfundenes Kaufhaus", "Teil ohne Buchung", "Shopping", "", id="b-3",
                         original="fehlt", split="Teilbuchung")])
    pre = _upload(client, data)
    assert pre["count"] == 3 and pre["splits"] == {"taken": 0, "plain": 0, "unclear": 1}
    assert _take(client, pre).json()["added"] == 3


def test_parts_of_another_account_are_not_attached(client, db):
    data = workbook([row("2025-09-03", GIRO_ACC, -100, "Erfundenes Kaufhaus", "Einkauf", "Shopping", "", split="Original"),
                     row("2025-09-03", PAYPAL_ACC, -100, "Erfundener Versand", "Paket", "Shopping", "", split="Teilbuchung")])
    pre = _upload(client, data)
    assert pre["count"] == 2 and pre["splits"] == {"taken": 0, "plain": 0, "unclear": 1}


# --- Lernen -------------------------------------------------------------------------------

def test_reliable_categories_are_learned_and_applied_to_bank_transactions(client, db):
    giro = client.post("/api/accounts", json={"name": "Mein Giro", "kind": "giro", "iban": GIRO}).json()["id"]
    ledger.import_rows(db, giro, [
        {"booking_date": "2025-11-03", "amount_cents": -2199, "counterparty": "Erfundener Kletterpark GmbH", "purpose": "Eintritt"},
    ], "openbanking")
    assert _tx(db, "Erfundener Kletterpark GmbH")[0]["cat"] == "sonstiges"
    result = _take(client, _upload(client)).json()
    assert result["learned"] == 2  # Supermarkt und Kletterpark; Einmaliges wird nicht gelernt
    learned = {r["key"]: r["category_id"] for r in db.query("SELECT key, category_id FROM learned_categories")}
    assert learned == {"erfundener supermarkt": _cat(db, "supermarkt"), "erfundener kletterpark": _cat(db, "freizeit")}
    bank = _tx(db, "Erfundener Kletterpark GmbH")[0]
    assert (bank["cat"], bank["rule_ref"], bank["category_locked"]) == ("freizeit", "learned", 0)


def test_own_corrections_win_over_finanzguru(client, db):
    hobby = _cat(db, "hobby")
    db.insert("learned_categories", {"key": "erfundener kletterpark", "sign": "out", "label": "Erfundener Kletterpark",
                                     "category_id": hobby, "updated": "2025-11-01T00:00:00"})
    _take(client, _upload(client))
    assert db.scalar("SELECT category_id FROM learned_categories WHERE key = 'erfundener kletterpark'") == hobby


def test_mixed_categories_are_not_learned(db):
    rows = [{"ref": "A", "account_name": "A", "amount_cents": -100, "counterparty": "Erfundener Gemischtwarenladen",
             "purpose": None, "counterparty_iban": None, "creditor_id": None, "main": "M", "sub": s, "transfer": False}
            for s in ("Eins", "Eins", "Zwei")]
    target = {("M", "Eins"): _cat(db, "supermarkt"), ("M", "Zwei"): _cat(db, "drogerie")}
    assert finanzguru._learn(db, rows, target) == 0
    assert finanzguru._learn(db, rows + [dict(rows[0]) for _ in range(6)], target) == 1


def test_learning_can_be_switched_off(client, db):
    assert _take(client, _upload(client), learn=False).json()["learned"] == 0
    assert db.scalar("SELECT COUNT(*) FROM learned_categories") == 0


# --- Kontostand und Selbsttest ------------------------------------------------------------

def test_history_does_not_disturb_the_balance_check(client, db):
    giro = client.post("/api/accounts", json={"name": "Mein Giro", "kind": "giro", "iban": GIRO}).json()["id"]
    ledger.import_rows(db, giro, [{"booking_date": "2025-11-03", "amount_cents": -2199, "counterparty": "Laden", "purpose": "A"}],
                       "openbanking")
    ledger.set_balance_anchor(db, giro, 100000, "2025-11-03")
    ledger.check_balance(db, giro, 100000, date(2025, 11, 3))
    before = ledger.current_balance(db, db.one("SELECT * FROM accounts WHERE id = ?", (giro,)))
    assert _take(client, _upload(client)).json()["added"] == 8
    # Der heutige Stand hängt am Bankstand und ändert sich durch alte Buchungen nicht.
    assert ledger.current_balance(db, db.one("SELECT * FROM accounts WHERE id = ?", (giro,))) == before
    # Nächster Abruf: eine neue Buchung über 50 €, der Bankstand sinkt genau um diese 50 €.
    ledger.import_rows(db, giro, [{"booking_date": "2025-11-04", "amount_cents": -5000, "counterparty": "Laden", "purpose": "B"}],
                       "openbanking")
    assert ledger.check_balance(db, giro, 95000, date(2025, 11, 4)) == 0
    assert ledger.balance_drift(db, giro, date(2025, 11, 20)) is None
    assert not [a for a in services.alerts(db, services.build_summary(db)) if a["key"].startswith("drift:")]


def test_balance_check_without_backfill_is_unchanged(db):
    acc = db.insert("accounts", {"name": "Testkonto", "kind": "giro"})
    ledger.check_balance(db, acc, 100000, date(2025, 11, 1))
    ledger.import_rows(db, acc, [{"booking_date": "2025-11-02", "amount_cents": -1000, "counterparty": "Laden", "purpose": "A"}],
                       "openbanking")
    assert ledger.check_balance(db, acc, 94001, date(2025, 11, 2)) == -4999
    # Der Vermerk gilt nur bis zum nächsten Abruf und stört einen späteren nicht.
    ledger.note_backfill(db, acc, -30000)
    ledger.note_backfill(db, acc, -20000)
    assert db.scalar("SELECT backfill_cents FROM balance_checks ORDER BY id DESC LIMIT 1") == -50000
    ledger.import_rows(db, acc, [{"booking_date": "2025-10-01", "amount_cents": -50000, "counterparty": "Alt", "purpose": "B"}],
                       "finanzguru")
    assert ledger.check_balance(db, acc, 94001, date(2025, 11, 3)) == 0
    assert ledger.check_balance(db, acc, 94001, date(2025, 11, 4)) == 0


def _with_balances(order):
    rows = [("2025-09-01", -100, 900), ("2025-09-02", -50, 850), ("2025-09-02", 200, 1050), ("2025-09-05", -25.5, 1024.5),
            ("2025-09-09", -24.5, 1000)]
    return workbook([row(d, GIRO_ACC, a, "Erfundener Laden", f"Kauf {i}", balance=b)
                     for i, (d, a, b) in enumerate(rows[::order])])


@pytest.mark.parametrize("order", [1, -1])
def test_closing_balance_is_taken_when_the_column_adds_up(client, db, order):
    result = _take(client, _upload(client, _with_balances(order))).json()
    assert result["accounts"][0]["balance_known"] is True
    acc = db.one("SELECT * FROM accounts")
    assert (acc["balance_cents"], acc["balance_date"]) == (100000, "2025-09-09")
    assert ledger.current_balance(db, acc) == 100000


def test_closing_balance_is_left_open_when_the_column_does_not_add_up(client, db):
    data = workbook([row(f"2025-09-0{i}", GIRO_ACC, -100, "Erfundener Laden", f"Kauf {i}", balance=5000) for i in range(1, 7)])
    result = _take(client, _upload(client, data)).json()
    assert result["accounts"][0]["balance_known"] is False
    assert db.one("SELECT balance_date FROM accounts")["balance_date"] is None


def test_existing_account_keeps_its_balance(client, db):
    giro = client.post("/api/accounts", json={"name": "Mein Giro", "kind": "giro", "iban": GIRO}).json()["id"]
    ledger.set_balance_anchor(db, giro, 4242, "2025-11-01")
    _take(client, _upload(client, _with_balances(1)))
    acc = db.one("SELECT balance_cents, balance_date FROM accounts WHERE id = ?", (giro,))
    assert (acc["balance_cents"], acc["balance_date"]) == (4242, "2025-11-01")


# --- Drumherum ----------------------------------------------------------------------------

def test_history_is_not_announced_as_new(client, db):
    assert services.new_auto_transactions(db) == []  # erster Lauf merkt sich nur den Stand
    _take(client, _upload(client))
    assert services.new_auto_transactions(db) == []


def test_export_in_the_inbox_waits_for_the_dialog(client, db, tmp_path, monkeypatch):
    from kassensturz import inbox

    folder = tmp_path / "eingang"
    monkeypatch.setenv("KASSENSTURZ_INBOX", str(folder))
    client.post("/api/accounts", json={"name": "Finanzguru Girokonto", "kind": "giro"})
    folder.mkdir()
    target = folder / "finanzguru.xlsx"
    target.write_bytes(export())
    old = time.time() - 60
    os.utime(target, (old, old))
    res = inbox.scan(db)
    assert res["imported"] == [] and res["pending"] == 1
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 0
    pre = client.post("/api/inbox/analyze", json={"filename": "finanzguru.xlsx"}).json()
    assert pre["kind"] == "finanzguru" and len(pre["accounts"]) == 2
    assert _take(client, pre).json()["added"] == 8
    assert not target.exists() and len(list((folder / "importiert").iterdir())) == 1
    assert db.scalar("SELECT COUNT(*) FROM inbox") == 0
