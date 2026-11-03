import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'mobile_session.dart';
import 'mobile_session_store.dart';

class MobileHttpResponse {
  const MobileHttpResponse({
    required this.statusCode,
    required this.body,
  });

  final int statusCode;
  final String body;
}

abstract interface class MobileTransport {
  Future<MobileHttpResponse> send({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    String? body,
  });

  void close();
}

/// Uses Dart's default TLS validation. No certificate override or redirect
/// following is permitted for requests carrying mobile credentials.
class IoMobileTransport implements MobileTransport {
  IoMobileTransport({
    Duration timeout = const Duration(seconds: 15),
    int maximumResponseBytes = 1024 * 1024,
  }) : _timeout = timeout,
       _maximumResponseBytes = maximumResponseBytes {
    _client.connectionTimeout = timeout;
  }

  final HttpClient _client = HttpClient();
  final Duration _timeout;
  final int _maximumResponseBytes;

  @override
  Future<MobileHttpResponse> send({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    String? body,
  }) async {
    if (uri.scheme != 'https') {
      throw const FormatException('Mobile-Verbindungen benötigen HTTPS.');
    }

    final request = await _client.openUrl(method, uri).timeout(_timeout);
    request
      ..followRedirects = false
      ..maxRedirects = 0
      ..headers.set(HttpHeaders.acceptHeader, 'application/json');
    headers.forEach((name, value) => request.headers.set(name, value));
    if (body != null) {
      request.headers.contentType = ContentType.json;
      request.write(body);
    }

    final response = await request.close().timeout(_timeout);
    final bytes = BytesBuilder(copy: false);
    await for (final chunk in response.timeout(_timeout)) {
      if (bytes.length + chunk.length > _maximumResponseBytes) {
        request.abort();
        throw const FormatException('Die Serverantwort ist zu groß.');
      }
      bytes.add(chunk);
    }

    return MobileHttpResponse(
      statusCode: response.statusCode,
      body: utf8.decode(bytes.takeBytes(), allowMalformed: false),
    );
  }

  @override
  void close() => _client.close(force: true);
}

class MobileApiException implements Exception {
  const MobileApiException({
    required this.statusCode,
    required this.code,
    required this.message,
  });

  final int statusCode;
  final String code;
  final String message;

  @override
  String toString() => message;
}

class MobileSessionExpiredException extends MobileApiException {
  const MobileSessionExpiredException()
    : super(
        statusCode: 401,
        code: 'session_expired',
        message: 'Die Sitzung ist abgelaufen. Bitte kopple das Gerät erneut.',
      );
}

class MobileApiClient {
  MobileApiClient({
    required MobileSessionStore sessionStore,
    MobileTransport? transport,
  }) : _sessionStore = sessionStore,
       _transport = transport ?? IoMobileTransport();

  final MobileSessionStore _sessionStore;
  final MobileTransport _transport;
  Future<MobileSession>? _refreshInFlight;

  Future<MobileSession?> loadSession() => _sessionStore.read();

  Future<MobileSession> pair({
    required String serverUrl,
    required String pairingSecret,
    required String deviceName,
  }) async {
    final baseUrl = MobileSession.normalizeServerUrl(serverUrl);
    final secret = pairingSecret.trim();
    final name = deviceName.trim();
    if (secret.length < 43 || secret.length > 128 || name.isEmpty) {
      throw const FormatException('Pairing-Code oder Gerätename ist ungültig.');
    }

    final response = await _requestJson(
      method: 'POST',
      uri: _endpoint(baseUrl, '/api/v1/pair'),
      body: {
        'pairing_secret': secret,
        'device_name': name,
      },
    );
    final session = MobileSession.fromPairResponse(
      serverUrl: baseUrl,
      response: response,
    );
    await _sessionStore.write(session);
    return session;
  }

  Future<Map<String, dynamic>> me() => _authenticatedJson(
    method: 'GET',
    path: '/api/v1/me',
  );

  Future<Map<String, dynamic>> overview() => _authenticatedJson(
    method: 'GET',
    path: '/api/v1/overview',
  );

