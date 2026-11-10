import 'package:flutter/foundation.dart';

import 'mobile_api_client.dart';
import 'mobile_error_messages.dart';
import 'mobile_models.dart';
import 'mobile_session.dart';
import 'mobile_session_store.dart';

/// What the app currently knows about its link to the Kassensturz server.
enum ServerLinkState { notPaired, connected, unreachable }

class MobileConnectionController extends ChangeNotifier {
  MobileConnectionController({
    required MobileApiClient apiClient,
    Duration readRetryDelay = const Duration(seconds: 1),
    DateTime Function()? clock,
  }) : _apiClient = apiClient,
       _readRetryDelay = readRetryDelay,
       _clock = clock ?? DateTime.now;

  factory MobileConnectionController.preview() {
    return MobileConnectionController(
      apiClient: MobileApiClient(sessionStore: InMemoryMobileSessionStore()),
    );
  }

  static const writeCapability = 'transactions.write';

  final MobileApiClient _apiClient;
  final Duration _readRetryDelay;
  final DateTime Function() _clock;

  MobileSession? _session;
  bool _isBusy = false;
  bool _isLoading = false;
  String? _errorMessage;
  String? _statusMessage;
  Map<String, dynamic>? _overview;
  Map<String, dynamic>? _transactionPage;
  bool _financeLoading = false;
  String? _financeError;
  bool _unreachable = false;
  DateTime? _lastSyncAt;
  Set<String> _capabilities = const {};
  String? _serverVersion;
  List<ServerAccount> _accounts = const [];
  List<ServerCategory> _categories = const [];
  List<ServerContract> _contracts = const [];
  bool _contractsLoading = false;
  String? _contractsError;
  int? _filterAccountId;
  int? _filterCategoryId;
  bool _disposed = false;

  void _notifyIfMounted() {
    if (!_disposed) notifyListeners();
  }

  MobileSession? get session => _session;
  bool get isBusy => _isBusy;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;
  String? get statusMessage => _statusMessage;
  bool get isConnected => _session != null;
  Map<String, dynamic>? get overviewData => _overview;
  List<Map<String, dynamic>> get transactionItems {
    final items = _transactionPage?['items'];
    if (items is! List) return const [];
    return items.whereType<Map>().map(Map<String, dynamic>.from).toList();
  }

  int get transactionTotal => (_transactionPage?['total'] as int?) ?? 0;
  bool get financeLoading => _financeLoading;
  String? get financeError => _financeError;

  ServerLinkState get linkState {
    if (_session == null) return ServerLinkState.notPaired;
    return _unreachable
        ? ServerLinkState.unreachable
        : ServerLinkState.connected;
  }

  /// Time of the last call that returned current data from the server.
  DateTime? get lastSyncAt => _lastSyncAt;
  String? get serverVersion => _serverVersion;

  /// True once the server announced that it accepts manual transactions.
  bool get canWriteTransactions => _capabilities.contains(writeCapability);

  /// True when the server answered but is older than this app expects.
  bool get serverNeedsUpdate =>
      _session != null && _serverVersion != null && !canWriteTransactions;

  List<ServerAccount> get accounts => _accounts;
  List<ServerAccount> get manualAccounts =>
      _accounts.where((account) => account.manualEntries).toList();
  List<ServerCategory> get categories => _categories;
  List<ServerContract> get contracts => _contracts;
  bool get contractsLoading => _contractsLoading;
  String? get contractsError => _contractsError;
  int? get filterAccountId => _filterAccountId;
  int? get filterCategoryId => _filterCategoryId;
  bool get hasTransactionFilter =>
      _filterAccountId != null || _filterCategoryId != null;

  Future<void> restore() async {
    _isLoading = true;
    _errorMessage = null;
    _notifyIfMounted();
    try {
      _session = await _apiClient.loadSession();
    } catch (_) {
      // A stored session that cannot be read (for example after restoring a
      // device backup without its key) can never work again. Remove it so
      // the app does not keep failing on every start.
      _session = null;
      try {
        await _apiClient.discardSession();
      } catch (_) {
        // Nothing else can be done; pairing again overwrites the entry.
      }
      _errorMessage =
          'Die gespeicherte Sitzung konnte nicht gelesen werden. '
          'Bitte richte die Verbindung erneut ein.';
    }
    if (_session != null) await _synchronize();
    _isLoading = false;
    _notifyIfMounted();
  }

  Future<bool> pair({
    required String serverUrl,
    required String pairingSecret,
    required String deviceName,
  }) async {
    _isBusy = true;
    _errorMessage = null;
    _statusMessage = null;
    _notifyIfMounted();
    try {
      _session = await _apiClient.pair(
        serverUrl: serverUrl,
        pairingSecret: pairingSecret,
        deviceName: deviceName,
      );
      _unreachable = false;
      _statusMessage = 'Gerät wurde sicher mit Kassensturz gekoppelt.';
      await _synchronize();
      return true;
    } catch (error) {
      _errorMessage = describeMobileError(error);
      await _clearLocalSessionIfExpired(error);
      return false;
    } finally {
      _isBusy = false;
      _notifyIfMounted();
    }
  }

