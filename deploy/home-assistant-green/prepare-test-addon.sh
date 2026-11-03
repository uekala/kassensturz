#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$ROOT/kassensturz/app"
ADDON_TEMPLATE="$ROOT/deploy/home-assistant-green/test-addon"
DEST="${1:-$ROOT/dist/kassensturz-mobile-test}"

case "$DEST" in
  "$ROOT"|"$ROOT/"|"$SOURCE"|"$ADDON_TEMPLATE")
    echo "Refusing unsafe destination: $DEST" >&2
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
