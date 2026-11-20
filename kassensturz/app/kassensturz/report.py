"""Berichte als PDF: Monatsbericht und Jahresrückblick zum Ablegen oder Ausdrucken.

Ohne zusätzliche Bibliothek: Kassensturz schreibt die PDF-Datei selbst, mit den Standardschriften Helvetica
und Helvetica-Bold, die jeder PDF-Betrachter mitbringt. Die Breiten der Zeichen (für rechtsbündige Beträge und
Zeilenumbruch) stammen aus den Adobe-Metriken dieser Schriften, in der Kodierung Windows-1252.
"""
from __future__ import annotations

import zlib
from datetime import date

from . import analytics, ledger
from .db import Database
from . import sharing
from .util import add_months, euro, month_end

# Breiten der Zeichen 32 bis 255 in Windows-1252, in Tausendsteln der Schriftgröße
_HELVETICA = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
    556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
    500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469,
    556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
    278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 761, 556, 0, 222, 556, 333, 1000, 556, 556, 333,
    1000, 667, 333, 1000, 0, 611, 0, 0, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 0, 500,
    667, 278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333,
    333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667,
    667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667,
    667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500,
)

_HELVETICA_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
    556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278,
    556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584,
    556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556,
    333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 761, 556, 0, 278, 556, 500, 1000, 556, 556, 333,
    1000, 667, 333, 1000, 0, 611, 0, 0, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 0, 500,
    667, 278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333,
    333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667,
    667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667,
    667, 611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278, 611, 611, 611,
    611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556,
)

_PAGE_W, _PAGE_H = 595.28, 841.89  # A4 in Punkt
_LEFT, _RIGHT, _TOP, _BOTTOM = 56.0, 539.0, 790.0, 64.0
_REPLACE = {"\u2212": "-", "\u2009": " ", "\u202f": " ", "\u2713": "", "\u00a0": " "}


def _encode(text: str) -> bytes:
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return text.encode("cp1252", errors="replace")


def text_width(text: str, size: float, bold: bool = False) -> float:
    table = _HELVETICA_BOLD if bold else _HELVETICA
    return sum(table[c - 32] if 32 <= c <= 255 and table[c - 32] else 556 for c in _encode(text)) * size / 1000


