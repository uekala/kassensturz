# Architecture Decision Record 0001: Local-first product architecture

- Status: Accepted as the product direction; implementation details remain subject to security review.
- Date: 2026-11-03
- Scope: Kassensturz mobile clients, Home Assistant integration and standalone deployment.

## Decision

Kassensturz will be a **local-first, single-household product**. Each customer operates one Kassensturz installation on their own Home Assistant host, NAS, mini-PC or home server. That installation is the system of record for accounts, transactions, contracts, categories, rules and forecasts.

The iOS and Android apps are clients of that installation. They connect directly over the customer's local network or a remote-access network the customer controls (for example, a VPN). Kassensturz will not operate a central service that stores customers' bank credentials or transaction histories.

"Local-first" does not mean "no third parties at all": direct FinTS access goes to the bank, while an Open Banking connection through Enable Banking necessarily involves that provider. The app must clearly explain the data flow and must only offer provider integrations under terms that permit the intended customer use.

## Product topology

```text
                         Customer-controlled network
  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                  │
  │  iOS app ──────────────┐                                         │
  │                        ├── HTTPS / VPN ──> Kassensturz instance  │
  │  Android app ──────────┘                       │                  │
  │                                               ├── Local SQLite   │
  │  Home Assistant UI / sensors ── HA adapter ───┤                  │
  │                                               ├── FinTS ──> Bank │
  │                                               └── Open Banking   │
  │                                                      │           │
  └──────────────────────────────────────────────────────┼───────────┘
                                                         v
                                                  Enable Banking
```

There is no Kassensturz-hosted transaction database, identity service, synchronization relay or telemetry endpoint in the default design.

## Components and responsibilities

### 1. Domain core (Python)

Keep the existing financial domain logic in Python and progressively separate it from its deployment and user-interface concerns.

Responsibilities:
- account and transaction model;
- import normalization and duplicate detection;
- categorization and user rules;
- contract and subscription detection;
- budgets, analytics and forecasts;
- provider adapters for FinTS and supported Open Banking APIs.

The core must not depend on Home Assistant request objects, ingress headers, mobile UI code or a central Kassensturz service.

### 2. Local application service (FastAPI)

The local service owns one household's database and exposes a versioned API.

Target API prefix: `/api/v1`.

Responsibilities:
- validate requests and enforce device authorization;
- provide stable DTOs independent of SQLite table layout;
- run imports and bank synchronization;
- expose health and capability information;
- publish domain events to connected clients where useful.

The current `/api/*` routes remain the Home Assistant web UI's compatibility interface until a separate migration is designed. Do not break them as part of the initial mobile foundation.

### 3. Persistence

- Keep SQLite for the single-household local installation.
- Treat the database as the authoritative record.
- Introduce explicit schema migrations before expanding the data model.
- Add device/session tables separately from financial tables.
- Never make a cloud database a prerequisite for the app to function.
- Define encrypted backup and restore behavior before advertising backup encryption.

SQLite is appropriate for the present single-household deployment. A move to PostgreSQL is not a prerequisite for the local-first product.

### 4. Home Assistant adapter

Home Assistant remains a supported deployment and integration, not a dependency of the domain core.

- Preserve the current add-on / App Store experience.
- Keep Ingress as the default browser access path.
- Do not expose the API on a new host port until device authentication, authorization, rate limiting and transport security are implemented.
- Keep Home Assistant sensors and notifications behind an adapter.
- Provide a documented standalone Docker deployment using the same Python core and API service.

### 5. Mobile clients

Build one Flutter codebase for iOS and Android.

Initial client responsibilities:
- manual server URL entry and QR-based pairing;
- device registration and revocation;
- dashboard, accounts, transactions, budgets and contracts;
- secure storage of device credentials using Keychain / Android Keystore;
- optional encrypted local cache after threat-model review;
- reconnect and clear offline / stale-data indicators.

The mobile app is not a bank connector in the first release. Bank credentials and bank sessions stay in the customer's Kassensturz instance.

## Connection and trust model

1. The user starts pairing from the trusted local Kassensturz UI or a local administrative command.
2. The instance generates a single-use, short-lived pairing secret and displays it as a QR code.
3. The mobile app exchanges the pairing secret for a device-specific credential.
4. The server stores only a verifier/hash of refresh credentials, records the device name and last use, and supports immediate device revocation.
5. Short-lived access credentials are used for API calls; refresh credentials rotate and the previous credential becomes invalid.
6. Pairing and API traffic require HTTPS. For remote access, recommend a customer-managed VPN. Do not recommend exposing the service directly to the public internet.
7. No shared global app password and no hard-coded vendor secret.

Exact token format, cryptographic algorithms, key rotation and pairing rate limits must be specified in a security ADR and reviewed before implementation.

## Network modes

Supported modes, in priority order:

1. **Local LAN:** user enters or scans the HTTPS address of their own instance.
2. **Customer-managed VPN:** the same local API is reached through WireGuard, Tailscale or an equivalent private network.
3. **Home Assistant deployment:** a separately authenticated API listener may be enabled only after the security work described above. Ingress remains the default browser UI path.

No Kassensturz relay, vendor VPN, reverse proxy or hosted discovery service is part of the initial design.

## Monetization boundaries

The initial release should not require a central entitlement server. Premium design must be resolved separately because Apple and Google purchase verification have different trust and platform requirements.

Before monetization implementation:
- decide whether premium is purchased through native store billing, a permitted external purchase flow, or a signed license;
- document how an entitlement is verified without putting store secrets in the mobile app;
- decide how a purchase is restored after reinstall or device replacement;
- ensure the local server can still be backed up and restored without account lock-in.

Do not implement a client-side boolean as the sole Premium authorization mechanism.

## Non-goals for the first mobile release

- multi-household / family cloud account;
- central Kassensturz-hosted bank aggregation;
- sharing financial data between users;
- vendor-managed remote access;
- AI processing of bank transactions by default;
- replacing the existing Home Assistant UI immediately.

## Acceptance criteria for the architecture

- Core financial logic can be imported and tested without Home Assistant.
- The same instance can serve the Home Assistant UI and authenticated mobile clients.
- No mobile request can read data before pairing and authorization.
- Each device can be revoked independently.
- No API listener is exposed by default before the security controls exist.
- The product remains usable without a Kassensturz cloud account.
- Bank-provider data flows and licensing restrictions are documented.
