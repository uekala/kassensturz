#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$ROOT/kassensturz/app"
ADDON_TEMPLATE="$ROOT/deploy/home-assistant-green/test-addon"
if (( $# > 1 )); then
  echo "Usage: $0 [destination-under-dist-or-RUNNER_TEMP]" >&2
  exit 2
fi

if (( $# == 0 )); then
  DEST="$ROOT/dist/kassensturz-mobile-test"
else
  DEST="$(realpath -m "$1")"
fi
ROOT_REAL="$(realpath "$ROOT")"
RUNNER_TEMP_REAL="$(realpath -m "${RUNNER_TEMP:-/tmp}")"

case "$DEST" in
  "$ROOT_REAL/dist/kassensturz-mobile-test"|"$RUNNER_TEMP_REAL"/*)
    ;;
  *)
    echo "Refusing destination outside repository dist/ or RUNNER_TEMP: $DEST" >&2
    exit 2
    ;;
esac

if [[ ! -f "$SOURCE/requirements.txt" || ! -f "$ADDON_TEMPLATE/config.yaml" ]]; then
  echo "Source application or test add-on template is missing." >&2
  exit 2
fi

rm -rf "$DEST"
mkdir -p "$DEST/app"
cp "$ADDON_TEMPLATE/config.yaml" "$DEST/config.yaml"
cp "$ADDON_TEMPLATE/Dockerfile" "$DEST/Dockerfile"
cp -a "$SOURCE/." "$DEST/app/"

cat > "$DEST/TEST-INSTANCE.txt" <<'EOF'
Kassensturz Mobile Test — isolated Home Assistant local add-on

Slug: kassensturz-mobile-test
Persistent data: dedicated Home Assistant app data volume (/data)
Bank background jobs: disabled
Sensors: disabled
Host port mapping: disabled by default
Tailscale service: not configured
mobile_server_url: empty
trusted_proxies: empty
mobile_client_networks: empty

This is a separate test instance. Do not copy production secrets or the
production SQLite database into this folder. Install and start manually.
EOF

echo "Prepared isolated Home Assistant test add-on:"
echo "  $DEST"
echo "Files:"
find "$DEST" -maxdepth 2 -type f | sort
