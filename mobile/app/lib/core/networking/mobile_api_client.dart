import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'mobile_session.dart';
import 'mobile_session_store.dart';

class MobileHttpResponse {
  const MobileHttpResponse({required this.statusCode, required this.body});

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

class MobileBinaryResponse {
  const MobileBinaryResponse({required this.statusCode, required this.bytes});

  final int statusCode;
  final Uint8List bytes;
}

/// Optional second channel for files. Requests carry raw bytes instead of
/// JSON and answers are returned undecoded.
abstract interface class MobileBinaryTransport {
  Future<MobileBinaryResponse> sendBinary({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    required int maximumResponseBytes,
    Uint8List? body,
  });
}

/// Why a request did not produce an HTTP response.
enum MobileNetworkFailure { unreachable, timeout, certificate, interrupted }

/// A transport failure. [requestSent] is false only when the connection was
/// never established, so the server cannot have processed the request.
class MobileNetworkException implements Exception {
  const MobileNetworkException(this.failure, {required this.requestSent});

  final MobileNetworkFailure failure;
  final bool requestSent;

  @override
  String toString() => 'MobileNetworkException(${failure.name})';
}

/// Uses Dart's default TLS validation. No certificate override or redirect
/// following is permitted for requests carrying mobile credentials.
class IoMobileTransport implements MobileTransport, MobileBinaryTransport {
  IoMobileTransport({
    Duration timeout = const Duration(seconds: 15),
    Duration fileTimeout = const Duration(seconds: 60),
    int maximumResponseBytes = 1024 * 1024,
  }) : _timeout = timeout,
       _fileTimeout = fileTimeout,
       _maximumResponseBytes = maximumResponseBytes {
    _client.connectionTimeout = timeout;
  }

  final HttpClient _client = HttpClient();
  final Duration _timeout;
  final Duration _fileTimeout;
  final int _maximumResponseBytes;

  @override
  Future<MobileHttpResponse> send({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    String? body,
  }) async {
    final response = await _exchange(
      method: method,
      uri: uri,
      headers: headers,
      timeout: _timeout,
      maximumResponseBytes: _maximumResponseBytes,
      write: (request) {
        if (body == null) return;
        request.headers.contentType = ContentType.json;
        request.write(body);
      },
    );
    return MobileHttpResponse(
      statusCode: response.statusCode,
      body: utf8.decode(response.bytes, allowMalformed: false),
    );
  }

  @override
  Future<MobileBinaryResponse> sendBinary({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    required int maximumResponseBytes,
    Uint8List? body,
  }) {
    return _exchange(
      method: method,
      uri: uri,
      headers: headers,
      timeout: _fileTimeout,
      maximumResponseBytes: maximumResponseBytes,
      write: (request) {
        if (body == null) return;
        request.headers.contentType = ContentType.binary;
        request.contentLength = body.length;
        request.add(body);
      },
    );
  }

  Future<MobileBinaryResponse> _exchange({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    required Duration timeout,
    required int maximumResponseBytes,
    required void Function(HttpClientRequest request) write,
  }) async {
    if (uri.scheme != 'https') {
      throw const FormatException('Mobile-Verbindungen benötigen HTTPS.');
    }

    late final HttpClientRequest request;
    try {
      request = await _client.openUrl(method, uri).timeout(_timeout);
    } on Object catch (error) {
      throw _networkFailure(error, requestSent: false);
    }
    request
      ..followRedirects = false
      ..maxRedirects = 0
      ..headers.set(HttpHeaders.acceptHeader, 'application/json');
    headers.forEach((name, value) => request.headers.set(name, value));
    write(request);

    try {
      final response = await request.close().timeout(timeout);
      final bytes = BytesBuilder(copy: false);
      await for (final chunk in response.timeout(timeout)) {
        if (bytes.length + chunk.length > maximumResponseBytes) {
          request.abort();
          throw const FormatException('Die Serverantwort ist zu groß.');
        }
        bytes.add(chunk);
      }

      return MobileBinaryResponse(
        statusCode: response.statusCode,
        bytes: bytes.takeBytes(),
      );
    } on FormatException {
      rethrow;
    } on Object catch (error) {
      throw _networkFailure(error, requestSent: true);
    }
  }

