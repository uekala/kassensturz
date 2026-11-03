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

echo "Android- und iOS-Projektdateien wurden erstellt."
echo "Nächster Schritt: flutter pub get && flutter test"
