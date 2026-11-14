"""Vollständige Sicherung, Schema-Version und Zustandsprüfung – nur erfundene Daten."""
import hashlib
import io
import json
import sqlite3
import stat
import zipfile
from datetime import date, timedelta

import pytest

from kassensturz import backup, db as dbmod, health, ledger, options, papers, services, umzug

JPEG = b"\xff\xd8\xff\xe0" + b"erfundenes Foto" * 20
PDF = b"%PDF-1.4\n% erfundener Beleg\n"


def _filled(db):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro", "created": dbmod.now_iso()})
    ledger.import_rows(db, acc, [{"booking_date": "2026-03-10", "amount_cents": -48000,
                                  "counterparty": "Erfundener Malerbetrieb", "purpose": "Test"}], "datei")
    tx = db.scalar("SELECT MAX(id) FROM transactions")
    papers.add_receipt(db, tx, "foto.jpg", JPEG)
    papers.add_receipt(db, tx, "rechnung.pdf", PDF)
    return tx


def _archive(client):
    response = client.get("/api/umzug/archive")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert umzug.ARCHIVE in response.headers["content-disposition"]
    return response.content


def _drop(tmp_path, content, name=umzug.ARCHIVE):
    folder = tmp_path / "eingang" / umzug.SUBFOLDER
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_bytes(content)
    return target


def _rebuild(content, change):
    """Archiv auspacken, verändern, neu packen."""
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    change(members)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for name, data in members.items():
            target.writestr(name, data)
    return out.getvalue()


def test_archive_holds_database_receipts_and_checksums(client, db):
    _filled(db)
    with zipfile.ZipFile(io.BytesIO(_archive(client))) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read(umzug.ARCHIVE_MANIFEST))
        stored = [r["stored"] for r in db.query("SELECT stored FROM receipts ORDER BY id")]
        assert names == {umzug.ARCHIVE_MANIFEST, umzug.ARCHIVE_DB, *(f"belege/{name}" for name in stored)}
        assert manifest["format"] == 1
        assert manifest["app_version"] == options.VERSION
        assert manifest["receipts"] == 2 and manifest["missing_receipts"] == 0
        for name, entry in manifest["files"].items():
            data = archive.read(name)
            assert entry == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        assert archive.read(f"belege/{stored[0]}") == JPEG


def test_archive_is_closed_for_other_networks(db):
    from fastapi.testclient import TestClient

    from kassensturz.main import app

    with TestClient(app, client=("192.168.50.20", 40000)) as outside:
        assert outside.get("/api/umzug/archive").status_code == 403
        assert outside.get("/api/health").status_code == 403


