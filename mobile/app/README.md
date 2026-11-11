# Kassensturz Mobile App

Flutter client source for iOS and Android. Both platforms share the Dart application code.

## Current status

The app is a client for exactly one Kassensturz server. All financial data lives on the server; the installed app keeps only the server address and the device credentials (in platform secure storage).

With a paired server (0.3.0 or newer) the app

- shows overview, accounts, budgets, transactions and contracts from the server,
- creates, edits and deletes manual transactions on accounts without a bank feed,
- changes category and note of bank transactions,
- filters the transaction list by account and category,
- shows the connection state, the last successful synchronisation and a cause-specific message when the server cannot be reached,
- reloads when the app returns to the foreground.

Without a connection the installed app shows a "connect" page instead of example data. Paired with an older server it stays read-only and asks to update the server.

The demo dashboard, the device-local account editor (encrypted SQLite) and the device-local budget limits were removed in 0.3.1, together with the packages they needed. Files written by versions before 0.2.0 stay on the device and are not read.

## Saving and repeated requests

Every "new transaction" form creates one request id and sends it with each attempt to save. The server stores the id, so repeating a save after a lost connection never books twice. Write requests are never repeated automatically; read requests are repeated once.

## Session renewal

Access tokens are renewed with the refresh token as soon as the server answers 401. Only one renewal runs at a time. The server accepts a replaced refresh token exactly once more, within ten minutes, to cover a lost answer. The client therefore repeats a renewal once, immediately, when the connection broke after the request was sent, and does not repeat it when the connection was never established. If the server rejects the renewal, the local session is removed and the device has to be paired again.

## Requirements

- Flutter SDK 3.47.9 from the stable channel (same version as CI)
- Android SDK for Android development
- Xcode on macOS for iOS development

Flutter's stable channel is the recommended channel for new projects and production releases: https://docs.flutter.dev/install/upgrade

## Local setup

From this directory:

```bash
flutter pub get
flutter test
flutter analyze
```

The automated suite covers the API client (pairing, renewal, repeated renewal, write calls), the connection controller (state, synchronisation, saving, filters), response models, error messages, the unpaired app and the connected app on every tab at phone size. The code is checked with `flutter_lints`. The Android manifest hardening is tested with pytest (`tests/test_android_manifest.py`).

Generate the native Android and iOS project files once. The script also declares the INTERNET permission in the release manifest and excludes the app data from Android backup and device transfer:

```bash
bash tool/bootstrap-platforms.sh
```

The bootstrap script refuses to overwrite existing platform folders. After the first generation, keep the generated android/ and ios/ directories under version control when preparing a real developer workspace.

Run on a connected device or simulator:

```bash
flutter devices
flutter run
```

## Security and API integration

The Flutter app includes HTTPS health checks, one-time pairing, automatic refresh, server-backed reads and writes and a native QR scanner for the versioned Kassensturz pairing payload. QR scanning uses the device camera only after the user opens the scanner; the iOS bootstrap adds the required camera usage explanation. The API client uses standard TLS certificate validation, disables redirects for authenticated requests, keeps access tokens in the Authorization header and sends refresh tokens only in the HTTPS request body. Access-token 401 responses trigger a single-flight refresh; a rejected refresh removes the stored session. Credentials are stored in platform secure storage. Do not add placeholder tokens, certificate exceptions or logs containing credentials.

See [Mobile architecture](../../docs/architecture/0006-flutter-mobile-client.md) and [Mobile security requirements](../../docs/architecture/0002-mobile-api-security.md).

## Releasing

A tag `mobile-v<version>` (the version in `pubspec.yaml` without the build number, e.g. `mobile-v0.3.4`) runs the tests, builds the signed arm64 APK and attaches it to a GitHub release with the matching section of `CHANGELOG.md`. The build needs the four `ANDROID_*` repository secrets; without them it stops before building. The build number comes from the run number of the workflow, so every release installs over the previous one.