def wrap_text(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and text_width(candidate, size, bold) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _fit(text: str, size: float, width: float, bold: bool = False) -> str:
    if text_width(text, size, bold) <= width:
        return text
    while text and text_width(text + "…", size, bold) > width:
        text = text[:-1]
    return text.rstrip() + "…"


class Pdf:
    """Ein sehr kleiner PDF-Schreiber: Seiten mit Text, Linien und Flächen."""

    def __init__(self, title: str):
        self.title = title
        self.pages: list[list[str]] = []
        self.y = 0.0
        self.new_page()

    # Zeichnen
    def new_page(self):
        self.pages.append([])
        self.y = _TOP

    def _ops(self, op: str):
        self.pages[-1].append(op)

    def text(self, x: float, y: float, text: str, size: float = 10, bold: bool = False, align: str = "left",
             gray: float = 0.0):
        if align == "right":
            x -= text_width(text, size, bold)
        raw = _encode(text).replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        self._ops(f"{gray:.2f} g BT /{'F2' if bold else 'F1'} {size:g} Tf {x:.2f} {y:.2f} Td (" + raw.decode("latin-1")
                  + ") Tj ET")

    def rect(self, x: float, y: float, w: float, h: float, gray: float = 0.85):
        self._ops(f"{gray:.2f} g {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1: float, y1: float, x2: float, y2: float, gray: float = 0.8, width: float = 0.5):
        self._ops(f"{gray:.2f} G {width:g} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    # Fluss von oben nach unten
    def need(self, height: float):
        if self.y - height < _BOTTOM:
            self.new_page()

    def heading(self, text: str, size: float = 13):
        self.need(size + 80)
        self.y -= 26
        self.text(_LEFT, self.y, text, size, bold=True)
        self.y -= 10

    def paragraph(self, text: str, size: float = 10, gray: float = 0.0):
        for part in wrap_text(text, size, _RIGHT - _LEFT):
            self.need(size + 4)
            self.y -= size + 4
            self.text(_LEFT, self.y, part, size, gray=gray)

    def table(self, columns: list[tuple[str, float, str]], rows: list[list[str]], bold_last: bool = False):
        """columns: (Überschrift, rechte bzw. linke Kante als Anteil der Breite, Ausrichtung)."""
        width = _RIGHT - _LEFT

        def edge(i):
            return _LEFT + columns[i][1] * width

        def cells(values, bold, gray=0.0):
            for i, value in enumerate(values):
                label, _pos, align = columns[i]
                if align == "right":
                    self.text(edge(i), self.y, value, 9.5, bold, "right", gray)
                else:
                    stop = next((edge(j) - text_width(columns[j][0], 9, True) - 8 for j in range(i + 1, len(columns))
                                 if columns[j][2] == "right"), _RIGHT)
                    self.text(edge(i), self.y, _fit(value, 9.5, stop - edge(i), bold), 9.5, bold, gray=gray)

        self.need(40)
        self.y -= 14
        cells([c[0] for c in columns], True, 0.35)
        self.y -= 5
        self.line(_LEFT, self.y, _RIGHT, self.y, 0.6)
        for n, row in enumerate(rows):
            if self.y - 16 < _BOTTOM:
                self.new_page()
                self.y -= 14
                cells([c[0] for c in columns], True, 0.35)
                self.y -= 5
                self.line(_LEFT, self.y, _RIGHT, self.y, 0.6)
            self.y -= 14
            last = bold_last and n == len(rows) - 1
            if last:
                self.line(_LEFT, self.y + 10.5, _RIGHT, self.y + 10.5, 0.6)
            cells(row, last)
            self.y -= 2

    def facts(self, items: list[tuple[str, str]]):
        """Große Kennzahlen nebeneinander."""
        self.need(60)
        self.y -= 16
        step = (_RIGHT - _LEFT) / max(1, len(items))
        for i, (label, value) in enumerate(items):
            self.text(_LEFT + i * step, self.y, label, 9, gray=0.4)
        self.y -= 20
        for i, (label, value) in enumerate(items):
            self.text(_LEFT + i * step, self.y, value, 15, bold=True)
        self.y -= 6

    def bars(self, items: list[tuple[str, int, int]]):
        """Einnahmen und Ausgaben je Monat als Balken: (Beschriftung, Einnahmen, Ausgaben) in Cent."""
        height = 110.0
        self.need(height + 50)
        self.y -= 14
        base = self.y - height
        top = max([1] + [max(i, e) for _l, i, e in items])
        slot = (_RIGHT - _LEFT) / max(1, len(items))
        for n, (label, income, expense) in enumerate(items):
            x = _LEFT + n * slot + slot / 2
            for dx, cents, gray in ((-7.5, income, 0.62), (0.5, expense, 0.2)):
                h = max(0.8, height * cents / top) if cents else 0.8
                self.rect(x + dx, base, 7, h, gray)
            self.text(x - text_width(label, 8) / 2, base - 12, label, 8, gray=0.4)
        self.line(_LEFT, base, _RIGHT, base, 0.7)
        self.y = base - 28
        self.rect(_LEFT, self.y + 1, 7, 7, 0.62)
        self.text(_LEFT + 11, self.y + 1, "Einnahmen", 8, gray=0.4)
        self.rect(_LEFT + 70, self.y + 1, 7, 7, 0.2)
        self.text(_LEFT + 81, self.y + 1, "Ausgaben", 8, gray=0.4)
        self.y -= 4

    # Ausgabe
    def bytes(self) -> bytes:
        made = date.today()
        total = len(self.pages)
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        catalog = add(b"")  # wird unten gefüllt
        pages_id = add(b"")
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        for n, ops in enumerate(self.pages, start=1):
            foot = Pdf.__new__(Pdf)
            foot.pages = [[]]
            foot.text(_LEFT, 36, f"Kassensturz · {self.title}", 8, gray=0.45)
            foot.text(_RIGHT, 36, f"Erstellt am {made.strftime('%d.%m.%Y')} · Seite {n} von {total}", 8,
                      align="right", gray=0.45)
            stream = zlib.compress("\n".join(ops + foot.pages[0]).encode("latin-1"))
            content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
            kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
                            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> >>"
                            % (pages_id, _PAGE_W, _PAGE_H, content, f1, f2)))
        objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
        objects[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        title = _encode(f"Kassensturz – {self.title}")
        title_hex = b"<FEFF" + "".join(f"{ord(c):04X}" for c in title.decode("cp1252")).encode() + b">"
        info = add(b"<< /Title " + title_hex + b" /Producer (Kassensturz) /CreationDate (D:"
                   + made.strftime("%Y%m%d").encode() + b") >>")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for n, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
        out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objects) + 1, catalog, info, xref)
        return bytes(out)