def test_fresh_installation_restores_database_and_receipts(client, db, tmp_path):
    tx = _filled(db)
    dropped = _drop(tmp_path, _archive(client))
    fresh = tmp_path / "neu" / "kassensturz.sqlite"

    assert umzug.adopt_if_fresh(fresh, tmp_path / "eingang") is True

    assert not dropped.exists()
    restored = sqlite3.connect(str(fresh))
    try:
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert restored.execute("SELECT counterparty FROM transactions WHERE id = ?", (tx,)).fetchone()[0] == "Erfundener Malerbetrieb"
        stored = [row[0] for row in restored.execute("SELECT stored FROM receipts ORDER BY id")]
    finally:
        restored.close()
    folder = fresh.parent / "belege"
    assert sorted(p.name for p in folder.iterdir()) == sorted(stored)
    assert (folder / stored[0]).read_bytes() == JPEG
    assert stat.S_IMODE((folder / stored[0]).stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o600
    assert sorted(p.name for p in fresh.parent.iterdir()) == ["belege", "kassensturz.sqlite"]


def test_installation_with_data_is_never_overwritten(client, db, tmp_path):
    _filled(db)
    dropped = _drop(tmp_path, _archive(client))
    assert umzug.adopt_if_fresh(db.path, tmp_path / "eingang") is False
    assert dropped.exists()
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 1


def _tamper_receipt(members):
    name = next(n for n in members if n.startswith("belege/") and n.endswith(".jpg"))
    members[name] = members[name][:-1] + b"X"


def _add_stray(members):
    members["belege/../../fremd.sh"] = b"#!/bin/sh"


def _add_listed_stray(members):
    manifest = json.loads(members[umzug.ARCHIVE_MANIFEST])
    data = b"<html>"
    manifest["files"]["belege/fremd.html"] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    members[umzug.ARCHIVE_MANIFEST] = json.dumps(manifest).encode()
    members["belege/fremd.html"] = data


def _drop_manifest(members):
    del members[umzug.ARCHIVE_MANIFEST]


def _lie_about_size(members):
    manifest = json.loads(members[umzug.ARCHIVE_MANIFEST])
    manifest["files"][umzug.ARCHIVE_DB]["bytes"] = 10
    members[umzug.ARCHIVE_MANIFEST] = json.dumps(manifest).encode()


def _break_database(members):
    data = b"keine Datenbank"
    manifest = json.loads(members[umzug.ARCHIVE_MANIFEST])
    manifest["files"][umzug.ARCHIVE_DB] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    members[umzug.ARCHIVE_MANIFEST] = json.dumps(manifest).encode()
    members[umzug.ARCHIVE_DB] = data


@pytest.mark.parametrize("change", [_tamper_receipt, _add_stray, _add_listed_stray, _drop_manifest, _lie_about_size, _break_database])
def test_damaged_or_foreign_archives_change_nothing(client, db, tmp_path, change):
    _filled(db)
    dropped = _drop(tmp_path, _rebuild(_archive(client), change))
    fresh = tmp_path / "neu" / "kassensturz.sqlite"

    assert umzug.adopt_if_fresh(fresh, tmp_path / "eingang") is False

    assert dropped.exists()
    assert not fresh.exists()
    assert not (fresh.parent / "belege").exists() or not list((fresh.parent / "belege").iterdir())
    assert not (tmp_path / "fremd.sh").exists()
    leftovers = [p.name for p in fresh.parent.iterdir()] if fresh.parent.exists() else []
    assert [n for n in leftovers if n.startswith("umzug-")] == []


def test_not_a_zip_changes_nothing(tmp_path):
    _drop(tmp_path, b"kein Archiv")
    fresh = tmp_path / "neu" / "kassensturz.sqlite"
    assert umzug.adopt_if_fresh(fresh, tmp_path / "eingang") is False
    assert not fresh.exists()


def test_schema_version_is_written_and_a_newer_one_is_kept(tmp_path):
    path = tmp_path / "s" / "kassensturz.sqlite"
    first = dbmod.Database(path)
    assert first.schema_before == 0 and first.newer_schema is False and first.integrity == "ok"
    assert first.conn.execute("PRAGMA user_version").fetchone()[0] == dbmod.SCHEMA_VERSION
    first.conn.execute(f"PRAGMA user_version = {dbmod.SCHEMA_VERSION + 5}")
    first.close()

    again = dbmod.Database(path)
    try:
        assert again.newer_schema is True
        assert again.conn.execute("PRAGMA user_version").fetchone()[0] == dbmod.SCHEMA_VERSION + 5
        titles = [a["title"] for a in health.alerts(again)]
        assert titles == ["Die Daten stammen von einer neueren Version"]
    finally:
        again.close()


def test_health_reports_database_receipts_and_backups(client, db, tmp_path):
    _filled(db)
    state = client.get("/api/health").json()
    assert state["integrity_ok"] is True
    assert (state["accounts"], state["transactions"]) == (1, 1)
    assert state["receipts"] == {"count": 2, "bytes": len(JPEG) + len(PDF), "missing": 0}
    assert state["backups"] == {"count": 0, "newest": None, "age_days": None, "stale": True}
    assert client.post("/api/health/backup-check").json() == {"found": False, "ok": False}
    assert health.alerts(db) == []

    backup.snapshot(db, date.today())
    state = client.get("/api/health").json()
    assert state["backups"]["count"] == 1
    assert state["backups"]["stale"] is False and state["backups"]["age_days"] == 0
    checked = client.post("/api/health/backup-check").json()
    assert checked["ok"] is True and checked["integrity"] == "ok"
    assert (checked["accounts"], checked["transactions"], checked["live_transactions"]) == (1, 1, 1)
    assert checked["newest_booking"] == "2026-03-10"


def test_broken_backup_and_missing_receipt_are_noticed(client, db, tmp_path):
    _filled(db)
    target = backup.snapshot(db, date.today() - timedelta(days=1))
    target.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    checked = client.post("/api/health/backup-check").json()
    assert checked["found"] is True and checked["ok"] is False
    assert checked["integrity"]

    stored = db.scalar("SELECT stored FROM receipts ORDER BY id LIMIT 1")
    (tmp_path / "belege" / stored).unlink()
    assert client.get("/api/health").json()["receipts"]["missing"] == 1
    alerts = [a for a in services.alerts(db, services.build_summary(db)) if a["key"].startswith("health:")]
    assert [a["title"] for a in alerts] == ["Belegdateien fehlen"]


def test_integrity_failure_becomes_a_critical_alert(db):
    db.integrity = "*** in database main ***"
    alerts = health.alerts(db)
    assert [(a["level"], a["title"]) for a in alerts] == [("critical", "Die Datenbank ist beschädigt")]
    assert health.status(db)["integrity_ok"] is False
