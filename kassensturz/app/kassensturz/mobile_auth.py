"""Secure device pairing and session lifecycle for the local mobile API.

This module deliberately contains no HTTP routes. A listener must not be enabled
until transport security, rate limiting, administration authorization and the
complete mobile DTO boundary are implemented and tested.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .db import Database


PAIRING_TTL = timedelta(minutes=5)
ACCESS_TTL = timedelta(minutes=10)
REFRESH_TTL = timedelta(days=30)
# A client whose refresh response got lost (connection drop) may present the
# just-replaced refresh token exactly once more within this window, counted
# from the first replacement, as long as the successor token was never used.
# The window equals the lifetime of the access token that was lost with it.
REFRESH_RETRY_GRACE = ACCESS_TTL
# Expired token rows are kept this long (so a late reuse is still recognised
# as "expired" rather than "unknown") and then deleted on the next rotation.
EXPIRED_TOKEN_RETENTION = timedelta(days=1)
MAX_ACTIVE_PAIRINGS = 3
MAX_DEVICE_NAME_LENGTH = 64


class MobileAuthError(Exception):
    """Base class for errors safe to map to generic API responses."""


class PairingRejected(MobileAuthError):
    """A pairing secret was unknown, expired or already consumed."""


class PairingLimitReached(MobileAuthError):
    """Too many unconsumed pairing secrets are already active."""


class InvalidCredential(MobileAuthError):
    """A token is invalid, expired, revoked or belongs to a revoked device."""


class RefreshReplayDetected(InvalidCredential):
    """A previously rotated refresh token was presented again."""


@dataclass(frozen=True)
class MobileDevice:
    id: str
    name: str


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Mobile authentication clock must be timezone-aware.")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds")


def _parse_stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _utc(parsed)


def _opaque_secret() -> str:
    # token_urlsafe(32) encodes 32 CSPRNG bytes (256 bits) without padding.
    return secrets.token_urlsafe(32)


def _typed_hash(kind: str, value: str) -> str:
    if kind not in {"pairing", "access", "refresh"}:
        raise ValueError("Unsupported mobile secret type.")
    if not isinstance(value, str) or not value:
        raise ValueError("Mobile secret must be a non-empty string.")
    prefix = f"kassensturz:{kind}:v1:".encode("ascii")
    return hashlib.sha256(prefix + value.encode("utf-8")).hexdigest()


def _validate_device_name(value: str) -> str:
    if not isinstance(value, str):
        raise PairingRejected("Pairing could not be completed.")
    name = value.strip()
    if (
        not name
        or len(name) > MAX_DEVICE_NAME_LENGTH
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
    ):
        raise PairingRejected("Pairing could not be completed.")
    return name


class MobileAuthService:
    """Database-backed pairing, token rotation and device revocation."""

    def __init__(
        self,
        db: Database,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._db = db
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        return _utc(self._clock())

    def create_pairing(self) -> dict:
        """Create a five-minute pairing secret; the raw value is returned once."""
        now = self._now()
        created_at = _stamp(now)
        expires_at = _stamp(now + PAIRING_TTL)
        secret = _opaque_secret()

        with self._db.tx(immediate=True):
            self._db.execute(
                "DELETE FROM mobile_pairings WHERE expires_at <= ? OR consumed_at IS NOT NULL",
                (created_at,),
            )
            active = self._db.scalar(
                "SELECT COUNT(*) FROM mobile_pairings "
                "WHERE consumed_at IS NULL AND expires_at > ?",
                (created_at,),
            )
            if active >= MAX_ACTIVE_PAIRINGS:
                raise PairingLimitReached("Too many active pairing requests.")

            self._db.insert(
                "mobile_pairings",
                {
                    "secret_hash": _typed_hash("pairing", secret),
                    "created_at": created_at,
                    "expires_at": expires_at,
                    "consumed_at": None,
                },
            )

        return {"pairing_secret": secret, "expires_at": expires_at}

    def redeem_pairing(self, pairing_secret: str, device_name: str) -> dict:
        """Atomically consume a pairing secret and issue a device token pair."""
        name = _validate_device_name(device_name)
        now = self._now()
        now_text = _stamp(now)

        try:
            pairing_hash = _typed_hash("pairing", pairing_secret)
        except ValueError as exc:
            raise PairingRejected("Pairing could not be completed.") from exc

        device_id = secrets.token_urlsafe(18)
        access_token = _opaque_secret()
        refresh_token = _opaque_secret()
        access_hash = _typed_hash("access", access_token)
        refresh_hash = _typed_hash("refresh", refresh_token)

        with self._db.tx(immediate=True):
            pairing = self._db.one(
                "SELECT id, expires_at, consumed_at FROM mobile_pairings "
                "WHERE secret_hash = ?",
                (pairing_hash,),
            )
            if (
                pairing is None
                or pairing["consumed_at"] is not None
                or _parse_stamp(pairing["expires_at"]) <= now
            ):
                raise PairingRejected("Pairing could not be completed.")

            consumed = self._db.execute_count(
                "UPDATE mobile_pairings SET consumed_at = ? "
                "WHERE id = ? AND consumed_at IS NULL AND expires_at > ?",
                (now_text, pairing["id"], now_text),
            )
            if consumed != 1:
                raise PairingRejected("Pairing could not be completed.")

            self._db.insert(
                "mobile_devices",
                {"id": device_id, "name": name, "created_at": now_text},
            )
            self._insert_token(
                access_hash, device_id, "access", now, ACCESS_TTL
            )
            self._insert_token(
                refresh_hash, device_id, "refresh", now, REFRESH_TTL
            )

        return {
            "device": {"id": device_id, "name": name},
            **self._token_response(access_token, refresh_token),
        }

    def authenticate_access_token(self, access_token: str) -> MobileDevice:
        """Validate a bearer token and update the device's last-used timestamp."""
        try:
            token_hash = _typed_hash("access", access_token)
        except ValueError as exc:
            raise InvalidCredential("Authentication required.") from exc

        now = self._now()
        now_text = _stamp(now)
        with self._db.tx(immediate=True):
            row = self._db.one(
                """
                SELECT t.device_id, t.expires_at, t.revoked_at,
                       d.name, d.revoked_at AS device_revoked_at
                FROM mobile_tokens AS t
                JOIN mobile_devices AS d ON d.id = t.device_id
                WHERE t.token_hash = ? AND t.token_type = 'access'
                """,
                (token_hash,),
            )
            if (
                row is None
                or row["revoked_at"] is not None
                or row["device_revoked_at"] is not None
                or _parse_stamp(row["expires_at"]) <= now
            ):
                raise InvalidCredential("Authentication required.")

            self._db.update(
                "mobile_devices",
                "id",
                row["device_id"],
                {"last_used_at": now_text},
            )
            return MobileDevice(id=row["device_id"], name=row["name"])

    def rotate_refresh_token(self, refresh_token: str) -> dict:
        """Rotate a refresh token.

        A replaced token may be presented exactly once more within
        ``REFRESH_RETRY_GRACE`` of its first replacement, and only while the
        successor is unused: that is a client whose response got lost. The
        unused successor is retired and chained to the new token. Every other
        reuse revokes the device with all its tokens – a further presentation
        of the replaced token, a presentation after the window, and any
        presentation of a successor that was retired by a retry (two parties
        then hold tokens of the same device).
        """
        try:
            old_hash = _typed_hash("refresh", refresh_token)
        except ValueError as exc:
            raise InvalidCredential("Authentication required.") from exc

        now = self._now()
        now_text = _stamp(now)
        replay_detected = False
        response = None

        with self._db.tx(immediate=True):
            self._purge_expired_tokens(now)
            row = self._db.one(
                """
                SELECT t.device_id, t.expires_at, t.revoked_at,
                       t.replaced_by_hash, d.revoked_at AS device_revoked_at
                FROM mobile_tokens AS t
                JOIN mobile_devices AS d ON d.id = t.device_id
                WHERE t.token_hash = ? AND t.token_type = 'refresh'
                """,
                (old_hash,),
            )
            if row is None or row["device_revoked_at"] is not None:
                raise InvalidCredential("Authentication required.")

            if row["revoked_at"] is not None:
                # Tokens are only revoked individually when a retry retires an
                # unused successor; that successor is chained to its
                # replacement. Seeing it here means a second party holds it.
                if row["replaced_by_hash"] is None:
                    raise InvalidCredential("Authentication required.")
                self._revoke_device_in_tx(row["device_id"], now_text)
                replay_detected = True
            elif row["replaced_by_hash"] is not None:
                successor = self._db.one(
                    "SELECT token_hash, created_at, revoked_at, replaced_by_hash "
                    "FROM mobile_tokens WHERE token_hash = ? AND token_type = 'refresh'",
                    (row["replaced_by_hash"],),
                )
                lost_response_retry = (
                    successor is not None
                    and successor["revoked_at"] is None
                    and successor["replaced_by_hash"] is None
                    and timedelta(0)
                    <= now - _parse_stamp(successor["created_at"])
                    <= REFRESH_RETRY_GRACE
                    and _parse_stamp(row["expires_at"]) > now
                )
                if not lost_response_retry:
                    # Commit the revocation before raising the replay error.
                    self._revoke_device_in_tx(row["device_id"], now_text)
                    replay_detected = True
                else:
                    access_token = _opaque_secret()
                    new_refresh_token = _opaque_secret()
                    new_refresh_hash = _typed_hash("refresh", new_refresh_token)
                    # Retire the pair that never reached the client. The
                    # replaced token keeps pointing at this retired successor,
                    # so a further presentation finds it used up: the retry
                    # works once and cannot move the window.
                    self._db.execute(
                        "UPDATE mobile_tokens SET revoked_at = ? "
                        "WHERE device_id = ? AND token_type = 'access' "
                        "AND revoked_at IS NULL AND created_at = ?",
                        (now_text, row["device_id"], successor["created_at"]),
                    )
                    retired = self._db.execute_count(
                        "UPDATE mobile_tokens SET revoked_at = ?, replaced_by_hash = ? "
                        "WHERE token_hash = ? AND revoked_at IS NULL "
                        "AND replaced_by_hash IS NULL",
                        (now_text, new_refresh_hash, successor["token_hash"]),
                    )
                    if retired != 1:
                        raise InvalidCredential("Authentication required.")
                    response = self._issue_pair(
                        row["device_id"], access_token, new_refresh_token, now
                    )
            elif _parse_stamp(row["expires_at"]) <= now:
                raise InvalidCredential("Authentication required.")
            else:
                access_token = _opaque_secret()
                new_refresh_token = _opaque_secret()
                changed = self._db.execute_count(
                    "UPDATE mobile_tokens SET replaced_by_hash = ? "
                    "WHERE token_hash = ? AND replaced_by_hash IS NULL "
                    "AND revoked_at IS NULL",
                    (_typed_hash("refresh", new_refresh_token), old_hash),
                )
                if changed != 1:
                    raise InvalidCredential("Authentication required.")
                response = self._issue_pair(
                    row["device_id"], access_token, new_refresh_token, now
                )

        if replay_detected:
            raise RefreshReplayDetected("Authentication required.")
        return response

    def _issue_pair(
        self,
        device_id: str,
        access_token: str,
        refresh_token: str,
        now: datetime,
    ) -> dict:
        self._insert_token(
            _typed_hash("access", access_token), device_id, "access", now, ACCESS_TTL
        )
        self._insert_token(
            _typed_hash("refresh", refresh_token), device_id, "refresh", now, REFRESH_TTL
        )
        self._db.update(
            "mobile_devices", "id", device_id, {"last_used_at": _stamp(now)}
        )
        return self._token_response(access_token, refresh_token)

    def _revoke_device_in_tx(self, device_id: str, now_text: str) -> None:
        self._db.update("mobile_devices", "id", device_id, {"revoked_at": now_text})
        self._db.execute(
            "UPDATE mobile_tokens SET revoked_at = ? "
            "WHERE device_id = ? AND revoked_at IS NULL",
            (now_text, device_id),
        )

    def _purge_expired_tokens(self, now: datetime) -> None:
        """Drop token rows that expired longer ago than the retention period."""
        self._db.execute(
            "DELETE FROM mobile_tokens WHERE expires_at < ?",
            (_stamp(now - EXPIRED_TOKEN_RETENTION),),
        )

    def revoke_device(self, device_id: str) -> bool:
        """Revoke a device and all of its credentials in one transaction."""
        now_text = _stamp(self._now())
        with self._db.tx(immediate=True):
            device = self._db.one(
                "SELECT id FROM mobile_devices WHERE id = ?", (device_id,)
            )
            if device is None:
                return False

            self._db.update(
                "mobile_devices",
                "id",
                device_id,
                {"revoked_at": now_text},
            )
            self._db.execute(
                "UPDATE mobile_tokens SET revoked_at = ? "
                "WHERE device_id = ? AND revoked_at IS NULL",
                (now_text, device_id),
            )
        return True

    def list_devices(self) -> list[dict]:
        """Return device metadata only; credential material is never included."""
        return self._db.query(
            "SELECT id, name, created_at, last_used_at, revoked_at "
            "FROM mobile_devices ORDER BY created_at DESC, id ASC"
        )

    def _insert_token(
        self,
        token_hash: str,
        device_id: str,
        token_type: str,
        now: datetime,
        ttl: timedelta,
    ) -> None:
        self._db.insert(
            "mobile_tokens",
            {
                "token_hash": token_hash,
                "device_id": device_id,
                "token_type": token_type,
                "created_at": _stamp(now),
                "expires_at": _stamp(now + ttl),
            },
        )

    @staticmethod
    def _token_response(access_token: str, refresh_token: str) -> dict:
        return {
            "access_token": access_token,
            "access_expires_in": int(ACCESS_TTL.total_seconds()),
            "refresh_token": refresh_token,
            "refresh_expires_in": int(REFRESH_TTL.total_seconds()),
            "token_type": "Bearer",
        }