def _pct(value) -> str:
    return "–" if value is None else f"{round(value * 100)} %"


def _date(value: str) -> str:
    return f"{value[8:10]}.{value[5:7]}.{value[:4]}" if value and len(value) >= 10 else (value or "")


def month_pdf(db: Database, month: str, today: date | None = None) -> bytes:
    """Monatsbericht: Kennzahlen, Vergleich mit den Monaten davor, Kategorien, große Ausgaben, Kontostände."""
    today = today or date.today()
    y, m = (int(x) for x in month.split("-"))
    start = date(y, m, 1)
    if not (2000 <= y and start <= today):
        raise ValueError("month")
    review = analytics.month_review(db, month)
    stats = analytics.month_stats(db, month)
    end = min(month_end(start), today)
    title = f"Monatsbericht {review['label']}"
    pdf = Pdf(title)
    pdf.text(_LEFT, pdf.y, title, 20, bold=True)
    pdf.y -= 18
    pdf.text(_LEFT, pdf.y, f"{_date(start.isoformat())} bis {_date(end.isoformat())}"
             + ("" if review["complete"] else " · Monat läuft noch"), 10, gray=0.4)
    if not review["has_data"]:
        pdf.paragraph("Für diesen Monat gibt es keine Buchungen.")
        return pdf.bytes()
    pdf.facts([("Einnahmen", euro(review["income_cents"])), ("Ausgaben", euro(review["expense_cents"])),
               ("Saldo", euro(review["saved_cents"])), ("Sparquote", _pct(review["savings_rate"]))])
    pdf.y -= 6
    pdf.paragraph(analytics.review_message(review), 10.5)
    if review["usual_expense_cents"] is not None:
        pdf.paragraph(f"Üblich sind {euro(review['usual_expense_cents'])} Ausgaben im Monat "
                      f"(Schnitt der {review['compared_months']} Monate davor).", 9, gray=0.4)
    usual: dict = {}
    if review["compared_months"]:
        for i in range(1, 4):
            for item in analytics.month_stats(db, add_months(start, -i).strftime("%Y-%m"))["breakdown"]:
                usual.setdefault(item["category_id"], []).append(item["cents"])
    pdf.heading("Ausgaben nach Kategorie")
    rows = []
    for item in stats["breakdown"]:
        share = item["cents"] / review["expense_cents"] if review["expense_cents"] else 0
        before = usual.get(item["category_id"])
        rows.append([item["name"], euro(item["cents"]), "unter 1 %" if share < 0.005 else f"{round(share * 100)} %",
                     euro(int(sum(before) / review["compared_months"])) if before else "–"])
    rows.append(["Summe", euro(review["expense_cents"]), "100 %", euro(review["usual_expense_cents"])])
    pdf.table([("Kategorie", 0, "left"), ("Betrag", 0.62, "right"), ("Anteil", 0.78, "right"),
               ("Üblich", 1.0, "right")], rows, bold_last=True)
    singles = [e for e in sharing.spending(db, start.isoformat(), end.isoformat())
               if not e["is_transfer"] and e["amount_cents"] < 0 and not e["contract_key"]]
    singles.sort(key=lambda e: e["amount_cents"])
    if singles:
        pdf.heading("Größte Einzelausgaben (ohne Verträge)")
        pdf.table([("Datum", 0, "left"), ("Empfänger", 0.16, "left"), ("Betrag", 1.0, "right")],
                  [[_date(e["booking_date"]), (e.get("counterparty") or e.get("purpose") or "Ohne Empfänger")[:80],
                    euro(-e["amount_cents"])] for e in singles[:10]])
    accounts = [a for a in ledger.accounts_with_balance(db) if a["kind"] not in ("taschengeld",)]
    if accounts:
        pdf.heading(f"Kontostände am {_date(end.isoformat())}")
        rows = []
        for a in accounts:
            series = ledger.balance_series(db, [a["id"]], end, end)
            rows.append([a["name"], euro(series[-1][1] if series else a["balance_now"])])
        pdf.table([("Konto", 0, "left"), ("Stand", 1.0, "right")], rows)
        pdf.paragraph("Werte von Depots, Immobilien und Krediten sind die zuletzt eingetragenen.", 8.5, gray=0.45)
    return pdf.bytes()


