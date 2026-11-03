import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kassensturz" / "app"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("KASSENSTURZ_DEV", "1")
os.environ.setdefault("KASSENSTURZ_NO_BACKGROUND", "1")
os.environ.setdefault("KASSENSTURZ_INBOX", "")

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from kassensturz import categorize, db as dbmod, secrets_store

    monkeypatch.setattr(dbmod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(secrets_store, "_PATH", tmp_path / "secrets.json")
    database = dbmod.reset_db_for_tests(tmp_path / "test.sqlite")
    categorize.ensure_categories(database)
    return database


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from kassensturz.main import app

    with TestClient(app) as c:
        yield c


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
