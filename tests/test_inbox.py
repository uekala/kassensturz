import os
import shutil
import time

import pytest

from conftest import FIXTURES


@pytest.fixture()
def folder(tmp_path, monkeypatch):
    p = tmp_path / "eingang"
    monkeypatch.setenv("KASSENSTURZ_INBOX", str(p))
    return p


def drop(folder, name, as_name=None):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (as_name or name)
    shutil.copy(FIXTURES / name, target)
    old = time.time() - 60
    os.utime(target, (old, old))
    return target


def test_known_iban_is_imported_and_moved(client, db, folder):
    from kassensturz import inbox

    client.post("/api/accounts", json={"name": "ING Girokonto", "kind": "giro", "iban": "DE89500105171234567890"})
    drop(folder, "ing.csv")
    res = inbox.scan(db)
    assert res["imported"][0]["added"] == 3 and res["pending"] == 0
    assert not (folder / "ing.csv").exists()
    assert len(list((folder / "importiert").iterdir())) == 1
    assert (folder / "LIESMICH.md").exists()


def test_fresh_files_wait_until_written(client, db, folder):
    from kassensturz import inbox

    inbox.ensure_folder()
    (folder / "neu.csv").write_bytes((FIXTURES / "ing.csv").read_bytes())
    assert inbox.scan(db)["imported"] == []
    assert (folder / "neu.csv").exists()


def test_unknown_file_waits_then_profile_makes_it_automatic(client, db, folder):
    from kassensturz import inbox

    drop(folder, "advanzia_export.csv", "umsaetze_okt.csv")
    res = inbox.scan(db)
    assert res["pending"] == 1
    st = client.get("/api/inbox").json()
    assert st["files"][0]["status"] == "pending" and st["available"]
    alerts = client.get("/api/overview").json()["alerts"] if client.get("/api/state").json()["accounts"] else []
    assert alerts == [] or any("Eingangsordner" in a["title"] for a in alerts)

    a = client.post("/api/inbox/analyze", json={"filename": "umsaetze_okt.csv"}).json()
    assert a["account_id"] is None and a["count"] == 2
    r = client.post("/api/import/commit", json={"token": a["token"], "new_account": {"name": "Advanzia", "kind": "kreditkarte"}}).json()
    assert r["added"] == 2
    assert not (folder / "umsaetze_okt.csv").exists()
    assert client.get("/api/inbox").json()["files"] == []

    # nächste Datei im selben Format geht ohne Rückfrage
    drop(folder, "advanzia_export.csv", "umsaetze_nov.csv")
    res = inbox.scan(db)
    assert res["imported"] and res["imported"][0]["account"] == "Advanzia"


def test_preset_name_matches_single_account(client, db, folder):
    from kassensturz import inbox

    client.post("/api/accounts", json={"name": "PayPal", "kind": "paypal", "settlement_pattern": "paypal"})
    drop(folder, "paypal.csv", "Download.CSV")
    res = inbox.scan(db)
    assert res["imported"][0]["account"] == "PayPal"


def test_bad_file_reported_and_deletable(client, db, folder):
    from kassensturz import inbox

    folder.mkdir(parents=True)
    bad = folder / "kaputt.csv"
    bad.write_text("nichts;hier\n1;2\n")
    old = time.time() - 60
    os.utime(bad, (old, old))
    inbox.scan(db)
    f = client.get("/api/inbox").json()["files"][0]
    assert f["status"] == "error"
    assert client.delete("/api/inbox/kaputt.csv").status_code == 200
    assert not bad.exists()
    assert client.post("/api/inbox/analyze", json={"filename": "../secrets.json"}).status_code == 404
