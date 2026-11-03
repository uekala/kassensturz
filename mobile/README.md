# Mobile client (iOS and Android)

This directory is reserved for the Flutter client. No application code is added until the local API and device-pairing contract is implemented and tested.

## Product contract

- Connect directly to one customer-controlled Kassensturz instance.
- No Kassensturz cloud account and no central transaction store.
- The first release is a companion client, not a separate bank connector.
- Store device credentials in iOS Keychain / Android Keystore.
- Use HTTPS only; remote access is expected to use the customer's VPN.
- Show connection state and the timestamp of the last successful synchronization.
- Support disconnecting and revoking a device from the local Kassensturz UI.

## Planned structure

```text
mobile/
  README.md
  app/                 # Flutter workspace (created with the API contract)
  docs/
    pairing-and-api.md
```

## Suggested client stack

- Flutter / Dart for one iOS and Android codebase.
- Riverpod (or an equivalent state-management approach).
- Dio or a typed HTTP client for the versioned REST API.
- Keychain / Android Keystore through a maintained secure-storage package.
- Drift / SQLite only when the offline-cache threat model and encryption choice are approved.

Package versions must be selected and pinned when the Flutter workspace is created; this README intentionally does not imply that a Flutter project already exists.

## Build order

1. Finalize the API DTOs and pairing protocol.
2. Implement the server's pairing, device-session and revocation endpoints.
3. Add API contract tests and security tests.
4. Generate the Flutter application skeleton.
5. Implement server pairing and a read-only dashboard.
6. Add transaction, budget and contract workflows.
7. Add offline cache only after data-at-rest protections are tested.
