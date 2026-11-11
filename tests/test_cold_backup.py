"""Cold backups: Home Assistant stops the app, archives /data and restores it.

The end-to-end test runs the real app (``python -m kassensturz``) like the
container does, stops it with SIGTERM, archives /data with the add-on's
``backup_exclude`` rules, restores the archive into an empty /data and compares
the data. All data is synthetic.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import tarfile
import time
from fnmatch import fnmatch
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "kassensturz" / "app"
SUPERVISOR_STOP_TIMEOUT = 10


def _config(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _backup_exclude(config: str) -> list[str]:
    block = re.search(r"^backup_exclude:\n((?:\s+- .+\n)+)", config, re.MULTILINE)
    assert block, "backup_exclude fehlt"
    return [line.split("-", 1)[1].strip().strip('"') for line in block.group(1).splitlines()]


@pytest.mark.parametrize(
    "config_path",
    [ROOT / "kassensturz" / "config.yaml", ROOT / "deploy/home-assistant-green/test-addon/config.yaml"],
)
def test_addons_use_cold_backups_and_keep_secrets_out(config_path):
    config = _config(config_path)
    assert re.search(r"^backup: cold$", config, re.MULTILINE)
    assert _backup_exclude(config) == ["secrets.json", "secrets.key"]


def test_graceful_shutdown_stays_below_the_supervisor_timeout():
    main = (APP_DIR / "kassensturz" / "__main__.py").read_text(encoding="utf-8")
    graceful = int(re.search(r"timeout_graceful_shutdown=(\d+)", main).group(1))
    assert 0 < graceful < SUPERVISOR_STOP_TIMEOUT


def test_close_writes_the_wal_into_the_database(tmp_path):
    from kassensturz import db as dbmod

    database = dbmod.Database(tmp_path / "k.sqlite")
    database.insert("accounts", {"name": "Testkonto", "created": dbmod.now_iso()})
    wal = tmp_path / "k.sqlite-wal"
    assert wal.exists() and wal.stat().st_size > 0

    database.close()

    assert not wal.exists() or wal.stat().st_size == 0
    with sqlite3.connect(f"file:{tmp_path / 'k.sqlite'}?mode=ro", uri=True) as check:
        assert check.execute("SELECT name FROM accounts").fetchall() == [("Testkonto",)]


def test_app_shutdown_closes_the_database(db, tmp_path):
    from fastapi.testclient import TestClient

    from kassensturz import db as dbmod
    from kassensturz.main import app

    with TestClient(app, client=("127.0.0.1", 50123)) as client:
        assert client.post("/api/accounts", json={"name": "Testkonto"}).status_code == 200
    assert dbmod._db is None
    with pytest.raises(sqlite3.ProgrammingError):
        db.conn.execute("SELECT 1")


# --- End to end: the real process, SIGTERM, archive, restore ---------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class App:
    def __init__(self, data_dir: Path, log: Path):
        self.data_dir = data_dir
        self.log = log
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.process: subprocess.Popen | None = None

    def start(self) -> App:
        env = {
            **os.environ,
            "KASSENSTURZ_DATA": str(self.data_dir),
            "KASSENSTURZ_HOST": "127.0.0.1",
            "KASSENSTURZ_PORT": str(self.port),
            "KASSENSTURZ_NO_BACKGROUND": "1",
            "KASSENSTURZ_INBOX": "",
            "PYTHONUNBUFFERED": "1",
        }
        with self.log.open("a", encoding="utf-8") as log:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "kassensturz"],
                cwd=APP_DIR,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(f"App beim Start beendet:\n{self.log.read_text()}")
            try:
                if httpx.get(f"{self.url}/api/accounts", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.kill()
        raise AssertionError(f"App antwortet nicht:\n{self.log.read_text()}")

    def stop(self) -> float:
        started = time.monotonic()
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=SUPERVISOR_STOP_TIMEOUT)
        except subprocess.TimeoutExpired as err:
            self.kill()
            raise AssertionError(f"Nicht innerhalb von {SUPERVISOR_STOP_TIMEOUT}s beendet") from err
        return time.monotonic() - started

    def kill(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()

    def accounts(self) -> list[dict]:
        rows = httpx.get(f"{self.url}/api/accounts", timeout=5).json()
        return sorted(({"name": r["name"], "iban": r.get("iban")} for r in rows), key=lambda r: r["name"])


def _ha_backup(data_dir: Path, archive: Path, exclude: list[str]) -> None:
    def skip(info: tarfile.TarInfo):
        name = info.name.split("/", 1)[1] if "/" in info.name else ""
        return None if any(fnmatch(name, pattern) for pattern in exclude) else info

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(data_dir, arcname="data", filter=skip)


@pytest.mark.skipif(os.name != "posix", reason="braucht POSIX-Signale wie der Container")
def test_cold_backup_and_restore_keep_the_data(tmp_path):
    data = tmp_path / "data"
    original = App(data, tmp_path / "app.log").start()
    try:
        for name, iban in [("Girokonto Test", "DE00 1234 5678 9012 3456 78"), ("Tagesgeld Test", None)]:
            body = {"name": name, **({"iban": iban} if iban else {})}
            assert httpx.post(f"{original.url}/api/accounts", json=body, timeout=5).status_code == 200
        expected = original.accounts()
        # A secret like a stored PIN must not end up in the backup.
        (data / "secrets.json").write_text('{"pin": "synthetisch"}', encoding="utf-8")
        (data / "secrets.key").write_bytes(b"x" * 32)
    finally:
        seconds = original.stop()

    assert seconds < SUPERVISOR_STOP_TIMEOUT
    assert "Kassensturz beendet, Datenbank geschlossen" in (tmp_path / "app.log").read_text()
    wal = data / "kassensturz.sqlite-wal"
    assert not wal.exists() or wal.stat().st_size == 0, "WAL nicht in die Datenbank geschrieben"
    with sqlite3.connect(f"file:{data / 'kassensturz.sqlite'}?mode=ro", uri=True) as check:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    archive = tmp_path / "ha-backup.tar.gz"
    _ha_backup(data, archive, _backup_exclude(_config(ROOT / "kassensturz" / "config.yaml")))
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "data/kassensturz.sqlite" in names
    assert not any(n.endswith(("secrets.json", "secrets.key")) for n in names)

    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(restored_root, filter="data")
    restored = App(restored_root / "data", tmp_path / "restored.log").start()
    try:
        assert restored.accounts() == expected
        assert expected[0]["iban"] == "DE00123456789012345678"
    finally:
        restored.stop()
