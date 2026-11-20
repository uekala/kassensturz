"""Advanzia-Abrechnung als PDF: erfundener Aufbau, erfundene Umsätze."""
from datetime import date

import pytest

from kassensturz import advanzia_pdf, importers
from kassensturz.report import Pdf


def statement(lines, marker="Advanzia Bank S.A. · Mastercard Gold · gebührenfrei.de", balances=True) -> bytes:
    pdf = Pdf("Testabrechnung")
    y = 780
    for text in [marker, "Rechnungsdatum: 15.11.2026"] + (["Saldo der letzten Rechnung 100,00"] if balances else []) \
            + lines + (["Neuer Saldo 40,31"] if balances else []):
        pdf.text(56, y, text, 9)
        y -= 14
    return pdf.bytes()


LINES = [
    "16.10.2026 17.10.2026 REWE Erfundene Filiale            12,34",
    "20.10.2026 21.10.2026 Erfundener Online-Shop USD 30,00 Kurs 1,0800   27,97",
    "05.11.2026 05.11.2026 Zahlung erhalten - Danke         100,00 -",
    "Summe der Umsätze 40,31",
]


def test_statement_with_balances_is_read_and_checked():
    res = importers.analyze(statement(LINES), "Rechnung.pdf")
    assert res["kind"] == "advanzia_pdf" and res["suggest"]["kind"] == "kreditkarte"
    assert res["pdf_check"]["matches"] is True
    got = [(r["booking_date"], r["amount_cents"], r["counterparty"][:12]) for r in res["rows"]]
    assert got == [("2026-10-16", -1234, "REWE Erfunde"), ("2026-10-20", -2797, "Erfundener O"),
                   ("2026-11-05", 10000, "Zahlung erha")]
    assert res["rows"][0]["value_date"] == "2026-10-17"


def test_without_balances_purchases_are_expenses_and_year_is_guessed():
    lines = ["28.12. 29.12. Erfundenes Kino 9,50", "03.01. 04.01. Erfundener Bäcker 2,10"]
    parsed = advanzia_pdf.parse("Advanzia\nRechnungsdatum: 15.01.2027\n" + "\n".join(lines))
    rows, check = advanzia_pdf.rows_from(parsed)
    assert check["balances_found"] is False and check["matches"] is None
    assert [(r["booking_date"], r["amount_cents"]) for r in rows] == [("2026-12-28", -950), ("2027-01-03", -210)]


def test_mismatch_is_reported_and_other_pdfs_are_refused():
    res = importers.analyze(statement(LINES[:2] + ["05.11.2026 05.11.2026 Zahlung erhalten 50,00 -"]), "r.pdf")
    assert res["pdf_check"]["matches"] is False and res["pdf_check"]["difference_cents"]
    with pytest.raises(ValueError, match="nur als Monatsabrechnung"):
        importers.analyze(statement(LINES, marker="Erfundene Sparkasse Kontoauszug"), "k.pdf")
    empty = importers.analyze(statement(["Keine Umsätze"], balances=False), "leer.pdf")
    assert empty["count"] == 0 and "keine Umsätze" in empty["error"]


def test_upload_through_the_import_route(client):
    r = client.post("/api/import/analyze", files={"file": ("rechnung.pdf", statement(LINES), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "advanzia_pdf" and body["count"] == 3 and body["pdf_check"]["matches"] is True
