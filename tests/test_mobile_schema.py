import sqlite3

import pytest


def test_mobile_tables_are_created_without_changing_financial_data(db):
    tables = {
        row["name"]
        for row in db.query(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    assert {"mobile_pairings", "mobile_devices", "mobile_tokens"} <= tables
    assert db.one("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'transactions'")
    assert db.one("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'accounts'")


def test_mobile_pairing_secret_hash_is_unique(db):
    pairing = {
        "secret_hash": "hash-a",
        "created_at": "2026-11-03T10:00:00+01:00",
        "expires_at": "2026-11-03T10:05:00+01:00",
    }

    db.insert("mobile_pairings", pairing)

    with pytest.raises(sqlite3.IntegrityError):
        db.insert("mobile_pairings", pairing)


def test_mobile_device_identifier_is_unique(db):
    device = {
        "id": "device-1",
        "name": "Test phone",
        "created_at": "2026-11-03T10:00:00+01:00",
    }

    db.insert("mobile_devices", device)

    with pytest.raises(sqlite3.IntegrityError):
        db.insert("mobile_devices", device)

    missing_id = {key: value for key, value in device.items() if key != "id"}
    with pytest.raises(sqlite3.IntegrityError):
        db.insert("mobile_devices", missing_id)


def test_mobile_tokens_only_allow_access_and_refresh_types(db):
    db.insert(
        "mobile_devices",
        {
            "id": "device-1",
            "name": "Test phone",
            "created_at": "2026-11-03T10:00:00+01:00",
        },
    )

    base = {
        "device_id": "device-1",
        "created_at": "2026-11-03T10:00:00+01:00",
        "expires_at": "2026-11-03T10:10:00+01:00",
    }
    db.insert("mobile_tokens", {**base, "token_hash": "access-hash", "token_type": "access"})
    db.insert(
        "mobile_tokens",
        {
            **base,
            "token_hash": "refresh-hash",
            "token_type": "refresh",
            "expires_at": "2026-12-03T10:00:00+01:00",
        },
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.insert(
            "mobile_tokens",
            {**base, "token_hash": "invalid-hash", "token_type": "bearer"},
        )


def test_mobile_token_hash_is_unique_and_required(db):
    db.insert(
        "mobile_devices",
        {
            "id": "device-1",
            "name": "Test phone",
            "created_at": "2026-11-03T10:00:00+01:00",
        },
    )
    token = {
        "token_hash": "same-hash",
        "device_id": "device-1",
        "token_type": "access",
        "created_at": "2026-11-03T10:00:00+01:00",
        "expires_at": "2026-11-03T10:10:00+01:00",
    }
    db.insert("mobile_tokens", token)

    with pytest.raises(sqlite3.IntegrityError):
        db.insert("mobile_tokens", token)

    missing_hash = {key: value for key, value in token.items() if key != "token_hash"}
    with pytest.raises(sqlite3.IntegrityError):
        db.insert("mobile_tokens", missing_hash)



def test_mobile_schema_rejects_empty_secrets_and_labels(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.insert(
            "mobile_pairings",
            {
                "secret_hash": "",
                "created_at": "2026-11-03T10:00:00+01:00",
                "expires_at": "2026-11-03T10:05:00+01:00",
            },
        )

    with pytest.raises(sqlite3.IntegrityError):
        db.insert(
            "mobile_devices",
            {
                "id": "device-empty-name",
                "name": "   ",
                "created_at": "2026-11-03T10:00:00+01:00",
            },
        )

    db.insert(
        "mobile_devices",
        {
            "id": "device-1",
            "name": "Test phone",
            "created_at": "2026-11-03T10:00:00+01:00",
        },
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.insert(
            "mobile_tokens",
            {
                "token_hash": "   ",
                "device_id": "device-1",
                "token_type": "access",
                "created_at": "2026-11-03T10:00:00+01:00",
                "expires_at": "2026-11-03T10:10:00+01:00",
            },
        )


def test_legacy_mobile_tables_are_migrated_without_data_loss(tmp_path):
    from kassensturz.db import Database

    path = tmp_path / "legacy.sqlite"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE mobile_pairings(
          id INTEGER PRIMARY KEY,
          secret_hash TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          consumed_at TEXT
        );
        CREATE TABLE mobile_devices(
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          created_at TEXT NOT NULL,
          last_used_at TEXT,
          revoked_at TEXT
        );
        CREATE TABLE mobile_tokens(
          token_hash TEXT PRIMARY KEY,
          device_id TEXT NOT NULL,
          token_type TEXT NOT NULL CHECK(token_type IN ('access', 'refresh')),
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          revoked_at TEXT,
          replaced_by_hash TEXT
        );
        INSERT INTO mobile_pairings VALUES
          (1, 'pair-hash', '2026-11-03T10:00:00+01:00', '2026-11-03T10:05:00+01:00', NULL);
        INSERT INTO mobile_devices VALUES
          ('device-1', 'Old phone', '2026-11-03T10:00:00+01:00', NULL, NULL);
        INSERT INTO mobile_tokens VALUES
          ('token-hash', 'device-1', 'access', '2026-11-03T10:00:00+01:00',
           '2026-11-03T10:10:00+01:00', NULL, NULL);
        """
    )
    legacy.commit()
    legacy.close()

    migrated = Database(path)
    assert migrated.one("SELECT secret_hash FROM mobile_pairings WHERE id = 1")["secret_hash"] == "pair-hash"
    assert migrated.one("SELECT name FROM mobile_devices WHERE id = 'device-1'")["name"] == "Old phone"
    assert migrated.one("SELECT token_hash FROM mobile_tokens WHERE device_id = 'device-1'")["token_hash"] == "token-hash"

    with pytest.raises(sqlite3.IntegrityError):
        migrated.insert(
            "mobile_devices",
            {"id": " ", "name": "Invalid", "created_at": "2026-11-03T10:00:00+01:00"},
        )

    indexes = {
        row["name"]
        for row in migrated.query(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    assert {
        "mobile_pairings_expiry",
        "mobile_devices_active",
        "mobile_tokens_device",
        "mobile_tokens_expiry",
    } <= indexes
