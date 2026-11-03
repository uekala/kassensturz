import 'dart:convert';

/// A single-device session issued by a local Kassensturz server.
class MobileSession {
  const MobileSession({
    required this.serverUrl,
    required this.deviceId,
    required this.deviceName,
    required this.accessToken,
    required this.refreshToken,
    required this.accessExpiresAt,
    required this.refreshExpiresAt,
  });

  final String serverUrl;
  final String deviceId;
  final String deviceName;
  final String accessToken;
  final String refreshToken;
  final DateTime accessExpiresAt;
  final DateTime refreshExpiresAt;

  /// Accept only an HTTPS origin. Credentials, query strings and URL paths
  /// are rejected so secrets can never accidentally be embedded in a URL.
  static String normalizeServerUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        uri.scheme.toLowerCase() != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw const FormatException(
        'Bitte eine gültige HTTPS-Serveradresse ohne Pfad eingeben.',
      );
    }
    return uri.origin;
  }

  factory MobileSession.fromPairResponse({
    required String serverUrl,
    required Map<String, dynamic> response,
    DateTime? now,
  }) {
    final device = response['device'];
    if (device is! Map) {
      throw const FormatException('Ungültige Geräteantwort vom Server.');
    }
    final deviceMap = Map<String, dynamic>.from(device);
    final deviceId = deviceMap['id'];
    final deviceName = deviceMap['name'];
    final accessToken = response['access_token'];
    final refreshToken = response['refresh_token'];
    final accessSeconds = response['access_expires_in'];
    final refreshSeconds = response['refresh_expires_in'];
    if (deviceId is! String ||
        deviceId.isEmpty ||
        deviceName is! String ||
        deviceName.isEmpty ||
        accessToken is! String ||
        accessToken.length < 32 ||
        refreshToken is! String ||
        refreshToken.length < 32 ||
        accessSeconds is! int ||
        accessSeconds <= 0 ||
        refreshSeconds is! int ||
        refreshSeconds <= 0 ||
        response['token_type'] != 'Bearer') {
      throw const FormatException('Ungültige Anmeldedaten vom Server.');
    }
    final issuedAt = (now ?? DateTime.now()).toUtc();
    return MobileSession(
      serverUrl: normalizeServerUrl(serverUrl),
      deviceId: deviceId,
      deviceName: deviceName,
      accessToken: accessToken,
      refreshToken: refreshToken,
      accessExpiresAt: issuedAt.add(Duration(seconds: accessSeconds)),
      refreshExpiresAt: issuedAt.add(Duration(seconds: refreshSeconds)),
    );
  }

  factory MobileSession.fromStoredJson(String encoded) {
    final decoded = jsonDecode(encoded);
    if (decoded is! Map) {
      throw const FormatException('Gespeicherte Sitzung ist ungültig.');
    }
    final value = Map<String, dynamic>.from(decoded);
    final serverUrl = value['server_url'];
    final deviceId = value['device_id'];
    final deviceName = value['device_name'];
    final accessToken = value['access_token'];
    final refreshToken = value['refresh_token'];
    final accessExpiry = value['access_expires_at'];
    final refreshExpiry = value['refresh_expires_at'];
    if (serverUrl is! String ||
        deviceId is! String ||
        deviceName is! String ||
        accessToken is! String ||
        refreshToken is! String ||
        accessExpiry is! String ||
        refreshExpiry is! String) {
      throw const FormatException('Gespeicherte Sitzung ist unvollständig.');
    }
    return MobileSession(
      serverUrl: normalizeServerUrl(serverUrl),
      deviceId: deviceId,
      deviceName: deviceName,
      accessToken: accessToken,
      refreshToken: refreshToken,
      accessExpiresAt: DateTime.parse(accessExpiry).toUtc(),
      refreshExpiresAt: DateTime.parse(refreshExpiry).toUtc(),
    );
  }

  String toStoredJson() => jsonEncode({
    'server_url': serverUrl,
    'device_id': deviceId,
    'device_name': deviceName,
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'access_expires_at': accessExpiresAt.toUtc().toIso8601String(),
    'refresh_expires_at': refreshExpiresAt.toUtc().toIso8601String(),
  });

  MobileSession withRotatedTokens({
    required String accessToken,
    required String refreshToken,
    required int accessExpiresIn,
    required int refreshExpiresIn,
    DateTime? now,
  }) {
    if (accessToken.length < 32 ||
        refreshToken.length < 32 ||
        accessExpiresIn <= 0 ||
        refreshExpiresIn <= 0) {
      throw const FormatException('Ungültige Tokenantwort vom Server.');
    }
    final issuedAt = (now ?? DateTime.now()).toUtc();
    return MobileSession(
      serverUrl: serverUrl,
      deviceId: deviceId,
      deviceName: deviceName,
      accessToken: accessToken,
      refreshToken: refreshToken,
      accessExpiresAt: issuedAt.add(Duration(seconds: accessExpiresIn)),
      refreshExpiresAt: issuedAt.add(Duration(seconds: refreshExpiresIn)),
    );
  }
}
