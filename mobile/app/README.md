# Kassensturz Mobile App

Flutter client source for iOS and Android. Both platforms share the Dart application code.

## Current status

The repository contains an initial UI prototype with demo data and widget tests. It is **not connected to a Kassensturz server**. Pairing, login, API calls and live financial information are not implemented.

The current navigation contains:

- Overview dashboard
- Accounts
- Transactions
- Connection and settings placeholder

Every screen displays a persistent notice that the visible values are example data.

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
