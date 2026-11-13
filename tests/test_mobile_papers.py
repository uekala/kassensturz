"""Steuerart und Belege aus der App – nur erfundene Daten."""
from kassensturz import ledger, papers
from test_mobile_write import https_client, paired_headers, reset_mobile_guards

JPEG = b"\xff\xd8\xff\xe0" + b"erfundenes Foto" * 10
PDF = b"%PDF-1.4\n% erfundener Beleg\n"


def _tx(db, archived=0):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro", "archived": archived})
    ledger.import_rows(db, acc, [{"booking_date": "2026-03-10", "amount_cents": -48000,
                                  "counterparty": "Erfundener Malerbetrieb", "purpose": "Test"}], "fints")
    return db.scalar("SELECT MAX(id) FROM transactions")


def test_tax_kind_can_be_set_on_bank_transactions(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    tx = _tx(db)
    with https_client() as client:
        headers = paired_headers(client)
        r = client.patch(f"/api/v1/transactions/{tx}", json={"tax_kind": "handwerker"}, headers=headers)
        assert r.status_code == 200
        assert r.json()["transaction"]["tax_kind"] == "handwerker"
        assert r.json()["transaction"]["receipt_count"] == 0
        item = client.get("/api/v1/transactions", headers=headers).json()["items"][0]
        assert (item["tax_kind"], item["receipt_count"]) == ("handwerker", 0)
        for bad in ("erfunden", 5, ["handwerker"], {"a": 1}):
            assert client.patch(f"/api/v1/transactions/{tx}", json={"tax_kind": bad}, headers=headers).status_code == 400, bad
        assert client.patch(f"/api/v1/transactions/{tx}", json={"tax_kind": None}, headers=headers).status_code == 200
        assert db.scalar("SELECT tax_kind FROM transactions WHERE id = ?", (tx,)) is None


def test_receipt_roundtrip(db, monkeypatch, tmp_path):
    reset_mobile_guards(monkeypatch)
    tx = _tx(db)
    with https_client() as client:
        headers = paired_headers(client)
        up = client.post(f"/api/v1/transactions/{tx}/receipts?filename=..%2FRechnung.JPG", content=JPEG,
                         headers={**headers, "Content-Type": "application/octet-stream"})
        assert up.status_code == 201
        receipt = up.json()["receipt"]
        assert receipt == {"id": receipt["id"], "filename": "Rechnung.jpg", "mime": "image/jpeg", "size": len(JPEG)}

        listed = client.get(f"/api/v1/transactions/{tx}/receipts", headers=headers).json()
        assert listed["items"] == [receipt]
        assert listed["max"] == papers.MAX_RECEIPTS_PER_TX
        assert client.get("/api/v1/transactions", headers=headers).json()["items"][0]["receipt_count"] == 1

        got = client.get(f"/api/v1/receipts/{receipt['id']}", headers=headers)
        assert got.content == JPEG
        assert got.headers["content-type"] == "image/jpeg"
        assert got.headers["x-content-type-options"] == "nosniff"

        assert client.delete(f"/api/v1/receipts/{receipt['id']}", headers=headers).status_code == 200
        assert client.get(f"/api/v1/receipts/{receipt['id']}", headers=headers).status_code == 404
        assert not list((tmp_path / "belege").iterdir())


def test_receipt_upload_is_validated(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    tx = _tx(db)
    with https_client() as client:
        headers = {**paired_headers(client), "Content-Type": "application/octet-stream"}
        assert client.post(f"/api/v1/transactions/{tx}/receipts", content=b"<html>", headers=headers).status_code == 400
        assert client.post(f"/api/v1/transactions/{tx}/receipts", content=b"", headers=headers).status_code == 400
        assert client.post("/api/v1/transactions/999999/receipts", content=PDF, headers=headers).status_code == 404
        assert client.post("/api/v1/transactions/abc/receipts", content=PDF, headers=headers).status_code == 404
        monkeypatch.setattr(papers, "MAX_RECEIPT_BYTES", 16)
        assert client.post(f"/api/v1/transactions/{tx}/receipts", content=PDF, headers=headers).status_code == 413
        assert db.scalar("SELECT COUNT(*) FROM receipts") == 0


def test_receipts_need_a_paired_device_and_a_visible_transaction(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    tx = _tx(db)
    hidden = _tx(db, archived=1)
    rid = papers.add_receipt(db, tx, "a.pdf", PDF)["id"]
    hidden_rid = papers.add_receipt(db, hidden, "b.pdf", PDF)["id"]
    with https_client() as client:
        for method, path in (("GET", f"/api/v1/transactions/{tx}/receipts"), ("POST", f"/api/v1/transactions/{tx}/receipts"),
                             ("GET", f"/api/v1/receipts/{rid}"), ("DELETE", f"/api/v1/receipts/{rid}")):
            assert client.request(method, path).status_code == 401, (method, path)
            assert client.request(method, path, headers={"Authorization": "Bearer falsch"}).status_code == 401
        headers = paired_headers(client)
        assert client.get(f"/api/v1/transactions/{hidden}/receipts", headers=headers).status_code == 404
        assert client.get(f"/api/v1/receipts/{hidden_rid}", headers=headers).status_code == 404
        assert client.delete(f"/api/v1/receipts/{hidden_rid}", headers=headers).status_code == 404
        assert db.scalar("SELECT COUNT(*) FROM receipts") == 2


def test_receipt_upload_is_rate_limited(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    tx = _tx(db)
    with https_client() as client:
        headers = {**paired_headers(client), "Content-Type": "application/octet-stream"}
        codes = [client.post(f"/api/v1/transactions/{tx}/receipts", content=b"x", headers=headers).status_code for _ in range(31)]
        assert codes[:30] == [400] * 30
        assert codes[30] == 429
