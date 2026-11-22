#!/usr/bin/env python3
"""Die von `flutter create` erzeugte AndroidManifest.xml härten.

* Deklariert die Berechtigung INTERNET ausdrücklich. Die Vorlage von Flutter fügt
  sie nur den Debug- und Profile-Manifesten hinzu; ein Release-Build hinge sonst
  davon ab, dass zufällig ein Plugin sie anfordert.
* Schaltet die automatische Sicherung von Android ab. Die Sitzung liegt im sicheren
  Speicher auf Keystore-Basis; eine wiederhergestellte Kopie lässt sich auf einem anderen
  Gerät nicht entschlüsseln, und Zugangsdaten gehören nicht in eine Cloud-Sicherung.

* Nimmt alle App-Daten von Cloud-Sicherung und Geräteumzug aus, unter
  Android 12 und neuer, wo ``allowBackup`` allein den Umzug auf ein neues
  Handy nicht mehr abdeckt.

Das Skript ist idempotent und scheitert laut, wenn sich die Vorlage auf eine Weise
geändert hat, die es nicht versteht.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

INTERNET = '<uses-permission android:name="android.permission.INTERNET"/>'
DEFAULT_MANIFEST = Path("android/app/src/main/AndroidManifest.xml")
RULES_NAME = "kassensturz_data_extraction_rules"
RULES_XML = """<?xml version="1.0" encoding="utf-8"?>
<data-extraction-rules>
    <cloud-backup>
        <exclude domain="root" />
        <exclude domain="file" />
        <exclude domain="database" />
        <exclude domain="sharedpref" />
        <exclude domain="external" />
    </cloud-backup>
    <device-transfer>
        <exclude domain="root" />
        <exclude domain="file" />
        <exclude domain="database" />
        <exclude domain="sharedpref" />
        <exclude domain="external" />
    </device-transfer>
</data-extraction-rules>
"""


class ManifestError(RuntimeError):
    """Das Manifest sieht nicht wie die Flutter-Vorlage aus."""


def harden(manifest: str) -> str:
    """Das Manifest mit Berechtigung INTERNET und abgeschalteten Sicherungen zurückgeben."""
    if manifest.count("<application") != 1:
        raise ManifestError("Erwartet genau ein <application>-Element.")

    if not re.search(
        r'<uses-permission\s+android:name="android\.permission\.INTERNET"\s*/>',
        manifest,
    ):
        opening = re.search(r"<manifest\b[^>]*>", manifest, re.DOTALL)
        if opening is None:
            raise ManifestError("Kein <manifest>-Element gefunden.")
        manifest = (
            manifest[: opening.end()]
            + "\n    "
            + INTERNET
            + manifest[opening.end() :]
        )

    manifest, replaced = re.subn(
        r'android:allowBackup="(?:true|false)"',
        'android:allowBackup="false"',
        manifest,
    )
    if replaced > 1:
        raise ManifestError("android:allowBackup ist mehrfach gesetzt.")
    if replaced == 0:
        manifest = manifest.replace(
            "<application",
            '<application\n        android:allowBackup="false"',
            1,
        )

    manifest, replaced = re.subn(
        r'android:fullBackupContent="[^"]*"',
        'android:fullBackupContent="false"',
        manifest,
    )
    if replaced == 0:
        manifest = manifest.replace(
            "<application",
            '<application\n        android:fullBackupContent="false"',
            1,
        )

    manifest, replaced = re.subn(
        r'android:dataExtractionRules="[^"]*"',
        f'android:dataExtractionRules="@xml/{RULES_NAME}"',
        manifest,
    )
    if replaced == 0:
        manifest = manifest.replace(
            "<application",
            f'<application\n        android:dataExtractionRules="@xml/{RULES_NAME}"',
            1,
        )
    return manifest


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_MANIFEST
    if not path.is_file():
        print(f"Manifest nicht gefunden: {path}", file=sys.stderr)
        return 2
    try:
        hardened = harden(path.read_text(encoding="utf-8"))
    except ManifestError as error:
        print(f"Manifest nicht angepasst: {error}", file=sys.stderr)
        return 1
    path.write_text(hardened, encoding="utf-8")
    rules = path.parent / "res" / "xml" / f"{RULES_NAME}.xml"
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(RULES_XML, encoding="utf-8")
    print("AndroidManifest: INTERNET-Berechtigung gesetzt, Backup deaktiviert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