  static MobileNetworkException _networkFailure(
    Object error, {
    required bool requestSent,
  }) {
    if (error is MobileNetworkException) return error;
    final MobileNetworkFailure failure;
    if (error is TimeoutException) {
      failure = MobileNetworkFailure.timeout;
    } else if (error is HandshakeException || error is TlsException) {
      failure = MobileNetworkFailure.certificate;
    } else if (requestSent) {
      failure = MobileNetworkFailure.interrupted;
    } else {
      failure = MobileNetworkFailure.unreachable;
    }
    return MobileNetworkException(failure, requestSent: requestSent);
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
    Duration refreshRetryDelay = const Duration(seconds: 2),
  }) : _sessionStore = sessionStore,
       _transport = transport ?? IoMobileTransport(),
       _refreshRetryDelay = refreshRetryDelay;

  final MobileSessionStore _sessionStore;
  final MobileTransport _transport;
  final Duration _refreshRetryDelay;
  Future<MobileSession>? _refreshInFlight;

  Future<MobileSession?> loadSession() => _sessionStore.read();

  /// Removes a stored session that can no longer be read or used.
  Future<void> discardSession() => _sessionStore.clear();

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
      body: {'pairing_secret': secret, 'device_name': name},
    );
    final session = MobileSession.fromPairResponse(
      serverUrl: baseUrl,
      response: response,
    );
    await _sessionStore.write(session);
    return session;
  }

  Future<Map<String, dynamic>> health({required String serverUrl}) async {
    final baseUrl = MobileSession.normalizeServerUrl(serverUrl);
    final response = await _requestJson(
      method: 'GET',
      uri: _endpoint(baseUrl, '/api/v1/health'),
    );
    if (response['status'] != 'ok' || response['api_version'] != 1) {
      throw const FormatException(
        'Der Server unterstützt die erwartete Kassensturz-API nicht.',
      );
    }
    return response;
  }

  Future<Map<String, dynamic>> me() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/me');

  Future<Map<String, dynamic>> overview() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/overview');

  Future<Map<String, dynamic>> transactions({
    int limit = 50,
    int offset = 0,
    String? month,
    int? accountId,
    int? categoryId,
    String? search,
    String? kind,
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
      if (search != null && search.isNotEmpty) 'q': search,
      if (kind != null && kind.isNotEmpty) 'kind': kind,
    };
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/transactions',
      query: query,
    );
  }

  Future<Map<String, dynamic>> accounts() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/accounts');

  Future<Map<String, dynamic>> categories() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/categories');

  /// Category spending, monthly totals and the balance curve. [month] is
  /// 'YYYY-MM'; without it the server answers for the current month.
  Future<Map<String, dynamic>> stats({String? month}) => _authenticatedJson(
    method: 'GET',
    path: '/api/v1/stats',
    query: {if (month != null && month.isNotEmpty) 'month': month},
  );

  /// What a purchase of [amountCents] today means until the next salary.
  Future<Map<String, dynamic>> afford(int amountCents) {
    if (amountCents <= 0) {
      throw const FormatException('Der Betrag ist ungültig.');
    }
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/afford',
      query: {'amount_cents': '$amountCents'},
    );
  }

  Future<Map<String, dynamic>> contracts() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/contracts');

  /// Creates a manual transaction. [fields] must contain a
  /// `client_request_id`; sending the same id again never books twice.
  /// Creates an account without bank feed for entries made by hand.
  Future<Map<String, dynamic>> createCashAccount(
    String name, {
    int? balanceCents,
  }) {
    if (name.trim().isEmpty) {
      throw const FormatException('Bitte gib dem Konto einen Namen.');
    }
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/accounts',
      body: {'name': name.trim(), 'balance_cents': ?balanceCents},
    );
  }

  Future<Map<String, dynamic>> createTransaction(Map<String, dynamic> fields) {
    final requestId = fields['client_request_id'];
    if (requestId is! String || requestId.length < 16) {
      throw const FormatException('Die Anfragekennung fehlt.');
    }
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/transactions',
      body: fields,
    );
  }

  Future<Map<String, dynamic>> updateTransaction(
    int id,
    Map<String, dynamic> changes,
  ) {
    if (id <= 0 || changes.isEmpty) {
      throw const FormatException('Die Änderung ist ungültig.');
    }
    return _authenticatedJson(
      method: 'PATCH',
      path: '/api/v1/transactions/$id',
      body: changes,
    );
  }

  /// Changes the status of a contract or acknowledges its price change.
  Future<Map<String, dynamic>> updateContract(
    String key,
    Map<String, dynamic> changes,
  ) {
    if (key.isEmpty || changes.isEmpty) {
      throw const FormatException('Die Änderung ist ungültig.');
    }
    return _authenticatedJson(
      method: 'PATCH',
      path: '/api/v1/contracts/${Uri.encodeComponent(key)}',
      body: changes,
    );
  }

  /// Builds the cancellation letter for a contract. [mode] is 'ordentlich',
  /// 'sonder' or 'termin'; [date] (YYYY-MM-DD) is only sent with 'termin'.
  Future<Map<String, dynamic>> contractLetter(
    String key, {
    String mode = 'ordentlich',
    String? date,
  }) {
    if (key.isEmpty) throw const FormatException('Der Vertrag fehlt.');
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/contracts/${Uri.encodeComponent(key)}/letter',
      body: {'mode': mode, 'date': ?date},
    );
  }

  /// Sets the monthly budget of an expense category; null removes it.
  Future<Map<String, dynamic>> setBudget(int categoryId, int? limitCents) {
    if (categoryId <= 0 || (limitCents != null && limitCents <= 0)) {
      throw const FormatException('Das Budget ist ungültig.');
    }
    return _authenticatedJson(
      method: 'PUT',
      path: '/api/v1/budgets/$categoryId',
      body: {'limit_cents': limitCents},
    );
  }

  Future<void> deleteTransaction(int id) async {
    if (id <= 0) throw const FormatException('Die Buchung ist ungültig.');
    await _authenticatedJson(
      method: 'DELETE',
      path: '/api/v1/transactions/$id',
    );
  }

  /// Largest receipt the app sends or shows; the server enforces the same.
  static const maximumReceiptBytes = 10 * 1024 * 1024;

  Future<Map<String, dynamic>> receipts(int transactionId) {
    if (transactionId <= 0) {
      throw const FormatException('Die Buchung ist ungültig.');
    }
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/transactions/$transactionId/receipts',
    );
  }

  /// Attaches a photo or PDF to a transaction. Never repeated automatically.
  Future<Map<String, dynamic>> uploadReceipt(
    int transactionId,
    String filename,
    Uint8List bytes,
  ) async {
    if (transactionId <= 0 || bytes.isEmpty) {
      throw const FormatException('Der Beleg ist leer.');
    }
    if (bytes.length > maximumReceiptBytes) {
      throw const FormatException('Die Datei ist größer als 10 MB.');
    }
    final answer = await _authenticatedBinary(
      method: 'POST',
      path: '/api/v1/transactions/$transactionId/receipts',
      query: {'filename': filename},
      body: bytes,
      maximumResponseBytes: 64 * 1024,
    );
    final decoded = _decodeJson(answer);
    if (decoded is! Map) {
      throw const FormatException(
        'Der Server hat keine gültige JSON-Antwort geliefert.',
      );
    }
    return Map<String, dynamic>.from(decoded);
  }

  /// The stored file of one receipt.
  Future<Uint8List> receiptBytes(int receiptId) {
    if (receiptId <= 0) throw const FormatException('Der Beleg ist ungültig.');
    return _authenticatedBinary(
      method: 'GET',
      path: '/api/v1/receipts/$receiptId',
      maximumResponseBytes: maximumReceiptBytes,
    );
  }

  Future<void> deleteReceipt(int receiptId) async {
    if (receiptId <= 0) throw const FormatException('Der Beleg ist ungültig.');
    await _authenticatedJson(
      method: 'DELETE',
      path: '/api/v1/receipts/$receiptId',
    );
  }

  Future<Uint8List> _authenticatedBinary({
    required String method,
    required String path,
    required int maximumResponseBytes,
    Map<String, String>? query,
    Uint8List? body,
  }) async {
    final Object transport = _transport;
    if (transport is! MobileBinaryTransport) {
      throw const FormatException('Diese Verbindung überträgt keine Dateien.');
    }
    final session = await _sessionStore.read();
    if (session == null) {
      throw const MobileSessionExpiredException();
    }

    Future<Uint8List> attempt(MobileSession current) async {
      final response = await transport.sendBinary(
        method: method,
        uri: _endpoint(current.serverUrl, path, query: query),
        headers: {'Authorization': 'Bearer ${current.accessToken}'},
        maximumResponseBytes: maximumResponseBytes,
        body: body,
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return response.bytes;
      }
      throw _apiError(response.statusCode, _decodeJson(response.bytes));
    }

    try {
      return await attempt(session);
    } on MobileApiException catch (error) {
      if (error.statusCode != 401) rethrow;
    }

    final refreshed = await _refreshSession(session);
    try {
      return await attempt(refreshed);
    } on MobileApiException catch (error) {
      if (error.statusCode == 401) {
        await _sessionStore.clear();
        throw const MobileSessionExpiredException();
      }
      rethrow;
    }
  }

  static dynamic _decodeJson(Uint8List bytes) {
    try {
      return jsonDecode(utf8.decode(bytes));
    } on FormatException {
      return null;
    }
  }

  static MobileApiException _apiError(int statusCode, dynamic decoded) {
    final error = decoded is Map ? decoded['error'] : null;
    final errorMap = error is Map ? error : const <String, dynamic>{};
    final code = errorMap['code'];
    final message = errorMap['message'];
    return MobileApiException(
      statusCode: statusCode,
      code: code is String ? code : 'http_error',
      message: message is String
          ? message
          : 'Der Kassensturz-Server antwortet mit HTTP $statusCode.',
    );
  }

  /// Attempts server-side logout and always removes the local credential set.
  /// If the server cannot be reached, the device can still be locally signed out.
  Future<void> logout() async {
    final session = await _sessionStore.read();
    if (session == null) return;
    try {
      await _authenticatedJson(method: 'POST', path: '/api/v1/auth/logout');
    } finally {
      await _sessionStore.clear();
    }
  }

  Future<Map<String, dynamic>> _authenticatedJson({
    required String method,
    required String path,
    Map<String, String>? query,
    Map<String, dynamic>? body,
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
        body: body,
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
        body: body,
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

  Future<MobileSession> _rotateRefreshToken(MobileSession staleSession) async {
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
      response = await _sendRefresh(current);
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

  /// Sends the refresh token. The server accepts a replaced refresh token
  /// exactly once more, and only within ten minutes of the first attempt.
  /// If the connection breaks after the request left the device, the answer
  /// may be lost although the server already rotated the token, so the one
  /// permitted repetition is sent right away instead of minutes later.
  /// A connection that was never established is not repeated here: nothing
  /// reached the server and the next call simply starts over.
  Future<Map<String, dynamic>> _sendRefresh(MobileSession current) async {
    Future<Map<String, dynamic>> send() => _requestJson(
      method: 'POST',
      uri: _endpoint(current.serverUrl, '/api/v1/auth/refresh'),
      body: {'refresh_token': current.refreshToken},
    );

    try {
      return await send();
    } on MobileNetworkException catch (error) {
      if (!error.requestSent) rethrow;
    }
    await Future<void>.delayed(_refreshRetryDelay);
    return send();
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
      throw _apiError(response.statusCode, decoded);
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
