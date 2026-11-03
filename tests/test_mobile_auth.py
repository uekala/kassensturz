from datetime import datetime, timedelta, timezone

import pytest

from kassensturz.mobile_auth import (
    ACCESS_TTL,
    MAX_ACTIVE_PAIRINGS,
    REFRESH_TTL,
    InvalidCredential,
    MobileAuthService,
    PairingLimitReached,
    PairingRejected,
    RefreshReplayDetected,
)


class FrozenClock:
    def __init__(self):
        self.current = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.current

    def advance(self, delta: timedelta):
        self.current += delta


@pytest.fixture
def mobile_auth(db):
    clock = FrozenClock()
    return MobileAuthService(db, clock=clock), clock


def test_pairing_secret_is_random_short_lived_and_only_stored_as_hash(db, mobile_auth):
    service, clock = mobile_auth

    pairing = service.create_pairing()

    assert len(pairing["pairing_secret"]) >= 43
    assert pairing["expires_at"] == (
        clock.current + timedelta(minutes=5)
    ).isoformat(timespec="seconds")
    stored = db.one("SELECT * FROM mobile_pairings")
    assert stored["secret_hash"] != pairing["pairing_secret"]
    assert stored["secret_hash"] != ""
    assert stored["consumed_at"] is None


def test_pairing_can_be_redeemed_only_once(db, mobile_auth):
    service, _ = mobile_auth
    pairing = service.create_pairing()

    result = service.redeem_pairing(pairing["pairing_secret"], "Mein iPhone")

    assert result["device"]["name"] == "Mein iPhone"
    assert result["access_expires_in"] == int(ACCESS_TTL.total_seconds())
    assert result["refresh_expires_in"] == int(REFRESH_TTL.total_seconds())
    assert result["token_type"] == "Bearer"

    stored_tokens = db.query(
        "SELECT token_hash, token_type FROM mobile_tokens ORDER BY token_type"
    )
    assert {row["token_type"] for row in stored_tokens} == {"access", "refresh"}
    assert result["access_token"] not in {row["token_hash"] for row in stored_tokens}
    assert result["refresh_token"] not in {row["token_hash"] for row in stored_tokens}

    with pytest.raises(PairingRejected):
        service.redeem_pairing(pairing["pairing_secret"], "Zweites Gerät")

    assert db.scalar("SELECT COUNT(*) FROM mobile_devices") == 1


def test_expired_pairing_is_rejected_without_creating_a_device(db, mobile_auth):
    service, clock = mobile_auth
    pairing = service.create_pairing()
    clock.advance(timedelta(minutes=5))

    with pytest.raises(PairingRejected):
        service.redeem_pairing(pairing["pairing_secret"], "iPhone")

    assert db.scalar("SELECT COUNT(*) FROM mobile_devices") == 0
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens") == 0


def test_pairing_rejects_invalid_device_names(db, mobile_auth):
    service, _ = mobile_auth
    pairing = service.create_pairing()

    with pytest.raises(PairingRejected):
        service.redeem_pairing(pairing["pairing_secret"], "  ")

    assert db.scalar("SELECT COUNT(*) FROM mobile_devices") == 0
    assert db.one("SELECT consumed_at FROM mobile_pairings")["consumed_at"] is None


def test_only_a_bounded_number_of_active_pairings_can_exist(db, mobile_auth):
    service, _ = mobile_auth

    for _ in range(MAX_ACTIVE_PAIRINGS):
        service.create_pairing()

    with pytest.raises(PairingLimitReached):
        service.create_pairing()

    assert db.scalar("SELECT COUNT(*) FROM mobile_pairings") == MAX_ACTIVE_PAIRINGS


def test_access_token_expires_and_device_revocation_is_immediate(db, mobile_auth):
    service, clock = mobile_auth
    pairing = service.create_pairing()
    credentials = service.redeem_pairing(pairing["pairing_secret"], "Android")

    device = service.authenticate_access_token(credentials["access_token"])
    assert device.id == credentials["device"]["id"]
    assert device.name == "Android"

    clock.advance(ACCESS_TTL + timedelta(seconds=1))
    with pytest.raises(InvalidCredential):
        service.authenticate_access_token(credentials["access_token"])

    # Revocation also invalidates a newly issued access token immediately.
    fresh_pairing = service.create_pairing()
    second = service.redeem_pairing(fresh_pairing["pairing_secret"], "iPhone")
    assert service.revoke_device(second["device"]["id"]) is True
    with pytest.raises(InvalidCredential):
        service.authenticate_access_token(second["access_token"])

    assert service.revoke_device("unknown-device") is False


def test_refresh_rotation_and_replay_revoke_the_entire_device(db, mobile_auth):
    service, _ = mobile_auth
    pairing = service.create_pairing()
    initial = service.redeem_pairing(pairing["pairing_secret"], "iPhone")

    rotated = service.rotate_refresh_token(initial["refresh_token"])
    assert rotated["access_token"] != initial["access_token"]
    assert rotated["refresh_token"] != initial["refresh_token"]
    assert service.authenticate_access_token(rotated["access_token"]).id == (
        initial["device"]["id"]
    )

    with pytest.raises(RefreshReplayDetected):
        service.rotate_refresh_token(initial["refresh_token"])

    device = next(
        item
        for item in service.list_devices()
        if item["id"] == initial["device"]["id"]
    )
    assert device["revoked_at"] is not None

    with pytest.raises(InvalidCredential):
        service.authenticate_access_token(rotated["access_token"])

    revoked_tokens = db.query(
        "SELECT revoked_at FROM mobile_tokens WHERE device_id = ?",
        (initial["device"]["id"],),
    )
    assert len(revoked_tokens) == 4
    assert all(row["revoked_at"] is not None for row in revoked_tokens)


def test_unknown_refresh_token_does_not_create_a_device(db, mobile_auth):
    service, _ = mobile_auth

    with pytest.raises(InvalidCredential):
        service.rotate_refresh_token("not-a-real-refresh-token")

    assert db.scalar("SELECT COUNT(*) FROM mobile_devices") == 0
    assert db.scalar("SELECT COUNT(*) FROM mobile_tokens") == 0