  Future<bool> checkServer(String serverUrl) async {
    _isBusy = true;
    _errorMessage = null;
    _statusMessage = null;
    _notifyIfMounted();
    try {
      final result = await _apiClient.health(serverUrl: serverUrl);
      final server = result['server'];
      final serverName = server is Map ? server['name'] : null;
      _statusMessage = serverName is String
          ? 'Server gefunden: $serverName.'
          : 'Kassensturz-Server erfolgreich geprüft.';
      return true;
    } catch (error) {
      _errorMessage = describeMobileError(error);
      return false;
    } finally {
      _isBusy = false;
      _notifyIfMounted();
    }
  }

  /// Tests the saved connection and reloads all data when it works.
  Future<bool> checkConnection() async {
    _isBusy = true;
    _errorMessage = null;
    _statusMessage = null;
    _notifyIfMounted();
    try {
      final reachable = await _synchronize();
      if (reachable) {
        _statusMessage = _serverVersion == null
            ? 'Verbindung erfolgreich geprüft.'
            : 'Verbunden mit Kassensturz $_serverVersion.';
      } else {
        _errorMessage = _financeError;
      }
      return reachable;
    } finally {
      _isBusy = false;
      _notifyIfMounted();
    }
  }

  /// Signs this device out on the server and removes the local session.
  Future<void> logout() async {
    _isBusy = true;
    _errorMessage = null;
    _statusMessage = null;
    _notifyIfMounted();
    try {
      await _apiClient.logout();
      _statusMessage = 'Dieses Gerät wurde abgemeldet.';
    } catch (error) {
      _errorMessage =
          '${describeMobileError(error)} '
          'Die lokale Sitzung wurde trotzdem entfernt.';
    } finally {
      _session = await _apiClient.loadSession();
      if (_session == null) _forgetServerData();
      _isBusy = false;
      _notifyIfMounted();
    }
  }

  Future<void> loadFinancialData() async {
    await _synchronize();
  }

  /// Reloads when the app returns to the foreground and the data is older
  /// than [maxAge]. Also the moment a connection that was lost is retried.
  Future<void> refreshIfStale({
    Duration maxAge = const Duration(minutes: 1),
  }) async {
    if (_session == null || _financeLoading || _isBusy) return;
    final last = _lastSyncAt;
    if (last != null && _clock().difference(last) < maxAge) return;
    await _synchronize();
  }

  /// Loads identity, overview, transactions and reference lists. Returns
  /// false when the server could not be reached or the session ended.
  Future<bool> _synchronize() async {
    if (_session == null) return false;
    _financeLoading = true;
    _financeError = null;
    _notifyIfMounted();
    Object? failure;
    try {
      final identity = await _read(_apiClient.me);
      _applyIdentity(identity);
    } catch (error) {
      failure = error;
    }
    if (failure == null) {
      try {
        _overview = await _read(_apiClient.overview);
      } catch (error) {
        failure = error;
      }
      try {
        _transactionPage = await _read(_loadTransactionPage);
      } catch (error) {
        failure ??= error;
      }
      if (canWriteTransactions) {
        try {
          final results = await Future.wait([
            _read(_apiClient.accounts),
            _read(_apiClient.categories),
          ]);
          _accounts = ServerAccount.listFrom(results[0]);
          _categories = ServerCategory.listFrom(results[1]);
        } catch (error) {
          failure ??= error;
        }
      }
    }
    if (failure == null) {
      _unreachable = false;
      _lastSyncAt = _clock();
    } else {
      _unreachable = isConnectivityFailure(failure);
      _financeError = describeMobileError(failure);
      await _clearLocalSessionIfExpired(failure);
    }
    _financeLoading = false;
    _notifyIfMounted();
    return failure == null;
  }

  void _applyIdentity(Map<String, dynamic> identity) {
    final server = identity['server'];
    final version = server is Map ? server['version'] : null;
    _serverVersion = version is String ? version : null;
    final capabilities = identity['capabilities'];
    _capabilities = capabilities is List
        ? capabilities.whereType<String>().toSet()
        : const {};
  }

  Future<Map<String, dynamic>> _loadTransactionPage() => _apiClient
      .transactions(accountId: _filterAccountId, categoryId: _filterCategoryId);

  /// Read calls change nothing on the server, so one automatic repetition
  /// after a transport failure is safe.
  Future<Map<String, dynamic>> _read(
    Future<Map<String, dynamic>> Function() call,
  ) async {
    try {
      return await call();
    } on MobileNetworkException {
      await Future<void>.delayed(_readRetryDelay);
      return call();
    }
  }

