"""Locally stored banking credentials encrypted with AES-256-GCM."""
from __future__ import annotations

import base64
import json
import os
import secrets
import stat
import threading
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .db import DATA_DIR

_PATH = DATA_DIR / "secrets.json"
_KEY_PATH = DATA_DIR / "secrets.key"
_lock = threading.Lock()

_FORMAT = "kassensturz-encrypted-secrets"
_VERSION = 1
_AAD = b"kassensturz-secrets:v1"
_KEY_BYTES = 32
_NONCE_BYTES = 12


class SecretsStoreError(RuntimeError):
    """Stored secrets cannot safely be read or decrypted."""


class SecretsKeyError(SecretsStoreError):
    """The configured installation key is invalid or unavailable."""


class SecretsIntegrityError(SecretsStoreError):
    """Encrypted secret data failed authentication or validation."""


def _configured_key() -> bytes | None:
    value = os.environ.get("KASSENSTURZ_MASTER_KEY")
    if value is None or not value.strip():
        return None
    try:
        key = bytes.fromhex(value.strip())
    except ValueError as exc:
        raise SecretsKeyError("KASSENSTURZ_MASTER_KEY muss aus genau 64 Hex-Zeichen bestehen.") from exc
    if len(key) != _KEY_BYTES:
        raise SecretsKeyError("KASSENSTURZ_MASTER_KEY muss einen 256-Bit-Schlüssel enthalten.")
    return key


def _read_key_file() -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(_KEY_PATH, flags)
    except OSError as exc:
        raise SecretsKeyError(
            "Der lokale Verschlüsselungsschlüssel fehlt oder kann nicht sicher geöffnet werden. "
            "Stelle secrets.key wieder her oder setze KASSENSTURZ_MASTER_KEY."
        ) from exc

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SecretsKeyError("Der Verschlüsselungsschlüssel ist keine reguläre Datei.")
        os.fchmod(fd, 0o600)
        key = os.read(fd, _KEY_BYTES + 1)
    finally:
        os.close(fd)

    if len(key) != _KEY_BYTES:
        raise SecretsKeyError("Die Datei secrets.key enthält keinen gültigen 256-Bit-Schlüssel.")
    return key


def _create_key_file() -> bytes:
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_bytes(_KEY_BYTES)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(_KEY_PATH, flags, 0o600)
    except FileExistsError:
        return _read_key_file()
    except OSError as exc:
        raise SecretsKeyError("Der lokale Verschlüsselungsschlüssel konnte nicht angelegt werden.") from exc

    try:
        os.fchmod(fd, 0o600)
        view = memoryview(key)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    except Exception:
        try:
            os.unlink(_KEY_PATH)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)
    return key


def _master_key(*, create: bool = True) -> bytes:
    configured = _configured_key()
    if configured is not None:
        return configured
    if _KEY_PATH.exists():
        return _read_key_file()
    if not create:
        raise SecretsKeyError("Der lokale Verschlüsselungsschlüssel fehlt.")
    try:
        return _create_key_file()
    except SecretsKeyError:
        raise


def _decode_envelope(envelope: dict) -> dict:
    if envelope.get("format") != _FORMAT or envelope.get("version") != _VERSION:
        raise SecretsIntegrityError("Das Format der verschlüsselten Geheimnisdatei wird nicht unterstützt.")
    try:
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise SecretsIntegrityError("Die verschlüsselte Geheimnisdatei ist beschädigt.") from exc
    if len(nonce) != _NONCE_BYTES or len(ciphertext) < 16:
        raise SecretsIntegrityError("Die verschlüsselte Geheimnisdatei ist unvollständig.")

    try:
        plaintext = AESGCM(_master_key(create=False)).decrypt(nonce, ciphertext, _AAD)
        data = json.loads(plaintext.decode("utf-8"))
    except SecretsKeyError:
        raise
    except (InvalidTag, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise SecretsIntegrityError(
            "Die Geheimnisse konnten nicht entschlüsselt werden. Prüfe den Installationsschlüssel und die Datensicherung."
        ) from exc
    if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
        raise SecretsIntegrityError("Der Inhalt der Geheimnisdatei hat ein ungültiges Format.")
    return data


def _load() -> dict:
    try:
        raw = _PATH.read_text("utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SecretsStoreError("Die lokale Geheimnisdatei kann nicht gelesen werden.") from exc

    try:
        stored = json.loads(raw)
    except ValueError as exc:
        raise SecretsIntegrityError("Die lokale Geheimnisdatei enthält kein gültiges JSON.") from exc

    if not isinstance(stored, dict):
        raise SecretsIntegrityError("Die lokale Geheimnisdatei hat ein ungültiges Format.")

    if stored.get("format") == _FORMAT:
        return _decode_envelope(stored)

    # Backward-compatible migration: a valid legacy plaintext dictionary is
    # immediately rewritten as an authenticated AES-GCM envelope on first read.
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in stored.items()):
        raise SecretsIntegrityError("Die bisherige Geheimnisdatei enthält ungültige Werte.")
    _save(stored)
    return stored


def _save(data: dict) -> None:
    if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
        raise SecretsStoreError("Es können nur Zeichenketten als Geheimnisse gespeichert werden.")

    _PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = _master_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, _AAD)
    envelope = {
        "format": _FORMAT,
        "version": _VERSION,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    encoded = json.dumps(envelope, separators=(",", ":"))
    tmp = _PATH.with_suffix(".tmp")
    fd = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(tmp, flags, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, _PATH)
        try:
            dir_fd = os.open(_PATH.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        if fd is not None:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def get_pin(connection_id: int) -> str | None:
    with _lock:
        return _load().get(str(connection_id))


def set_pin(connection_id: int, pin: str) -> None:
    with _lock:
        data = _load()
        data[str(connection_id)] = pin
        _save(data)


def delete_pin(connection_id: int) -> None:
    with _lock:
        data = _load()
        if data.pop(str(connection_id), None) is not None:
            _save(data)


def has_pin(connection_id: int) -> bool:
    return get_pin(connection_id) is not None


def get_secret(name: str) -> str | None:
    with _lock:
        return _load().get(f"secret:{name}")


def set_secret(name: str, value: str) -> None:
    with _lock:
        data = _load()
        data[f"secret:{name}"] = value
        _save(data)


def delete_secret(name: str) -> None:
    with _lock:
        data = _load()
        if data.pop(f"secret:{name}", None) is not None:
            _save(data)
