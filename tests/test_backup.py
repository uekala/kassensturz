

def test_restore_rehearsal_leaves_live_data_alone(client, db, tmp_path, monkeypatch):
    import hashlib

    from kassensturz import backup
    acc = db.insert("accounts", {"name": "KS-Testgiro", "kind": "giro"})
    for n in range(3):
        db.insert("transactions", {"account_id": acc, "booking_date": f"2026-11-0{n + 1}", "amount_cents": -100 * (n + 1),
                                   "counterparty": "Erfunden", "hash": f"ks-probe-{n}"})
    copies = tmp_path / "kopien"
    monkeypatch.setattr(backup, "folder", lambda: copies)
    copy = backup.snapshot(db)
    # Nach der Kopie: eine neue und eine gelöschte Buchung
    db.insert("transactions", {"account_id": acc, "booking_date": "2026-11-09", "amount_cents": -900,
                               "counterparty": "Erfunden", "hash": "ks-probe-neu"})
    db.execute("DELETE FROM transactions WHERE hash = 'ks-probe-0'")
    live_file = db.path.read_bytes()
    before = hashlib.sha256(live_file).hexdigest()
    copy_before = hashlib.sha256(copy.read_bytes()).hexdigest()

    r = client.post("/api/health/restore-rehearsal").json()
    assert r["found"] and r["ok"] and r["name"] == copy.name
    assert [s["name"] for s in r["steps"]] == ["open", "compute", "compare", "outside"]
    assert (r["backup_transactions"], r["live_new"], r["gone"]) == (3, 1, 1)
    assert "1 Buchungen der Kopie fehlen" in r["steps"][2]["text"] and "1 Buchungen dazugekommen" in r["steps"][2]["text"]
    # Weder der Bestand noch die Kopie wurden verändert, und es bleibt kein Probe-Ordner zurück.
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == copy_before
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 3
    assert hashlib.sha256(db.path.read_bytes()).hexdigest() == before
    import glob
    import tempfile
    assert not glob.glob(tempfile.gettempdir() + "/kassensturz-probe-*")


def test_restore_rehearsal_without_copy_or_with_broken_copy(db, tmp_path, monkeypatch):
    from kassensturz import backup, health
    copies = tmp_path / "kopien"
    copies.mkdir()
    monkeypatch.setattr(backup, "folder", lambda: copies)
    assert health.rehearse_restore(db) == {"found": False, "ok": False}
    broken = copies / "daily-2026-11-19.sqlite"
    broken.write_bytes(b"kein SQLite")
    r = health.rehearse_restore(db)
    assert r["found"] and not r["ok"] and r["steps"][-1]["text"].startswith("Abgebrochen")
