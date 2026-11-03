import 'dart:convert';

import 'mobile_session.dart';

/// A short-lived pairing invitation read from a Kassensturz admin QR code.
class MobilePairingPayload {
  const MobilePairingPayload({
    required this.serverUrl,
    required this.pairingSecret,
  });

  static const type = 'kassensturz-pairing';
  static const version = 1;

  final String serverUrl;
  final String pairingSecret;

  factory MobilePairingPayload.fromRawValue(String rawValue) {
    dynamic decoded;
    try {
      decoded = jsonDecode(rawValue);
    } on FormatException {
      throw const FormatException(
        'Dieser QR-Code ist kein Kassensturz-Pairing-Code.',
      );
    }

    if (decoded is! Map ||
        decoded['type'] != type ||
        decoded['version'] != version) {
      throw const FormatException(
        'Dieser QR-Code wird von Kassensturz nicht unterstützt.',
      );
    }

    final serverUrl = decoded['server_url'];
    final pairingSecret = decoded['pairing_secret'];
    if (serverUrl is! String ||
        pairingSecret is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{43,128}$').hasMatch(pairingSecret)) {
      throw const FormatException(
        'Der Kassensturz-Pairing-Code ist unvollständig oder ungültig.',
      );
    }

    return MobilePairingPayload(
      serverUrl: MobileSession.normalizeServerUrl(serverUrl),
      pairingSecret: pairingSecret,
    );
  }
}
