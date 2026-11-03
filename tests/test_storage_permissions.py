import os
import stat

import pytest


def test_database_directory_and_file_are_private(db):
    from kassensturz.db import DATA_DIR

    database_path = DATA_DIR / "test.sqlite"

    assert stat.S_IMODE(DATA_DIR.stat().st_mode) == 0o700
    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600


def test_secrets_file_is_created_with_private_permissions(db, tmp_path, monkeypatch):
    from kassensturz import secrets_store

    secret_path = tmp_path / "private-secrets.json"
    monkeypatch.setattr(secrets_store, "_PATH", secret_path)

    secrets_store.set_pin(7, "test-pin")
    assert secrets_store.get_pin(7) == "test-pin"
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600

    secrets_store.set_secret("private-key", "test-value")
    assert secrets_store.get_secret("private-key") == "test-value"
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600


def test_database_does_not_follow_existing_symlink(tmp_path):
    from kassensturz.db import Database

    target = tmp_path / "unrelated.txt"
    target.write_text("leave unchanged", encoding="utf-8")
    database_link = tmp_path / "linked.sqlite"
    try:
        database_link.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks are not available on this platform.")

    with pytest.raises(OSError):
        Database(database_link)

    assert target.read_text("utf-8") == "leave unchanged"
