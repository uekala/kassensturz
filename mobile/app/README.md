# Kassensturz Mobile App

Flutter client source for iOS and Android. Both platforms share the Dart application code.

## Current status

The repository contains an initial local-first UI prototype with synthetic demo data and automated tests. It is **not connected to a Kassensturz server**. Pairing, login, API calls, bank connections and live financial information are not implemented.

The current navigation contains:

- Overview dashboard
- Accounts
- Transactions
- Budgets
- More / settings

Every screen that displays financial values clearly identifies them as example data. Do not interpret these values as a real account balance, transaction history or bank feed.

## Budgets and local persistence

Budget category limits can be created, edited and deleted. The prototype calculates spending against its shared synthetic transaction examples and displays the result for the selected month. The dashboard and budget screen use the same budget state.

Budget limits are stored on the device using the asynchronous SharedPreferences API and are restored when the app is reopened. Only category IDs and budget amounts are stored there; credentials, bank details and transaction data are not.

SharedPreferences is lightweight app storage, not an encrypted financial database or an authoritative store for critical financial data. The repository abstraction is designed so that this storage implementation can be replaced when the Kassensturz server and its mobile API are available.

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

The current automated suite contains repository tests for local budget persistence and widget tests for the app's main flows.

Generate the native Android and iOS project files once:

```bash
bash tool/bootstrap-platforms.sh
```

The bootstrap script refuses to overwrite existing platform folders. After the first generation, keep the generated `android/` and `ios/` directories under version control when preparing a real developer workspace.

Run on a connected device or simulator:

```bash
flutter devices
flutter run
```

## Security and API integration

No networking or credential storage is wired into this prototype yet. Do not add placeholder tokens, fake authentication, or insecure certificate exceptions. The API integration must use the approved contract and platform-secure credential storage once the server-side mobile authentication is implemented.

See [Mobile architecture](../../docs/architecture/0006-flutter-mobile-client.md) and [Mobile security requirements](../../docs/architecture/0002-mobile-api-security.md).
