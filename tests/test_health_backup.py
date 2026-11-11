"""Überwachung (/healthz) und eigene Sicherungskopien der Datenbank."""
import sqlite3
import stat
from datetime import date, timedelta

from fastapi.testclient import TestClient

from kassensturz import backup, db as dbmod, options, services


def _account(database, name="Bargeld"):
    return database.insert("accounts", {"name": name, "kind": "cash", "created": dbmod.now_iso()})


def test_healthz_answers_locally_without_financial_data(client, db):
    _account(db)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "ok", "version": options.VERSION, "problems": []}


def test_healthz_is_closed_for_other_networks(db):
    from kassensturz.main import app

    with TestClient(app, client=("192.168.50.20", 40000)) as outside:
        assert outside.get("/healthz").status_code == 403


def test_healthz_reports_a_stalled_scheduler(client, db, monkeypatch):
    monkeypatch.delenv("KASSENSTURZ_NO_BACKGROUND", raising=False)
    monkeypatch.setattr(services, "scheduler_age_seconds", lambda: 901.0)
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["problems"] == ["scheduler"]

    monkeypatch.setattr(services, "scheduler_age_seconds", lambda: 30.0)
    assert client.get("/healthz").status_code == 200


def test_healthz_stays_ok_while_a_transaction_holds_the_database(client, db):
    import threading

    started, release = threading.Event(), threading.Event()

    def hold():
        with db.tx():
            started.set()
            release.wait(10)

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert started.wait(5)
        assert client.get("/healthz").status_code == 200
    finally:
        release.set()
        worker.join()


def test_daily_snapshot_is_a_complete_private_copy(db):
    _account(db, "Bargeld")
    with db.tx():
        _account(db, "Sparschwein")

    target = backup.run_if_due(db, date(2026, 11, 11))

    assert target is not None and target.name == "daily-2026-11-11.sqlite"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    copy = sqlite3.connect(str(target))
    try:
        assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        names = [row[0] for row in copy.execute("SELECT name FROM accounts ORDER BY name")]
    finally:
        copy.close()
    assert names == ["Bargeld", "Sparschwein"]
    assert not list(target.parent.glob("*.tmp"))


def test_snapshot_runs_once_per_day_and_keeps_seven(db):
    first = date(2026, 11, 1)
    assert backup.run_if_due(db, first) is not None
    assert backup.run_if_due(db, first) is None

    for offset in range(1, 10):
        backup.run_if_due(db, first + timedelta(days=offset))

    kept = sorted(path.name for path in backup.folder().glob("daily-*.sqlite"))
    assert len(kept) == backup.KEEP_DAILY
    assert kept[0] == "daily-2026-11-04.sqlite"
    assert kept[-1] == "daily-2026-11-10.sqlite"


def test_snapshot_refuses_to_run_inside_a_transaction(db):
    import pytest

    with db.tx():
        with pytest.raises(RuntimeError):
            backup.snapshot(db)


def test_first_start_of_a_new_version_saves_the_previous_state(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dbmod, "_db", None)
    path = tmp_path / "kassensturz.sqlite"
    current = options.VERSION

    # Kein Bestand: nichts zu sichern.
    database = dbmod.get_db()
    assert not backup.folder().exists()
    assert database.get_setting(backup.VERSION_KEY) == options.VERSION
    _account(database, "Altbestand")

    # Gleicher Stand: kein weiterer Start legt eine Kopie an.
    dbmod.close_db()
    dbmod.get_db()
    assert not list(backup.folder().glob("pre-update-*.sqlite")) if backup.folder().exists() else True

    # Neue Version: der Stand der alten wird vorher gesichert.
    dbmod.close_db()
    monkeypatch.setattr(options, "VERSION", "9.9.9")
    database = dbmod.get_db()
    copies = list(backup.folder().glob("pre-update-*.sqlite"))
    assert len(copies) == 1
    assert copies[0].name.endswith(f"-von-{current}.sqlite")
    assert stat.S_IMODE(copies[0].stat().st_mode) == 0o600
    copy = sqlite3.connect(str(copies[0]))
    try:
        assert copy.execute("SELECT name FROM accounts").fetchone()[0] == "Altbestand"
        assert copy.execute("SELECT value FROM settings WHERE key = 'app_version'").fetchone()[0] == f'"{current}"'
    finally:
        copy.close()
    assert database.get_setting(backup.VERSION_KEY) == "9.9.9"
    dbmod.close_db()
    assert path.exists()


def test_a_failing_copy_does_not_stop_the_start(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dbmod, "_db", None)
    dbmod.get_db()
    dbmod.close_db()

    def broken(*_args):
        raise OSError("Datenträger voll")

    monkeypatch.setattr(backup, "_copy", broken)
    monkeypatch.setattr(options, "VERSION", "9.9.9")
    assert dbmod.get_db().get_setting(backup.VERSION_KEY) == "9.9.9"
    dbmod.close_db()
