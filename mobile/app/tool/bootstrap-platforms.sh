#!/usr/bin/env bash
set -euo pipefail

if ! command -v flutter >/dev/null 2>&1; then
  echo "Flutter SDK nicht gefunden. Installiere zuerst den Flutter Stable Channel." >&2
  exit 1
fi

if [[ -d android || -d ios ]]; then
  echo "Android- oder iOS-Projektdateien existieren bereits. Bootstrap wird aus Sicherheitsgründen abgebrochen." >&2
  echo "Prüfe die vorhandenen Plattformdateien und führe flutter create nicht erneut darüber aus." >&2
  exit 1
fi

flutter create \
  --project-name kassensturz_mobile \
  --org de.uekala.kassensturz \
  --platforms android,ios \
  .

python3 - <<'PY'
from pathlib import Path
import plistlib
import re

info_path = Path("ios/Runner/Info.plist")
with info_path.open("rb") as source:
    info = plistlib.load(source)
info["NSCameraUsageDescription"] = (
    "Kassensturz verwendet die Kamera, um den einmaligen Geräte-Pairing-QR-Code zu scannen."
)
info["NSFaceIDUsageDescription"] = (
    "Kassensturz verwendet Face ID, um die App zu entsperren."
)
with info_path.open("wb") as target:
    plistlib.dump(info, target, fmt=plistlib.FMT_XML, sort_keys=False)

# App-Zeichen: ein K, dessen oberer Arm ein Pfeil nach oben ist, auf dem Blau der App.
android = Path("android/app/src/main")
manifest_path = android / "AndroidManifest.xml"
manifest = manifest_path.read_text(encoding="utf-8")
manifest, replacements = re.subn(
    r'android:icon="[^"]+"',
    'android:icon="@mipmap/ic_launcher"',
    manifest,
    count=1,
)
if replacements != 1:
    raise SystemExit("Das Standard-App-Icon in AndroidManifest.xml wurde nicht gefunden.")
manifest_path.write_text(manifest, encoding="utf-8")

# Alte Farbressource aus früheren Läufen entfernen, damit sie nicht liegen bleibt.
(android / "res/values/ic_launcher_colors.xml").unlink(missing_ok=True)

MARK = """    <!-- Stamm des K -->
    <path
        android:fillColor="{main}"
        android:pathData="M33,31 a5.5,5.5 0 0 1 11,0 v46 a5.5,5.5 0 0 1 -11,0 Z" />
    <!-- Unterer Arm -->
    <path
        android:strokeColor="{soft}"
        android:strokeWidth="10"
        android:strokeLineCap="round"
        android:pathData="M53,55 L70,77" />
    <!-- Oberer Arm als Pfeil nach oben -->
    <path
        android:strokeColor="{main}"
        android:strokeWidth="10"
        android:strokeLineCap="round"
        android:pathData="M50,58 L67,39" />
    <path
        android:fillColor="{main}"
        android:pathData="M58,29.5 H76 a3,3 0 0 1 3,3 V50.5 a3,3 0 0 1 -5.1,2.1 L55.9,34.6 a3,3 0 0 1 2.1,-5.1 Z" />
"""
VECTOR = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
{mark}</vector>
"""

drawable = android / "res/drawable"
drawable.mkdir(parents=True, exist_ok=True)
(drawable / "ic_launcher_foreground.xml").write_text(
    VECTOR.format(mark=MARK.format(main="#FFFFFF", soft="#A9C1FF")), encoding="utf-8")
# Einfarbige Fassung für die thematischen Symbole ab Android 13.
(drawable / "ic_launcher_monochrome.xml").write_text(
    VECTOR.format(mark=MARK.format(main="#FFFFFF", soft="#99FFFFFF")), encoding="utf-8")
(drawable / "ic_launcher_background.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <gradient
        android:angle="315"
        android:startColor="#3D6BFF"
        android:endColor="#1535B5" />
</shape>
""", encoding="utf-8")

adaptive = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
    <monochrome android:drawable="@drawable/ic_launcher_monochrome" />
</adaptive-icon>
"""
for qualifier in ("mipmap-anydpi-v26",):
    resource_dir = android / "res" / qualifier
    resource_dir.mkdir(parents=True, exist_ok=True)
    (resource_dir / "ic_launcher.xml").write_text(adaptive, encoding="utf-8")
    (resource_dir / "ic_launcher_round.xml").write_text(adaptive, encoding="utf-8")
PY

python3 "$(dirname "${BASH_SOURCE[0]}")/configure-android-manifest.py"
python3 "$(dirname "${BASH_SOURCE[0]}")/configure-android-app-lock.py"

echo "Android- und iOS-Projektdateien wurden erstellt."
echo "Das Kassensturz-App-Icon wurde eingerichtet."
echo "Nächster Schritt: flutter pub get && flutter test"
