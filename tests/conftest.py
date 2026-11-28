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
    from kassensturz import categorize, secrets_store
    from kassensturz import db as dbmod

    monkeypatch.setattr(dbmod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(secrets_store, "_PATH", tmp_path / "secrets.json")
    monkeypatch.setattr(secrets_store, "_KEY_PATH", tmp_path / "secrets.key")
    database = dbmod.reset_db_for_tests(tmp_path / "test.sqlite")
    categorize.ensure_categories(database)
    # Die Regeln gelten als angewandt: Tests setzen Kategorien oft direkt, der Start soll sie nicht neu zuordnen.
    database.set_setting(categorize.RULES_VERSION_KEY, categorize.RULES_VERSION)
    return database


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient
    from kassensturz.main import app

    with TestClient(app, client=("127.0.0.1", 50123)) as c:
        yield c


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
