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
  static const searchCapability = 'transactions.search';
  static const statsCapability = 'stats';
  static const budgetCapability = 'budgets.write';
  static const contractCapability = 'contracts.write';
  static const affordCapability = 'afford';

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
  String _filterSearch = '';
  String? _filterKind;
  Map<String, dynamic>? _stats;
  bool _statsLoading = false;
  String? _statsError;
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

  /// True once the server answers "can I afford this?".
  bool get canAfford => _capabilities.contains(affordCapability);

  /// Asks the server what a purchase would mean. Either the answer or the
  /// message to show is set. Nothing is stored.
  Future<({Map<String, dynamic>? answer, String? error})> afford(
    int amountCents,
  ) async {
    if (_session == null) {
      return (
        answer: null,
        error: describeMobileError(const MobileSessionExpiredException()),
      );
    }
    try {
      return (answer: await _apiClient.afford(amountCents), error: null);
    } catch (error) {
      _unreachable = isConnectivityFailure(error);
      await _clearLocalSessionIfExpired(error);
      _notifyIfMounted();
      return (answer: null, error: describeMobileError(error));
    }
  }

  /// True once the server accepts contract changes and builds letters.
  bool get canEditContracts => _capabilities.contains(contractCapability);

  /// True once the server accepts budget changes from the app.
  bool get canEditBudgets => _capabilities.contains(budgetCapability);

  /// True once the server offers the figures for the analysis page.
  bool get canShowStats => _capabilities.contains(statsCapability);

  /// The analysis last loaded with [loadStats], as the server sent it.
  Map<String, dynamic>? get stats => _stats;
  bool get statsLoading => _statsLoading;
  String? get statsError => _statsError;

  /// True once the server can search transactions and split them by kind.
  bool get canSearchTransactions => _capabilities.contains(searchCapability);

  int? get filterAccountId => _filterAccountId;
  int? get filterCategoryId => _filterCategoryId;
  String get filterSearch => _filterSearch;

  /// 'in' for income, 'out' for expenses, null for both.
  String? get filterKind => _filterKind;
  bool get hasTransactionFilter =>
      _filterAccountId != null ||
      _filterCategoryId != null ||
      _filterSearch.isNotEmpty ||
      _filterKind != null;

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

  /// An older server ignores unknown parameters and would answer with the
  /// unfiltered list, so search and kind are only sent when it knows them.
  Future<Map<String, dynamic>> _loadTransactionPage({int offset = 0}) {
    return _apiClient.transactions(
      offset: offset,
      accountId: _filterAccountId,
      categoryId: _filterCategoryId,
      search: canSearchTransactions ? _filterSearch : null,
      kind: canSearchTransactions ? _filterKind : null,
    );
  }

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
      final next = await _read(() => _loadTransactionPage(offset: offset));
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

  /// Searches counterparty, purpose and note. Empty text ends the search.
  Future<void> setTransactionSearch(String text) async {
    final search = text.trim();
    if (search == _filterSearch) return;
    _filterSearch = search;
    await refreshTransactions();
  }

  /// 'in' shows income only, 'out' expenses only, null both.
  Future<void> setTransactionKind(String? kind) async {
    if (kind == _filterKind) return;
    _filterKind = kind;
    await refreshTransactions();
  }

  /// Loads the analysis for [month] ('YYYY-MM'); null is the current month.
  /// The previous analysis stays visible until the new one has arrived.
  Future<void> loadStats({String? month}) async {
    if (_session == null || _statsLoading || !canShowStats) return;
    _statsLoading = true;
    _statsError = null;
    _notifyIfMounted();
    try {
      _stats = await _read(() => _apiClient.stats(month: month));
      _unreachable = false;
    } catch (error) {
      _unreachable = isConnectivityFailure(error);
      _statsError = describeMobileError(error);
      await _clearLocalSessionIfExpired(error);
    } finally {
      _statsLoading = false;
      _notifyIfMounted();
    }
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

  /// After a category change the server applies it to similar transactions;
  /// [lastAlsoChanged] says how many followed the last update.
  Future<String?> updateTransaction(int id, Map<String, dynamic> changes) {
    _lastAlsoChanged = 0;
    return _write(() async {
      final response = await _apiClient.updateTransaction(id, changes);
      final count = response['also_changed'];
      _lastAlsoChanged = count is int ? count : 0;
      return response;
    });
  }

  int get lastAlsoChanged => _lastAlsoChanged;
  int _lastAlsoChanged = 0;

  Future<String?> deleteTransaction(int id) =>
      _write(() => _apiClient.deleteTransaction(id));

  /// Changes a contract and reloads the contract list. Returns null on
  /// success, otherwise the message to show.
  Future<String?> updateContract(
    String key,
    Map<String, dynamic> changes,
  ) async {
    final error = await _write(
      () => _apiClient.updateContract(key, changes),
      capability: contractCapability,
    );
    if (error == null) await loadContracts();
    return error;
  }

  /// Fetches the cancellation letter. Either the letter or the message to
  /// show is set. Nothing is stored on the server.
  Future<({Map<String, dynamic>? letter, String? error})> contractLetter(
    String key, {
    String mode = 'ordentlich',
    String? date,
  }) async {
    if (_session == null) {
      return (
        letter: null,
        error: describeMobileError(const MobileSessionExpiredException()),
      );
    }
    if (!canEditContracts) {
      return (
        letter: null,
        error:
            'Der Server kann noch keine Kündigungsschreiben liefern. '
            'Bitte aktualisiere Kassensturz in Home Assistant.',
      );
    }
    try {
      final letter = await _apiClient.contractLetter(
        key,
        mode: mode,
        date: date,
      );
      return (letter: letter, error: null);
    } catch (error) {
      _unreachable = isConnectivityFailure(error);
      await _clearLocalSessionIfExpired(error);
      _notifyIfMounted();
      return (letter: null, error: describeMobileError(error));
    }
  }

  /// Sets or, with null, removes the monthly budget of a category. Returns
  /// null on success, otherwise the message to show.
  Future<String?> setBudget(int categoryId, int? limitCents) => _write(
    () => _apiClient.setBudget(categoryId, limitCents),
    capability: budgetCapability,
  );

  /// Write calls are never repeated automatically. After success all views
  /// are reloaded so balances and lists show what the server stored.
  Future<String?> _write(
    Future<Object?> Function() call, {
    String capability = writeCapability,
  }) async {
    if (_session == null) {
      return describeMobileError(const MobileSessionExpiredException());
    }
    if (!_capabilities.contains(capability)) {
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
    _filterSearch = '';
    _filterKind = null;
    _stats = null;
    _statsError = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _apiClient.close();
    super.dispose();
  }
}
