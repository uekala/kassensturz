"""App-Optionen aus /data/options.json (von Home Assistant gepflegt)."""
from __future__ import annotations

import json
import os

from .db import DATA_DIR

DEFAULTS = {
    "fints_product_id": "",
    "sync_time": "06:30",
    "sensors": True,
    "notify_service": "",
    "notify_new_transactions": True,
    "warn_threshold": 200,
    "cancellation_reminder_days": "45,21,7",
    "import_folder": "/share/kassensturz",
    "trusted_proxies": "",
    "mobile_client_networks": "",
    "mobile_server_url": "",
}

VERSION = "0.3.11"


def load() -> dict:
    opts = dict(DEFAULTS)
    try:
        opts.update(json.loads((DATA_DIR / "options.json").read_text("utf-8")))
    except (OSError, ValueError):
        pass
    if os.environ.get("KASSENSTURZ_FINTS_PRODUCT_ID"):
        opts["fints_product_id"] = os.environ["KASSENSTURZ_FINTS_PRODUCT_ID"]
    return opts


def network_security_settings() -> dict[str, str]:
    """Read proxy/client CIDRs from HA app options or standalone environment."""
    opts = load()
    settings: dict[str, str] = {}
    for option_name, env_name in (
        ("trusted_proxies", "KASSENSTURZ_TRUSTED_PROXIES"),
        ("mobile_client_networks", "KASSENSTURZ_MOBILE_CLIENT_NETWORKS"),
    ):
        value = os.environ[env_name] if env_name in os.environ else opts.get(option_name, "")
        if not isinstance(value, str):
            raise ValueError(f"{option_name} must be a comma-separated string of IPs/CIDRs.")
        settings[option_name] = value
    return settings


def cancellation_reminder_days() -> list[int]:
    """Return configured reminder offsets, falling back safely to the defaults."""
    raw = load().get("cancellation_reminder_days", DEFAULTS["cancellation_reminder_days"])
    if not isinstance(raw, str):
        return [7, 21, 45]
    try:
        values = [int(part.strip()) for part in raw.split(",")]
    except (TypeError, ValueError):
        return [7, 21, 45]
    values = sorted({value for value in values if 1 <= value <= 365})
    return values if values else [7, 21, 45]
