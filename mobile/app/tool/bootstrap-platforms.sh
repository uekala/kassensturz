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
with info_path.open("wb") as target:
    plistlib.dump(info, target, fmt=plistlib.FMT_XML, sort_keys=False)

# Use the same evergreen palette as the Kassensturz application theme.
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

(android / "res/values").mkdir(parents=True, exist_ok=True)
(android / "res/values/ic_launcher_colors.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">#174A3E</color>
</resources>
""", encoding="utf-8")

(android / "res/drawable").mkdir(parents=True, exist_ok=True)
(android / "res/drawable/ic_launcher_foreground.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <!-- Receipt with a folded, segmented lower edge -->
    <path
        android:fillColor="#FFFFFF"
        android:pathData="M31,20 H70 C73.3,20 76,22.7 76,26 V80 L69,75 L62,80 L55,75 L48,80 L41,75 L34,80 L27,75 V26 C27,22.7 29.7,20 33,20 Z" />
    <!-- Transaction lines -->
    <path
        android:fillColor="#287A65"
        android:pathData="M37,34 H65 V38 H37 Z M37,45 H65 V49 H37 Z M37,56 H55 V60 H37 Z" />
    <!-- Mint coin, with a simple euro mark -->
    <path
        android:fillColor="#DCECE5"
        android:pathData="M72,55 A17,17 0,1 0,72 89 A17,17 0,1 0,72 55 Z" />
    <path
        android:fillColor="#174A3E"
        android:pathData="M78,64 C76,61.8 73.8,60.8 71.5,60.8 C67.8,60.8 65,63.1 63.8,66.2 H60.5 V69 H63.2 C63.1,69.5 63.1,70 63.1,70.5 C63.1,71 63.1,71.5 63.2,72 H60.5 V74.8 H63.8 C65,77.9 67.8,80.2 71.5,80.2 C73.8,80.2 76,79.2 78,77 L75.5,74.8 C74.3,76.1 73,76.8 71.4,76.8 C69.6,76.8 68.1,76.1 67.2,74.8 H73.5 V72 H66.2 C66.1,71.5 66.1,71 66.1,70.5 C66.1,70 66.1,69.5 66.2,69 H73.5 V66.2 H67.2 C68.1,64.9 69.6,64.2 71.4,64.2 C73,64.2 74.3,64.9 75.5,66.2 Z" />
</vector>
""", encoding="utf-8")

adaptive = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
"""
for qualifier in ("mipmap-anydpi-v26",):
    resource_dir = android / "res" / qualifier
    resource_dir.mkdir(parents=True, exist_ok=True)
    (resource_dir / "ic_launcher.xml").write_text(adaptive, encoding="utf-8")
    (resource_dir / "ic_launcher_round.xml").write_text(adaptive, encoding="utf-8")
PY

python3 "$(dirname "${BASH_SOURCE[0]}")/configure-android-manifest.py"

echo "Android- und iOS-Projektdateien wurden erstellt."
echo "Das Kassensturz-App-Icon wurde im Original-Theme eingerichtet."
echo "Nächster Schritt: flutter pub get && flutter test"
