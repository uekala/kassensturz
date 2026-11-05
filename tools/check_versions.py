#!/usr/bin/env python3
"""Check the Home Assistant add-on and Flutter app version metadata."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
FLUTTER_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:\+\d+)?$")


def read_value(path: Path, key: str) -> str:
    match = re.search(
        rf"^{re.escape(key)}:\s*['\"]?([^'\"\s]+)",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise SystemExit(f"Missing {key}: in {path.relative_to(ROOT)}")
    return match.group(1)


addon_version = read_value(ROOT / "kassensturz" / "config.yaml", "version")
if not SEMVER.fullmatch(addon_version):
    raise SystemExit(f"Invalid Home Assistant add-on version: {addon_version!r}")

changelog = (ROOT / "kassensturz" / "CHANGELOG.md").read_text(encoding="utf-8")
headings = re.findall(r"^##\s+(\d+\.\d+\.\d+)(?:\s|$)", changelog, re.MULTILINE)
if not headings or headings[0] != addon_version:
    latest = headings[0] if headings else "no version heading"
    raise SystemExit(
        f"Add-on changelog starts at {latest}, config.yaml says {addon_version}"
    )

mobile_version = read_value(ROOT / "mobile" / "app" / "pubspec.yaml", "version")
if not FLUTTER_VERSION.fullmatch(mobile_version):
    raise SystemExit(f"Invalid Flutter app version: {mobile_version!r}")

print(
    f"Kassensturz add-on {addon_version} and Flutter app {mobile_version}: "
    "independent version tracks are valid."
)
