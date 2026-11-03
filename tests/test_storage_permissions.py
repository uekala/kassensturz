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
    assert stat.S_IMODE(secrets_store._KEY_PATH.stat().st_mode) == 0o600
    assert "test-pin" not in secret_path.read_text("utf-8")

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



def test_legacy_plaintext_secrets_are_migrated_on_first_read(db):
    import json

    from kassensturz import secrets_store

    secrets_store._PATH.write_text(
        json.dumps({"12": "legacy-pin", "secret:eb_private_key": "legacy-private-key"}),
        encoding="utf-8",
    )

    assert secrets_store.get_pin(12) == "legacy-pin"
    assert secrets_store.get_secret("eb_private_key") == "legacy-private-key"

    stored = json.loads(secrets_store._PATH.read_text("utf-8"))
    assert stored["format"] == "kassensturz-encrypted-secrets"
    assert stored["version"] == 1
    assert "legacy-pin" not in secrets_store._PATH.read_text("utf-8")
    assert "legacy-private-key" not in secrets_store._PATH.read_text("utf-8")
    assert stat.S_IMODE(secrets_store._KEY_PATH.stat().st_mode) == 0o600


def test_wrong_master_key_fails_closed_without_overwriting_secrets(db, monkeypatch):
    import pytest

    from kassensturz import secrets_store

    monkeypatch.setenv("KASSENSTURZ_MASTER_KEY", "11" * 32)
    secrets_store.set_pin(99, "do-not-lose-this-pin")
    before = secrets_store._PATH.read_bytes()

    monkeypatch.setenv("KASSENSTURZ_MASTER_KEY", "22" * 32)
    with pytest.raises(secrets_store.SecretsIntegrityError):
        secrets_store.get_pin(99)
    with pytest.raises(secrets_store.SecretsIntegrityError):
        secrets_store.set_pin(100, "another-pin")

    assert secrets_store._PATH.read_bytes() == before


def test_invalid_master_key_is_rejected(db, monkeypatch):
    import pytest

    from kassensturz import secrets_store

    monkeypatch.setenv("KASSENSTURZ_MASTER_KEY", "not-a-valid-key")
    with pytest.raises(secrets_store.SecretsKeyError):
        secrets_store.set_pin(1, "pin")


def test_tampered_encrypted_secrets_are_rejected(db):
    import json

    import pytest

    from kassensturz import secrets_store

    secrets_store.set_pin(5, "sensitive-pin")
    envelope = json.loads(secrets_store._PATH.read_text("utf-8"))
    ciphertext = envelope["ciphertext"]
    envelope["ciphertext"] = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    secrets_store._PATH.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(secrets_store.SecretsIntegrityError):
        secrets_store.get_pin(5)
