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

/// Optionaler zweiter Kanal für Dateien. Anfragen tragen rohe Bytes statt
/// JSON, und Antworten kommen undekodiert zurück.
abstract interface class MobileBinaryTransport {
  Future<MobileBinaryResponse> sendBinary({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    required int maximumResponseBytes,
    Uint8List? body,
  });
}

/// Warum eine Anfrage keine HTTP-Antwort ergeben hat.
enum MobileNetworkFailure { unreachable, timeout, certificate, interrupted }

/// Ein Transportfehler. [requestSent] ist nur false, wenn die Verbindung nie
/// zustande kam, der Server die Anfrage also nicht verarbeitet haben kann.
class MobileNetworkException implements Exception {
  const MobileNetworkException(this.failure, {required this.requestSent});

  final MobileNetworkFailure failure;
  final bool requestSent;

  @override
  String toString() => 'MobileNetworkException(${failure.name})';
}

/// Nutzt die Standard-TLS-Prüfung von Dart. Für Anfragen mit Zugangsdaten der Handy-App
/// sind weder Zertifikatsausnahmen noch das Folgen von Weiterleitungen erlaubt.
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

  /// Entfernt eine gespeicherte Sitzung, die sich nicht mehr lesen oder nutzen lässt.
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
    String? part,
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
      if (part != null && part.isNotEmpty) 'part': part,
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

  /// Ausgaben nach Kategorie, Monatssummen und Saldoverlauf. [month] ist
  /// 'YYYY-MM'; ohne antwortet der Server für den laufenden Monat.
  Future<Map<String, dynamic>> stats({String? month, String? part}) =>
      _authenticatedJson(
        method: 'GET',
        path: '/api/v1/stats',
        query: {
          if (month != null && month.isNotEmpty) 'month': month,
          if (part != null && part.isNotEmpty) 'part': part,
        },
      );

  /// Der Jahresrückblick, verglichen mit dem Vorjahr.
  Future<Map<String, dynamic>> yearReview({int? year, String? part}) =>
      _authenticatedJson(
        method: 'GET',
        path: '/api/v1/year',
        query: {
          if (year != null) 'year': '$year',
          if (part != null && part.isNotEmpty) 'part': part,
        },
      );

  /// Was ein Kauf über [amountCents] heute bis zum nächsten Gehalt bedeutet.
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

  /// Legt einen manuellen Umsatz an. [fields] muss eine `client_request_id`
  /// enthalten; dieselbe ID erneut zu senden bucht nie doppelt.
  Future<Map<String, dynamic>> netWorthHistory() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/networth');

  Future<Map<String, dynamic>> news() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/news');

  Future<void> markNewsSeen() async {
    await _authenticatedJson(method: 'POST', path: '/api/v1/news/seen');
  }

  /// Steuerübersicht von [year] (bei null das neueste) und die Garantien.
  Future<Map<String, dynamic>> papers({int? year}) => _authenticatedJson(
    method: 'GET',
    path: '/api/v1/papers',
    query: year == null ? null : {'year': '$year'},
  );

  /// Transactions without a real category, largest first.
  Future<Map<String, dynamic>> triage({int limit = 30}) => _authenticatedJson(
    method: 'GET',
    path: '/api/v1/triage',
    query: {'limit': '$limit'},
  );

  Future<Map<String, dynamic>> budgetSuggestions() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/budgets/suggestions');

  Future<Map<String, dynamic>> syncStatus() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/sync');

  /// Bittet den Server, jetzt bei den Banken abzurufen. Nie automatisch
  /// wiederholt: Banken erlauben nur wenige Abrufe am Tag. Mit
  /// [interactive] darf eine Bank zurückfragen, zum Beispiel nach einer TAN.
  Future<Map<String, dynamic>> startSync({bool interactive = false}) =>
      _authenticatedJson(
        method: 'POST',
        path: '/api/v1/sync',
        body: interactive ? {'interactive': true} : null,
      );

  /// Beantwortet, was eine Bank während eines Abrufs fragt, oder gibt den Abruf auf. Eine TAN
  /// gilt einmal, deshalb wird das nie automatisch wiederholt.
  Future<Map<String, dynamic>> answerSync(
    String qid, {
    String? value,
    bool cancel = false,
  }) => _authenticatedJson(
    method: 'POST',
    path: '/api/v1/sync/answer',
    body: {'qid': qid, 'value': ?value, if (cancel) 'cancel': true},
  );

  /// Beginnt das Verlängern einer ablaufenden Bank-Einwilligung; die Antwort enthält die
  /// zu öffnende Seite der Bank. Auf dem Server ändert sich noch nichts.
  Future<Map<String, dynamic>> startBankRenewal(int id) => _authenticatedJson(
    method: 'POST',
    path: '/api/v1/banks/renew',
    body: {'id': id},
  );

  /// Schließt eine Verlängerung mit der Adresse ab, auf der der Browser gelandet ist. Der Code
  /// darin gilt einmal, deshalb wird das nie automatisch wiederholt.
  Future<Map<String, dynamic>> completeBankRenewal(String address) =>
      _authenticatedJson(
        method: 'POST',
        path: '/api/v1/banks/renew/complete',
        body: {'text': address},
      );

  /// Legt ein Konto ohne Bankanbindung für von Hand erfasste Einträge an.
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

  /// Trägt den heutigen Wert einer Geldanlage oder die Restschuld eines Kredits ein.
  Future<Map<String, dynamic>> setAccountValue(int accountId, int cents) =>
      _authenticatedJson(
        method: 'PUT',
        path: '/api/v1/accounts/$accountId/value',
        body: {'value_cents': cents},
      );

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

  /// Ändert den Status eines Vertrags oder nimmt seine Preisänderung zur Kenntnis.
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

  /// Erstellt das Kündigungsschreiben für einen Vertrag. [mode] ist 'ordentlich',
  /// 'sonder' oder 'termin'; [date] (YYYY-MM-DD) wird nur mit 'termin' gesendet.
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

  /// Setzt das Monatsbudget einer Ausgabenkategorie; null entfernt es. Mit
  /// [own] ist es das Budget dieser Person, das nur eigene Konten zählt.
  Future<Map<String, dynamic>> setBudget(
    int categoryId,
    int? limitCents, {
    bool own = false,
  }) {
    if (categoryId <= 0 || (limitCents != null && limitCents <= 0)) {
      throw const FormatException('Das Budget ist ungültig.');
    }
    final prefix = own ? '/api/v1/budgets/own' : '/api/v1/budgets';
    return _authenticatedJson(
      method: 'PUT',
      path: '$prefix/$categoryId',
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

  /// Größter Beleg, den die App sendet oder zeigt; der Server setzt dasselbe durch.
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

  /// Hängt ein Foto oder PDF an einen Umsatz. Nie automatisch wiederholt.
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

  /// Die gespeicherte Datei eines Belegs.
  Future<Uint8List> receiptBytes(int receiptId) {
    if (receiptId <= 0) throw const FormatException('Der Beleg ist ungültig.');
    return _authenticatedBinary(
      method: 'GET',
      path: '/api/v1/receipts/$receiptId',
      maximumResponseBytes: maximumReceiptBytes,
    );
  }

  /// Ein Monatsbericht (Zeitraum JJJJ-MM) oder der Jahresrückblick (Zeitraum JJJJ) als
  /// PDF, aus dem, was dieses Gerät sieht.
  Future<Uint8List> reportBytes({
    required String kind,
    required String period,
    String? part,
  }) {
    if (kind != 'month' && kind != 'year') {
      throw const FormatException('Diesen Bericht gibt es nicht.');
    }
    return _authenticatedBinary(
      method: 'GET',
      path: '/api/v1/report/$kind',
      query: {
        'period': period,
        if (part != null && part.isNotEmpty) 'part': part,
      },
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

  /// Ob sich eine Ausgabe mit dem Haushalt teilen lässt und wie sie geteilt ist.
  Future<Map<String, dynamic>> transactionShare(int transactionId) {
    if (transactionId <= 0) {
      throw const FormatException('Die Buchung ist ungültig.');
    }
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/transactions/$transactionId/share',
    );
  }

  /// Geteilte Ausgaben dieser Person, was offen ist, und die Zahlungen.
  Future<Map<String, dynamic>> householdSharing() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/household/sharing');

  /// Hält eine Zahlung dieser Person an eine andere im Haushalt fest.
  Future<Map<String, dynamic>> addSettlement(
    int toPersonId,
    int cents,
    String note,
  ) {
    if (toPersonId <= 0 || cents <= 0) {
      throw const FormatException('Die Zahlung ist ungültig.');
    }
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/household/settlements',
      body: {'to_person_id': toPersonId, 'cents': cents, 'note': note},
    );
  }

  /// Teilt eine Ausgabe nach den für den Haushalt festgelegten Anteilen oder macht das rückgängig.
  Future<Map<String, dynamic>> setTransactionShare(
    int transactionId, {
    required bool shared,
  }) {
    if (transactionId <= 0) {
      throw const FormatException('Die Buchung ist ungültig.');
    }
    return _authenticatedJson(
      method: shared ? 'PUT' : 'DELETE',
      path: '/api/v1/transactions/$transactionId/share',
      body: shared ? const <String, dynamic>{} : null,
    );
  }

  /// Wer was geändert hat, das Neueste zuerst, soweit diese Person es sehen darf.
  Future<Map<String, dynamic>> changes({int offset = 0}) {
    if (offset < 0) throw const FormatException('Ungültige Seite.');
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/changes',
      query: {'offset': '$offset', 'limit': '50'},
    );
  }

  /// Projekte mit ihren Kosten, soweit diese Person die Buchungen sieht.
  Future<Map<String, dynamic>> projects() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/projects');

  /// Ein Projekt mit Kosten nach Kategorie und Monat und seinen Buchungen.
  Future<Map<String, dynamic>> project(int id) {
    if (id <= 0) throw const FormatException('Das Projekt ist ungültig.');
    return _authenticatedJson(method: 'GET', path: '/api/v1/projects/$id');
  }

  /// Charging per month from Ladecockpit.
  Future<Map<String, dynamic>> chargingMonths() =>
      _authenticatedJson(method: 'GET', path: '/api/v1/charging');

  /// Die Ladung, die eine Buchung bezahlt hat; sonst ist `charging` null.
  Future<Map<String, dynamic>> transactionCharging(int transactionId) {
    if (transactionId <= 0) {
      throw const FormatException('Die Buchung ist ungültig.');
    }
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/transactions/$transactionId/charging',
    );
  }

  /// Das Projekt eines Umsatzes und die Projekte, in die er kommen kann.
  Future<Map<String, dynamic>> transactionProject(int transactionId) {
    if (transactionId <= 0) {
      throw const FormatException('Die Buchung ist ungültig.');
    }
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/transactions/$transactionId/project',
    );
  }

  /// Legt einen Umsatz in ein Projekt oder nimmt ihn mit null heraus.
  Future<Map<String, dynamic>> setTransactionProject(
    int transactionId,
    int? projectId,
  ) {
    if (transactionId <= 0 || (projectId != null && projectId <= 0)) {
      throw const FormatException('Das Projekt ist ungültig.');
    }
    return _authenticatedJson(
      method: 'PUT',
      path: '/api/v1/transactions/$transactionId/project',
      body: {'project_id': projectId},
    );
  }

  /// Tilgungsplan eines Kredits; mit [extraCents] die Wirkung, heute so viel
  /// zu tilgen.
  Future<Map<String, dynamic>> loanPlan(int accountId, {int extraCents = 0}) {
    if (accountId <= 0 || extraCents < 0) {
      throw const FormatException('Der Kredit ist ungültig.');
    }
    return _authenticatedJson(
      method: 'GET',
      path: '/api/v1/accounts/$accountId/loan',
      query: extraCents > 0 ? {'extra_cents': '$extraCents'} : null,
    );
  }

  /// Blendet eine Auffälligkeit aus, die die Person geprüft hat.
  Future<Map<String, dynamic>> acknowledgeAlert(String key) {
    if (key.isEmpty) throw const FormatException('Der Hinweis fehlt.');
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/alerts/ack',
      body: {'key': key},
    );
  }

  /// Plant eine einmalige Ausgabe, die dann in der Prognose zählt.
  Future<Map<String, dynamic>> createPlanned({
    required String label,
    required int cents,
    required String dueDate,
    required int accountId,
  }) {
    if (label.trim().isEmpty || cents <= 0 || accountId <= 0) {
      throw const FormatException('Die geplante Ausgabe ist ungültig.');
    }
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/planned',
      body: {
        'label': label.trim(),
        'cents': cents,
        'due_date': dueDate,
        'account_id': accountId,
      },
    );
  }

  /// Hält fest, dass für eine Ausgabe Geld zurückkommt, ganz oder teilweise.
  Future<Map<String, dynamic>> createExpected(int transactionId, int cents) {
    if (transactionId <= 0 || cents <= 0) {
      throw const FormatException('Der erwartete Eingang ist ungültig.');
    }
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/expected',
      body: {'tx_id': transactionId, 'cents': cents},
    );
  }

  /// Hakt eine geplante Ausgabe oder eine erwartete Einnahme ab oder streicht sie.
  /// [kind] ist `planned` oder `expected`; [action] `paid`, `received` oder `drop`.
  Future<Map<String, dynamic>> settlePlan(String kind, int id, String action) {
    const allowed = {
      'planned': {'paid', 'drop'},
      'expected': {'received', 'drop'},
    };
    if (id <= 0 || !(allowed[kind]?.contains(action) ?? false)) {
      throw const FormatException('Die Aktion ist ungültig.');
    }
    return _authenticatedJson(
      method: 'POST',
      path: '/api/v1/$kind/$id/$action',
      body: const <String, dynamic>{},
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

  /// Versucht das Abmelden auf dem Server und entfernt immer die lokalen Zugangsdaten.
  /// Ist der Server nicht erreichbar, lässt sich das Gerät trotzdem lokal abmelden.
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

    // Eine andere Anfrage hat die Rotation vielleicht schon abgeschlossen.
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

  /// Sendet das Refresh-Token. Der Server akzeptiert ein ersetztes Refresh-Token
  /// genau ein weiteres Mal, und nur innerhalb von zehn Minuten nach dem ersten Versuch.
  /// Bricht die Verbindung ab, nachdem die Anfrage das Gerät verlassen hat, kann die
  /// Antwort verloren sein, obwohl der Server das Token schon rotiert hat; die eine
  /// erlaubte Wiederholung wird deshalb sofort gesendet statt Minuten später.
  /// Eine Verbindung, die nie zustande kam, wird hier nicht wiederholt: Nichts hat den
  /// Server erreicht, und der nächste Aufruf beginnt einfach von vorn.
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
