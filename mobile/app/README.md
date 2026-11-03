# Kassensturz Mobile App

Flutter client source for iOS and Android. Both platforms share the Dart application code.

## Current status

The repository contains a local-first Flutter prototype. It is **not yet connected to a Kassensturz server**. The server-side pairing, login/session and read API routes exist, but this Flutter client does not call them yet. Bank connections and live financial information are not implemented in the app.

The navigation contains:

- Overview dashboard
- Accounts
- Transactions
- Budgets
- More / settings

Dashboard, transactions and budget spending are based on synthetic example data. Account records created in the production app are manually entered by the user. They are not imported from a bank, synchronized with a server or reconciled against transactions.

## Local account management

Accounts can be created, edited and deleted on the device. Each record contains a name, account type, optional institution, optional final four digits and a manually entered EUR balance. Balances are stored as signed integer cents to avoid floating-point storage errors.

The app deliberately rejects complete account/card numbers. It does not ask for or store an IBAN, card number, PIN, TAN or online-banking credentials.

In the production entry point, account records are stored in an SQLite database encrypted with SQLite3MultipleCiphers in SQLCipher compatibility mode. A random 256-bit database key is kept separately using flutter_secure_storage (Android secure storage / iOS Keychain). The test and preview app constructor uses an in-memory repository with synthetic example accounts.

This storage design protects the account database at rest; it is not a complete security certification. Operating-system backups, device compromise, memory exposure, recovery and key-loss handling still require a dedicated release review. Losing the platform-stored database key can make the local account database unreadable.

## Budgets and local persistence

Budget category limits can be created, edited and deleted. The prototype calculates spending against shared synthetic transaction examples and displays the result for the selected month. The dashboard and budget screen use the same budget state.

Budget limits are currently stored on the device using the asynchronous SharedPreferences API. Only category IDs and budget amounts are stored there; credentials, bank details and transaction data are not. SharedPreferences is lightweight app storage and is not encrypted. It is not used for account balances or other account records.

The repository abstractions allow storage implementations to evolve as the Flutter client is connected to the existing Kassensturz server and mobile API.

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

The automated suite covers account model validation, secure-key handling, encrypted database persistence and wrong-key rejection, budget persistence, and the app's main widget flows.

Generate the native Android and iOS project files once:

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

No networking, pairing, mobile authentication or credential exchange is wired into the Flutter prototype yet. Do not add placeholder tokens, fake authentication, or insecure certificate exceptions. The Flutter integration must use the approved API contract, HTTPS certificate validation and platform-secure credential storage.

See [Mobile architecture](../../docs/architecture/0006-flutter-mobile-client.md) and [Mobile security requirements](../../docs/architecture/0002-mobile-api-security.md).
