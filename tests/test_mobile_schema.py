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
