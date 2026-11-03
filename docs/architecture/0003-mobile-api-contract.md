# Mobile API contract (v1)

This contract describes the first client/server boundary. The API remains disabled by default.

## Deployment and transport

- A mobile API listener is opt-in.
- Every pairing and authenticated request uses HTTPS.
- Local LAN access is preferred; remote access uses a customer-managed VPN.
- Do not expose the service directly to the public internet.
- The mobile client connects to the customer's own server URL. There is no vendor relay.

## Pairing lifecycle

1. The owner opens the local Kassensturz administration interface.
2. The server creates a cryptographically random, single-use pairing secret.
3. The secret expires after five minutes and is shown only once (preferably as a QR code).
4. The mobile client sends the secret and a device label over HTTPS.
5. The server consumes the secret atomically and creates a separately identifiable device.
6. The owner can see and revoke each paired device from the local administration interface.

Pairing secrets must never be put in URL query strings or application logs.

## Session lifecycle

- Access credential lifetime: 10 minutes.
- Refresh credential lifetime: 30 days.
- Refresh credentials rotate after every successful refresh.
- Reuse of an already rotated refresh credential revokes the affected device session.
- Device credentials are opaque random values; only cryptographic hashes are persisted on the server.
- Device revocation invalidates all credentials for that device.

These values are initial product defaults and require security review before release.

## Initial endpoints

| Method | Path | Purpose | Authorization |
|---|---|---|---|
| POST | `/api/mobile/pairings` | Create one pairing code | Home Assistant Ingress administration |
| GET | `/api/mobile/devices` | List paired devices | Home Assistant Ingress administration |
| DELETE | `/api/mobile/devices/{id}` | Revoke a device | Home Assistant Ingress administration |
| POST | `/api/v1/pair` | Redeem pairing secret | HTTPS + one-time secret |
| POST | `/api/v1/auth/refresh` | Rotate session credentials | HTTPS + refresh credential |
| POST | `/api/v1/auth/logout` | Revoke current device | HTTPS + access credential |
| GET | `/api/v1/me` | Device identity | HTTPS + access credential |
| GET | `/api/v1/overview` | Financial dashboard | HTTPS + access credential |
| GET | `/api/v1/transactions` | Paginated transactions | HTTPS + access credential |

## Versioning and compatibility

- All new mobile endpoints live under `/api/v1`.
- Existing `/api/*` routes remain compatible with the Home Assistant web UI.
- Mobile response objects are DTOs, not direct database row dumps.
- Pagination is mandatory for list endpoints.
- A breaking API change requires a new major version prefix.

## Release gates

No financial-data endpoint may be enabled until:
- pairing secrets are single-use, short-lived and consumed atomically;
- credentials are hashed at rest, expiring, rotating and revocable;
- every financial endpoint requires device authentication;
- HTTPS is enforced by the ASGI application and verified deployment configuration;
- tests cover replay, expiry, unauthorized access and device revocation.
