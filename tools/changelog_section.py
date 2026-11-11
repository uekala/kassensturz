#!/usr/bin/env python3
"""Print the changelog section of one version, for GitHub release notes."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def section(text: str, version: str) -> str:
    match = re.search(
        rf"^##[ \t]+{re.escape(version)}(?![\d.])[^\n]*\n(.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise SystemExit(f"No changelog section for version {version}")
    return match.group(1).strip() + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: changelog_section.py CHANGELOG.md VERSION")
    sys.stdout.write(section(Path(sys.argv[1]).read_text(encoding="utf-8"), sys.argv[2]))