  Future<Map<String, dynamic>> transactions({
    int limit = 50,
    int offset = 0,
    String? month,
    int? accountId,
    int? categoryId,
  }) {
    if (limit < 1 || limit > 100 || offset < 0) {
      throw RangeError('Ungültige Buchungsseitenparameter.');
    }
    final query = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (month != null && month.isNotEmpty) 'month': month,
      if (accountId != null) 'account_id': '$accountId',
      if (categoryId != null) 'category_id': '$categoryId',
    };
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/transactions',
      query: query,
    );
  }

  /// Attempts server-side logout and always removes the local credential set.
  /// If the server cannot be reached, the device can still be locally signed out.
  Future<void> logout() async {
    final session = await _sessionStore.read();
    if (session == null) return;
    try {
      await _authenticatedJson(
        method: 'POST',
        path: '/api/v1/auth/logout',
      );
    } finally {
      await _sessionStore.clear();
    }
  }

  Future<Map<String, dynamic>> _authenticatedJson({
    required String method,
    required String path,
    Map<String, String>? query,
  }) async {
    final session = await _sessionStore.read();
    if (session == null) {
      throw const MobileSessionExpiredException();
    }

    try {
      return await _requestJson(
        method: method,
        uri: _endpoint(session.serverUrl, path, query: query),
        headers: {'Authorization': 'Bearer ${session.accessToken}'},
      );
    } on MobileApiException catch (error) {
      if (error.statusCode != 401) rethrow;
    }

    final refreshed = await _refreshSession(session);
    try {
      return await _requestJson(
        method: method,
        uri: _endpoint(refreshed.serverUrl, path, query: query),
        headers: {'Authorization': 'Bearer ${refreshed.accessToken}'},
      );
    } on MobileApiException catch (error) {
      if (error.statusCode == 401) {
        await _sessionStore.clear();
        throw const MobileSessionExpiredException();
      }
      rethrow;
    }
  }

  Future<MobileSession> _refreshSession(MobileSession staleSession) {
    final pending = _refreshInFlight;
    if (pending != null) return pending;

    final refresh = _rotateRefreshToken(staleSession);
    _refreshInFlight = refresh;
    return refresh.whenComplete(() {
      if (identical(_refreshInFlight, refresh)) {
        _refreshInFlight = null;
      }
    });
  }

  Future<MobileSession> _rotateRefreshToken(
    MobileSession staleSession,
  ) async {
    final current = await _sessionStore.read();
    if (current == null) throw const MobileSessionExpiredException();

    // Another request may already have completed the rotation.
    if (current.refreshToken != staleSession.refreshToken) {
      return current;
    }
    if (current.refreshExpiresAt.isBefore(DateTime.now().toUtc())) {
      await _sessionStore.clear();
      throw const MobileSessionExpiredException();
    }

    late final Map<String, dynamic> response;
    try {
      response = await _requestJson(
        method: 'POST',
        uri: _endpoint(current.serverUrl, '/api/v1/auth/refresh'),
        body: {'refresh_token': current.refreshToken},
      );
    } on MobileApiException catch (error) {
      if (error.statusCode == 401) {
        await _sessionStore.clear();
        throw const MobileSessionExpiredException();
      }
      rethrow;
    }

    final accessToken = response['access_token'];
    final refreshToken = response['refresh_token'];
    final accessSeconds = response['access_expires_in'];
    final refreshSeconds = response['refresh_expires_in'];
    if (response['token_type'] != 'Bearer' ||
        accessToken is! String ||
        refreshToken is! String ||
        accessSeconds is! int ||
        refreshSeconds is! int) {
      throw const FormatException('Ungültige Tokenantwort vom Server.');
    }

    final updated = current.withRotatedTokens(
      accessToken: accessToken,
      refreshToken: refreshToken,
      accessExpiresIn: accessSeconds,
      refreshExpiresIn: refreshSeconds,
    );
    await _sessionStore.write(updated);
    return updated;
  }

  Future<Map<String, dynamic>> _requestJson({
    required String method,
    required Uri uri,
    Map<String, String>? headers,
    Map<String, dynamic>? body,
  }) async {
    final response = await _transport.send(
      method: method,
      uri: uri,
      headers: headers ?? const {},
      body: body == null ? null : jsonEncode(body),
    );

    dynamic decoded;
    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      decoded = null;
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = decoded is Map ? decoded['error'] : null;
      final errorMap = error is Map ? error : const <String, dynamic>{};
      final code = errorMap['code'];
      final message = errorMap['message'];
      throw MobileApiException(
        statusCode: response.statusCode,
        code: code is String ? code : 'http_error',
        message: message is String
            ? message
            : 'Der Kassensturz-Server antwortet mit HTTP ${response.statusCode}.',
      );
    }

    if (decoded is! Map) {
      throw const FormatException(
        'Der Server hat keine gültige JSON-Antwort geliefert.',
      );
    }
    return Map<String, dynamic>.from(decoded);
  }

  static Uri _endpoint(
    String baseUrl,
    String path, {
    Map<String, String>? query,
  }) {
    final base = Uri.parse(baseUrl);
    return base.replace(path: path, queryParameters: query);
  }

  void close() => _transport.close();
}
