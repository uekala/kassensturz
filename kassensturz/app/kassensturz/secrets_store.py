"""Gespeicherte Banking-PINs. Liegen nur auf dem Home-Assistant-Gerät und sind von Backups ausgenommen."""
from __future__ import annotations

import json
import os
import threading

from .db import DATA_DIR

_PATH = DATA_DIR / "secrets.json"
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), "utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(_PATH)


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