  Future<void> loadMoreTransactions() async {
    if (_session == null || _financeLoading) return;
    final current = _transactionPage;
    if (current == null) {
      await loadFinancialData();
      return;
    }
    final offset =
        (current['offset'] as int? ?? 0) + (current['limit'] as int? ?? 50);
    if (offset >= transactionTotal) return;
    _financeLoading = true;
    _financeError = null;
    _notifyIfMounted();
    try {
      final next = await _read(
        () => _apiClient.transactions(
          offset: offset,
          accountId: _filterAccountId,
          categoryId: _filterCategoryId,
        ),
      );
      final combined = <Map<String, dynamic>>[
        ...transactionItems,
        if (next['items'] is List)
          ...List<Map<String, dynamic>>.from(
            (next['items'] as List).whereType<Map>().map(
              Map<String, dynamic>.from,
            ),
          ),
      ];
      _transactionPage = {
        ...next,
        'items': combined,
        'offset': 0,
        'limit': combined.length,
      };
      _unreachable = false;
    } catch (error) {
      await _recordReadFailure(error);
    } finally {
      _financeLoading = false;
      _notifyIfMounted();
    }
  }

  Future<void> refreshTransactions() async {
    if (_session == null) return;
    _financeLoading = true;
    _financeError = null;
    _notifyIfMounted();
    try {
      _transactionPage = await _read(_loadTransactionPage);
      _unreachable = false;
      _lastSyncAt = _clock();
    } catch (error) {
      await _recordReadFailure(error);
    } finally {
      _financeLoading = false;
      _notifyIfMounted();
    }
  }

  /// Limits the transaction list to one account and/or category.
  Future<void> setTransactionFilter({int? accountId, int? categoryId}) async {
    if (accountId == _filterAccountId && categoryId == _filterCategoryId) {
      return;
    }
    _filterAccountId = accountId;
    _filterCategoryId = categoryId;
    await refreshTransactions();
  }

  Future<void> loadContracts() async {
    if (_session == null || _contractsLoading) return;
    _contractsLoading = true;
    _contractsError = null;
    _notifyIfMounted();
    try {
      _contracts = ServerContract.listFrom(await _read(_apiClient.contracts));
      _unreachable = false;
    } catch (error) {
      _unreachable = isConnectivityFailure(error);
      _contractsError = describeMobileError(error);
      await _clearLocalSessionIfExpired(error);
    } finally {
      _contractsLoading = false;
      _notifyIfMounted();
    }
  }

  /// Creates a manual transaction. Returns null on success, otherwise the
  /// message to show. The caller keeps [fields] unchanged for a retry so the
  /// server recognises the repetition by its `client_request_id`.
  Future<String?> createTransaction(Map<String, dynamic> fields) =>
      _write(() => _apiClient.createTransaction(fields));

  Future<String?> updateTransaction(int id, Map<String, dynamic> changes) =>
      _write(() => _apiClient.updateTransaction(id, changes));

  Future<String?> deleteTransaction(int id) =>
      _write(() => _apiClient.deleteTransaction(id));

  /// Write calls are never repeated automatically. After success all views
  /// are reloaded so balances and lists show what the server stored.
  Future<String?> _write(Future<Object?> Function() call) async {
    if (_session == null) {
      return describeMobileError(const MobileSessionExpiredException());
    }
    if (!canWriteTransactions) {
      return 'Der Server unterstützt das Speichern noch nicht. '
          'Bitte aktualisiere Kassensturz in Home Assistant.';
    }
    try {
      await call();
    } catch (error) {
      _unreachable = isConnectivityFailure(error);
      await _clearLocalSessionIfExpired(error);
      _notifyIfMounted();
      return describeMobileError(error);
    }
    await _synchronize();
    return null;
  }

  Future<void> _recordReadFailure(Object error) async {
    _unreachable = isConnectivityFailure(error);
    _financeError = describeMobileError(error);
    await _clearLocalSessionIfExpired(error);
  }

  Future<void> _clearLocalSessionIfExpired(Object error) async {
    if (error is! MobileSessionExpiredException) return;
    _session = await _apiClient.loadSession();
    if (_session == null) {
      _forgetServerData();
      _statusMessage = describeMobileError(error);
    }
  }

  void _forgetServerData() {
    _overview = null;
    _transactionPage = null;
    _financeError = null;
    _unreachable = false;
    _lastSyncAt = null;
    _capabilities = const {};
    _serverVersion = null;
    _accounts = const [];
    _categories = const [];
    _contracts = const [];
    _contractsError = null;
    _filterAccountId = null;
    _filterCategoryId = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _apiClient.close();
    super.dispose();
  }
}
