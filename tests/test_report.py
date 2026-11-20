"""PDF-Berichte: gültige Datei, Inhalt, Umlaute und Euro, Grenzen. Nur erfundene Daten."""
import re
import zlib
from datetime import date

import pytest

from kassensturz import ledger, report


def _text(pdf: bytes) -> str:
    """Alle Textstücke aller Seiten, in Windows-1252 gelesen."""
    out = []
    for stream in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S):
        ops = zlib.decompress(stream)
        out += [re.sub(rb"\\(.)", rb"\1", m).decode("cp1252") for m in re.findall(rb"\((.*?)(?<!\\)\) Tj", ops)]
    return "\n".join(out)


def _valid(pdf: bytes):
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    start = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
    assert pdf[start:start + 4] == b"xref"
    count = int(re.search(rb"xref\n0 (\d+)", pdf).group(1))
    offsets = [int(o) for o in re.findall(rb"(\d{10}) 00000 n ", pdf)]
    assert len(offsets) == count - 1
    for n, off in enumerate(offsets, start=1):
        assert pdf[off:].startswith(b"%d 0 obj" % n)


def _setup(db):
    acc = db.insert("accounts", {"name": "Testkonto (Gemeinschaft)", "kind": "giro"})
    rows = []
    for m in range(1, 13):
        rows.append({"booking_date": f"2025-{m:02d}-01", "amount_cents": 200000, "counterparty": "Erfundene Firma",
                     "purpose": f"Lohn {m}"})
        rows += [{"booking_date": f"2025-{m:02d}-{d:02d}", "amount_cents": -2500 - d, "counterparty": f"Bäckerei Größe {d}",
                  "purpose": f"Brötchen {m}-{d}"} for d in range(2, 28)]
    ledger.import_rows(db, acc, rows, "datei")
    return acc


def test_month_report_is_a_valid_pdf_with_the_figures(db):
    _setup(db)
    pdf = report.month_pdf(db, "2025-06", today=date(2026, 1, 10))
    _valid(pdf)
    text = _text(pdf)
    assert "Monatsbericht Juni 2025" in text and "01.06.2025 bis 30.06.2025" in text
    assert "2.000,00 €" in text and "Kontostände am 30.06.2025" in text
    assert "Testkonto \\(Gemeinschaft\\)" not in text and "Testkonto (Gemeinschaft)" in text
    assert "Bäckerei Größe 27" in text  # die größte Einzelausgabe des Monats
    assert "Seite 1 von" in text


def test_year_report_spans_pages_and_names_the_months(db):
    _setup(db)
    pdf = report.year_pdf(db, 2025, today=date(2026, 1, 10))
    _valid(pdf)
    text = _text(pdf)
    assert "Jahresrückblick 2025" in text and "Dezember" in text and "24.000,00 €" in text
    assert pdf.count(b"/Type /Page ") >= 1


def test_reports_without_data_and_limits(db, client):
    _valid(report.month_pdf(db, "2026-01", today=date(2026, 1, 10)))
    with pytest.raises(ValueError):
        report.month_pdf(db, "2026-02", today=date(2026, 1, 10))
    r = client.get("/api/report/month.pdf?month=2025-06")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert 'filename="kassensturz-2025-06.pdf"' in r.headers["content-disposition"]
    assert client.get("/api/report/month.pdf?month=2025-13").status_code == 400
    assert client.get("/api/report/month.pdf?month=2999-01").status_code == 400
    assert client.get("/api/report/year.pdf?year=1999").status_code == 400
    assert client.get("/api/report/year.pdf").status_code == 200


def test_text_width_and_wrapping():
    assert report.text_width("WW", 10) > report.text_width("ii", 10)
    assert report.text_width("A", 10, bold=True) >= report.text_width("A", 10)
    lines = report.wrap_text("eins zwei drei vier fünf sechs sieben acht neun zehn", 10, 80)
    assert len(lines) > 1 and all(report.text_width(line, 10) <= 80 for line in lines)
