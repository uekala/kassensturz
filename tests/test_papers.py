"""Steuerart und Belege – nur mit erfundenen Daten."""
import stat

from kassensturz import db as dbmod, ledger, papers, services

JPEG = b"\xff\xd8\xff\xe0" + b"erfundenes Foto" * 10
PDF = b"%PDF-1.4\n% erfundener Beleg\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _tx(db, day="2026-03-10", cents=-48000, who="Erfundener Malerbetrieb", account=None):
    account = account or db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    ledger.import_rows(db, account, [{"booking_date": day, "amount_cents": cents, "counterparty": who, "purpose": "Test"}], "datei")
    return db.scalar("SELECT MAX(id) FROM transactions"), account


def test_tax_kind_is_set_validated_and_cleared(client, db):
    tx, _ = _tx(db)
    assert client.patch(f"/api/transactions/{tx}", json={"tax_kind": "handwerker"}).status_code == 200
    item = client.get("/api/transactions").json()["items"][0]
    assert item["tax_kind"] == "handwerker"
    assert item["receipt_count"] == 0
    assert client.patch(f"/api/transactions/{tx}", json={"tax_kind": "erfunden"}).status_code == 400
    assert client.patch(f"/api/transactions/{tx}", json={"note": "bleibt"}).status_code == 200
    assert db.scalar("SELECT tax_kind FROM transactions WHERE id = ?", (tx,)) == "handwerker"
    client.patch(f"/api/transactions/{tx}", json={"tax_kind": None})
    assert db.scalar("SELECT tax_kind FROM transactions WHERE id = ?", (tx,)) is None


def test_tax_year_groups_sums_and_counts_missing_receipts(client, db):
    a, acc = _tx(db, "2026-03-10", -48000, "Erfundener Malerbetrieb")
    b, _ = _tx(db, "2026-06-01", -12000, "Erfundener Elektriker", acc)
    c, _ = _tx(db, "2026-09-15", -5000, "Erfundener Verein", acc)
    d, _ = _tx(db, "2025-12-20", -9900, "Erfundener Altfall", acc)
    for tx, kind in ((a, "handwerker"), (b, "handwerker"), (c, "spende"), (d, "spende")):
        client.patch(f"/api/transactions/{tx}", json={"tax_kind": kind})
    papers.add_receipt(db, a, "rechnung.pdf", PDF)

    data = client.get("/api/tax?year=2026").json()

    assert data["years"] == [2026, 2025]
    assert data["count"] == 3
    assert data["total_cents"] == 65000
    assert [(g["kind"], g["total_cents"], g["count"], g["missing_receipts"]) for g in data["groups"]] == [
        ("handwerker", 60000, 2, 1), ("spende", 5000, 1, 1)]
    assert client.get("/api/tax").json()["year"] == 2026
    assert [k["key"] for k in data["kinds"]] == list(papers.TAX_KINDS)


def test_tax_csv_lists_rows_and_neutralises_formulas(client, db):
    tx, _ = _tx(db, "2026-03-10", -48000, "=HYPERLINK(erfunden)")
    client.patch(f"/api/transactions/{tx}", json={"tax_kind": "handwerker"})
    res = client.get("/api/tax.csv?year=2026")
    assert res.status_code == 200
    assert "kassensturz-steuer-2026.csv" in res.headers["content-disposition"]
    lines = res.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Steuerart;Datum;Empfänger")
    assert lines[1].startswith("Handwerkerleistung;2026-03-10;'=HYPERLINK(erfunden);Test;480,00;Testgiro")
    assert lines[2].startswith("Summe Handwerkerleistung;;;;480,00")
    assert client.get("/api/tax.csv?year=12").status_code == 400


def test_receipt_upload_download_and_delete(client, db, tmp_path):
    tx, _ = _tx(db)
    res = client.post(f"/api/transactions/{tx}/receipts", files={"file": ("../../Rechnung März.JPG", JPEG, "text/html")})
    assert res.status_code == 200
    rid = res.json()["id"]
    assert res.json()["filename"] == "Rechnung März.jpg"
    assert res.json()["mime"] == "image/jpeg"
    assert "stored" not in res.json()

    stored = db.scalar("SELECT stored FROM receipts WHERE id = ?", (rid,))
    path = tmp_path / "belege" / stored
    assert path.read_bytes() == JPEG
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700

    got = client.get(f"/api/receipts/{rid}")
    assert got.content == JPEG
    assert got.headers["content-type"] == "image/jpeg"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-disposition"].startswith("inline")
    assert client.get("/api/transactions").json()["items"][0]["receipt_count"] == 1
    assert [r["id"] for r in client.get(f"/api/transactions/{tx}/receipts").json()["items"]] == [rid]

    assert client.delete(f"/api/receipts/{rid}").status_code == 200
    assert not path.exists()
    assert client.get(f"/api/receipts/{rid}").status_code == 404
    assert client.delete(f"/api/receipts/{rid}").status_code == 404


def test_receipt_rejects_wrong_content_size_and_count(client, db, monkeypatch):
    tx, _ = _tx(db)
    html = client.post(f"/api/transactions/{tx}/receipts", files={"file": ("beleg.pdf", b"<html><script>1</script>", "application/pdf")})
    assert html.status_code == 400
    svg = client.post(f"/api/transactions/{tx}/receipts", files={"file": ("beleg.png", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/png")})
    assert svg.status_code == 400
    assert client.post(f"/api/transactions/{tx}/receipts", files={"file": ("leer.pdf", b"", "application/pdf")}).status_code == 400
    assert client.post("/api/transactions/99999/receipts", files={"file": ("a.pdf", PDF, "application/pdf")}).status_code == 404

    monkeypatch.setattr(papers, "MAX_RECEIPT_BYTES", 64)
    assert client.post(f"/api/transactions/{tx}/receipts", files={"file": ("gross.png", PNG + b"\x00" * 64, "image/png")}).status_code == 400
    monkeypatch.setattr(papers, "MAX_RECEIPTS_PER_TX", 2)
    for _ in range(2):
        assert client.post(f"/api/transactions/{tx}/receipts", files={"file": ("a.png", PNG, "image/png")}).status_code == 200
    assert client.post(f"/api/transactions/{tx}/receipts", files={"file": ("a.png", PNG, "image/png")}).status_code == 400
    assert db.scalar("SELECT COUNT(*) FROM receipts") == 2
    assert len(list((dbmod.DATA_DIR / "belege").iterdir())) == 2


def test_receipts_disappear_with_their_account(db, tmp_path):
    tx, acc = _tx(db)
    keep, _ = _tx(db, who="Erfundener Bäcker")
    papers.add_receipt(db, tx, "a.pdf", PDF)
    papers.add_receipt(db, keep, "b.pdf", PDF)
    ledger.delete_account(db, acc)

    services.refresh(db, notify=False)

    assert [r["tx_id"] for r in db.query("SELECT tx_id FROM receipts")] == [keep]
    assert len(list((tmp_path / "belege").iterdir())) == 1


def test_receipt_file_ignores_manipulated_storage_names(db):
    tx, _ = _tx(db)
    rid = papers.add_receipt(db, tx, "a.pdf", PDF)["id"]
    db.execute("UPDATE receipts SET stored = ? WHERE id = ?", ("../kassensturz.sqlite", rid))
    assert papers.receipt_file(db, rid) is None
    assert papers.delete_receipt(db, rid) is True
