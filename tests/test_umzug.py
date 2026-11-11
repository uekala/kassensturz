"""Umzug der Datenbank: Export über die Oberfläche, Übernahme beim Start."""
import sqlite3
import stat

from kassensturz import db as dbmod, umzug


def _account(database, name="Girokonto"):
    return database.insert("accounts", {"name": name, "kind": "giro", "created": dbmod.now_iso()})


def _export(client, tmp_path):
    response = client.get("/api/umzug/export")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert umzug.FILENAME in response.headers["content-disposition"]
    folder = tmp_path / "eingang" / umzug.SUBFOLDER
    folder.mkdir(parents=True)
    target = folder / umzug.FILENAME
    target.write_bytes(response.content)
    return target


def test_export_is_a_complete_database(client, db, tmp_path):
    _account(db, "Tagesgeld")
    exported = _export(client, tmp_path)
    conn = sqlite3.connect(str(exported))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert [row[0] for row in conn.execute("SELECT name FROM accounts")] == ["Tagesgeld"]
    finally:
        conn.close()


def test_export_is_closed_for_other_networks(db):
    from fastapi.testclient import TestClient

    from kassensturz.main import app

    with TestClient(app, client=("192.168.50.20", 40000)) as outside:
        assert outside.get("/api/umzug/export").status_code == 403


def test_fresh_installation_adopts_the_file_and_removes_it(client, db, tmp_path):
    _account(db, "Tagesgeld")
    exported = _export(client, tmp_path)
    new_path = tmp_path / "neu" / "kassensturz.sqlite"

    assert umzug.adopt_if_fresh(new_path, tmp_path / "eingang") is True
    assert not exported.exists()
    assert stat.S_IMODE(new_path.stat().st_mode) == 0o600
    adopted = dbmod.Database(new_path)
    try:
        assert [row["name"] for row in adopted.query("SELECT name FROM accounts")] == ["Tagesgeld"]
    finally:
        adopted.close()


def test_empty_existing_database_is_replaced(client, db, tmp_path):
    _account(db)
    _export(client, tmp_path)
    new_path = tmp_path / "neu" / "kassensturz.sqlite"
    dbmod.Database(new_path).close()

    assert umzug.adopt_if_fresh(new_path, tmp_path / "eingang") is True
    conn = sqlite3.connect(str(new_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
    finally:
        conn.close()


def test_installation_with_data_is_never_overwritten(client, db, tmp_path):
    _account(db, "Alt")
    exported = _export(client, tmp_path)
    new_path = tmp_path / "neu" / "kassensturz.sqlite"
    existing = dbmod.Database(new_path)
    existing.insert("accounts", {"name": "Schon da", "kind": "cash", "created": dbmod.now_iso()})
    existing.close()

    assert umzug.adopt_if_fresh(new_path, tmp_path / "eingang") is False
    assert exported.exists()
    conn = sqlite3.connect(str(new_path))
    try:
        assert [row[0] for row in conn.execute("SELECT name FROM accounts")] == ["Schon da"]
    finally:
        conn.close()


def test_foreign_or_broken_files_are_rejected(tmp_path):
    folder = tmp_path / "eingang" / umzug.SUBFOLDER
    folder.mkdir(parents=True)
    source = folder / umzug.FILENAME
    new_path = tmp_path / "neu" / "kassensturz.sqlite"

    source.write_bytes(b"kein sqlite" * 100)
    assert umzug.adopt_if_fresh(new_path, tmp_path / "eingang") is False
    assert not new_path.exists()

    source.unlink()
    other = sqlite3.connect(str(source))
    other.execute("CREATE TABLE notizen (text TEXT)")
    other.commit()
    other.close()
    assert umzug.adopt_if_fresh(new_path, tmp_path / "eingang") is False
    assert not new_path.exists()
    assert source.exists()


def test_symlink_and_missing_folder_are_ignored(tmp_path):
    new_path = tmp_path / "neu" / "kassensturz.sqlite"
    assert umzug.adopt_if_fresh(new_path, None) is False
    assert umzug.adopt_if_fresh(new_path, tmp_path / "eingang") is False

    folder = tmp_path / "eingang" / umzug.SUBFOLDER
    folder.mkdir(parents=True)
    real = tmp_path / "woanders.sqlite"
    real.write_bytes(b"")
    (folder / umzug.FILENAME).symlink_to(real)
    assert umzug.adopt_if_fresh(new_path, tmp_path / "eingang") is False
