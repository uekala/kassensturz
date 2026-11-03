"""Vollständiger Abruf gegen die Test-Bank aus dem Quellcode von python-fints.
Ausführen mit: FINTS_TESTS_DIR=/pfad/zu/python-fints/tests pytest tests/test_fints_mock.py"""
import importlib.util
import os
import time
from pathlib import Path

import pytest

TESTS_DIR = os.environ.get("FINTS_TESTS_DIR")
if not TESTS_DIR or not (Path(TESTS_DIR) / "conftest.py").exists():
    pytest.skip("FINTS_TESTS_DIR nicht gesetzt", allow_module_level=True)

spec = importlib.util.spec_from_file_location("fints_test_bank", Path(TESTS_DIR) / "conftest.py")
bank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank)
fints_server = bank.fints_server  # pytest-Fixture


def _wait(job):
    for _ in range(200):
        if job.state not in ("running", "waiting"):
            return job
        time.sleep(0.05)
    raise AssertionError("Abruf hängt")


def test_full_sync_against_test_bank(db, fints_server, monkeypatch):
    import fints.client as fc
    import fints.parser

    from kassensturz import fints_sync, ledger, secrets_store

    fints.parser.robust_mode = True
    monkeypatch.setenv("KASSENSTURZ_FINTS_PRODUCT_ID", "TEST-123")
    orig = fc.FinTS3Client.get_transactions
    # Die Test-Bank kennt keine Datumsgrenzen im Umsatzabruf
    monkeypatch.setattr(fc.FinTS3Client, "get_transactions", lambda self, acc, s=None, e=None, include_pending=False: orig(self, acc))

    cid = db.insert("connections", {"name": "Testbank", "blz": "12345678", "login": "test1", "server": fints_server, "history_days": 90})
    job = _wait(fints_sync.start(cid, "1234", save_pin=True))
    assert job.state == "done", job.error
    assert job.result["added"] == 3
    acc = ledger.accounts_with_balance(db)[0]
    assert acc["iban"] == "DE111234567800000001" and acc["tx_count"] == 3
    assert secrets_store.has_pin(cid)

    again = _wait(fints_sync.start(cid, None))
    assert again.state == "done" and again.result["added"] == 0

    wrong = _wait(fints_sync.start(cid, "9999"))
    assert wrong.state == "error" and "PIN" in wrong.error