def year_pdf(db: Database, year: int, today: date | None = None) -> bytes:
    """Jahresrückblick: Kennzahlen mit Vorjahr, Monate, Kategorien, große Einzelausgaben."""
    r = analytics.year_review(db, year, today=today)
    title = f"Jahresrückblick {year}"
    pdf = Pdf(title)
    pdf.text(_LEFT, pdf.y, title, 20, bold=True)
    pdf.y -= 18
    pdf.text(_LEFT, pdf.y, f"01.01.{year} bis {_date(r['until'])}" + (" · Jahr läuft noch" if r["running"] else ""),
             10, gray=0.4)
    if not r["has_data"]:
        pdf.paragraph("Für dieses Jahr gibt es keine Buchungen.")
        return pdf.bytes()
    pdf.facts([("Einnahmen", euro(r["income_cents"])), ("Ausgaben", euro(r["expense_cents"])),
               ("Saldo", euro(r["saved_cents"])), ("Sparquote", _pct(r["savings_rate"]))])
    p = r["previous"]
    if p:
        pdf.paragraph(f"Vorjahr{' bis zum selben Tag' if r['running'] else ''}: Einnahmen {euro(p['income_cents'])}, "
                      f"Ausgaben {euro(p['expense_cents'])}, Saldo {euro(p['saved_cents'])}.", 9.5, gray=0.4)
    lines = []
    if r["expense_cents"] and r["fixed_cents"]:
        lines.append(f"{round(r['fixed_cents'] / r['expense_cents'] * 100)} % der Ausgaben waren feste Zahlungen "
                     "aus Verträgen.")
    if r["best_month"] and r["worst_month"] and r["best_month"]["month"] != r["worst_month"]["month"]:
        lines.append(f"Bester Monat: {r['best_month']['label']} ({euro(r['best_month']['saldo_cents'])}), "
                     f"schwächster: {r['worst_month']['label']} ({euro(r['worst_month']['saldo_cents'])}).")
    if lines:
        pdf.y -= 4
        pdf.paragraph(" ".join(lines), 10.5)
    months = [m for m in r["months"] if not m["future"]]
    pdf.heading("Je Monat")
    pdf.bars([(m["label"][:3], m["income_cents"], m["expense_cents"]) for m in months])
    # Monate vor der ersten Buchung lässt die Tabelle weg
    while months and not (months[0]["income_cents"] or months[0]["expense_cents"]):
        months = months[1:]
    pdf.table([("Monat", 0, "left"), ("Einnahmen", 0.55, "right"), ("Ausgaben", 0.77, "right"), ("Saldo", 1.0, "right")],
              [[m["label"], euro(m["income_cents"]), euro(m["expense_cents"]), euro(m["saldo_cents"])] for m in months]
              + [["Summe", euro(r["income_cents"]), euro(r["expense_cents"]), euro(r["saved_cents"])]], bold_last=True)
    pdf.heading("Wofür das Geld ging")
    columns = [("Kategorie", 0, "left"), ("Betrag", 0.62 if p else 0.8, "right"), ("Anteil", 0.78 if p else 1.0, "right")]
    rows = [[c["name"], euro(c["cents"]), "unter 1 %" if c["share"] < 0.005 else f"{round(c['share'] * 100)} %"]
            for c in r["categories"]]
    if p:
        columns.append(("Vorjahr", 1.0, "right"))
        for row, c in zip(rows, r["categories"]):
            row.append(euro(c["previous_cents"]) if c["previous_cents"] is not None else "–")
    pdf.table(columns, rows)
    if r["moved"]:
        pdf.heading("Größte Veränderungen zum Vorjahr")
        pdf.table([("Kategorie", 0, "left"), ("Vorjahr", 0.62, "right"), ("Dieses Jahr", 0.8, "right"),
                   ("Veränderung", 1.0, "right")],
                  [[c["name"], euro(c["previous_cents"]), euro(c["cents"]),
                    ("+" if c["change_cents"] > 0 else "") + euro(c["change_cents"])] for c in r["moved"]])
    if r["biggest"]:
        pdf.heading("Größte Einzelausgaben (ohne Verträge)")
        pdf.table([("Datum", 0, "left"), ("Empfänger", 0.16, "left"), ("Betrag", 1.0, "right")],
                  [[_date(b["date"]), b["name"], euro(-b["amount_cents"])] for b in r["biggest"]])
    pdf.paragraph(f"{r['count']} Buchungen, ohne Umbuchungen zwischen eigenen Konten.", 8.5, gray=0.45)
    return pdf.bytes()
