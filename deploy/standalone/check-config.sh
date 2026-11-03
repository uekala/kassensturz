#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

docker compose --file "$COMPOSE_FILE" config --quiet

docker compose --file "$COMPOSE_FILE" config --format json |
  python3 -c '
import json
import sys

config = json.load(sys.stdin)
service = config.get("services", {}).get("kassensturz")
if not service:
    raise SystemExit("ERROR: service kassensturz is missing")

environment = service.get("environment") or {}
if isinstance(environment, list):
    environment = dict(item.split("=", 1) for item in environment if "=" in item)

checks = {
    "host networking is required": service.get("network_mode") == "host",
    "KASSENSTURZ_HOST must remain 127.0.0.1": environment.get("KASSENSTURZ_HOST") == "127.0.0.1",
    "no published ports may be configured": not service.get("ports"),
    "container must run read-only": service.get("read_only") is True,
    "all Linux capabilities must be dropped": "ALL" in (service.get("cap_drop") or []),
    "no-new-privileges must be enabled": "no-new-privileges:true" in (service.get("security_opt") or []),
    "privileged container mode is forbidden": service.get("privileged") is not True,
}

failed = [message for message, passed in checks.items() if not passed]
for message, passed in checks.items():
    print(("OK: " if passed else "FAIL: ") + message)

if failed:
    raise SystemExit(1)
'
