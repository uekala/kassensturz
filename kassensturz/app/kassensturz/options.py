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
    "warn_threshold": 200,
    "import_folder": "/share/kassensturz",
}

VERSION = "0.2.0"


def load() -> dict:
    opts = dict(DEFAULTS)
    try:
        opts.update(json.loads((DATA_DIR / "options.json").read_text("utf-8")))
    except (OSError, ValueError):
        pass
    if os.environ.get("KASSENSTURZ_FINTS_PRODUCT_ID"):
        opts["fints_product_id"] = os.environ["KASSENSTURZ_FINTS_PRODUCT_ID"]
    return opts
