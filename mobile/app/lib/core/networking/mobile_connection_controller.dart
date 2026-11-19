import 'dart:async';

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
    Duration syncPollInterval = const Duration(seconds: 3),
    DateTime Function()? clock,
  }) : _apiClient = apiClient,
       _readRetryDelay = readRetryDelay,
       _syncPollInterval = syncPollInterval,
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
  static const ownBudgetCapability = 'budgets.own';
  static const contractCapability = 'contracts.write';
  static const affordCapability = 'afford';
  static const taxCapability = 'tax';
  static const receiptsCapability = 'receipts';
  static const sharingCapability = 'household.sharing';
  static const warrantyCapability = 'warranty';
  static const accountsCapability = 'accounts.write';
  static const syncCapability = 'sync';
  static const triageCapability = 'triage';
  static const newsCapability = 'news';
  static const netWorthCapability = 'networth';
  static const papersCapability = 'papers';
  static const suggestCapability = 'budgets.suggest';
  static const plansCapability = 'plans';
  static const projectsCapability = 'projects';
  static const chargingCapability = 'charging';
  static const loansCapability = 'loans';
  static const changesCapability = 'changes';
  static const partsCapability = 'parts';
  static const bankRenewCapability = 'banks.renew';
  static const accountValueCapability = 'accounts.value';
  static const syncTanCapability = 'sync.tan';
  static const yearCapability = 'year';

  final MobileApiClient _apiClient;
  final Duration _readRetryDelay;
  final Duration _syncPollInterval;
  ServerSyncStatus? _syncStatus;
  String? _answeredQid;
  int _triageTotal = 0;
  ServerNews? _news;
  int _triageExpenseCents = 0;
  bool _bankSyncRunning = false;
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
  bool _readOnly = false;
  List<ServerAccount> _accounts = const [];
  List<ServerCategory> _categories = const [];
  List<ServerContract> _contracts = const [];
  bool _contractsLoading = false;
  String? _contractsError;
  int? _filterAccountId;
  int? _filterCategoryId;
  String _filterSearch = '';
  String? _filterKind;
  String? _viewPart;
  String? _statsMonth;
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

  /// True when the server stores a tax kind per transaction.
  bool get canTagTax => _capabilities.contains(taxCapability);

  /// True when the server stores the end of a warranty per transaction.
  bool get canSetWarranty => _capabilities.contains(warrantyCapability);

  /// True when the server reports the net worth over the last months.
  bool get canShowNetWorthHistory => _capabilities.contains(netWorthCapability);

  /// Net worth at month ends and today, oldest first; empty when unknown.
  Future<List<({DateTime day, int cents})>> loadNetWorthHistory() async {
    try {
      final response = await _read(_apiClient.netWorthHistory);
      final raw = response['history'];
      return [
        if (raw is List)
          for (final entry in raw.whereType<Map>())
            if (entry['cents'] is int &&
                DateTime.tryParse('${entry['date']}') != null)
              (
                day: DateTime.parse('${entry['date']}'),
                cents: entry['cents'] as int,
              ),
      ];
    } catch (error) {
      await _describeFailure(error);
      return const [];
    }
  }

  /// True when the server shows the tax overview and warranties.
  bool get canShowPapers => _capabilities.contains(papersCapability);

  /// What arrived since this device last marked it as read; null when
  /// nothing did or the server is older.
  ServerNews? get news => _news;

  /// Marks the news as read on the server and hides them here.
  Future<void> markNewsRead() async {
    _news = null;
    _notifyIfMounted();
    try {
      await _apiClient.markNewsSeen();
    } catch (error) {
      // They simply show up again on the next load.
      await _describeFailure(error);
    }
  }

  /// Tax overview and warranties. Either the data or the message is set.
  Future<({PapersOverview? data, String? error})> loadPapers({
    int? year,
  }) async {
    try {
      final response = await _read(() => _apiClient.papers(year: year));
      return (data: PapersOverview.fromJson(response), error: null);
    } catch (error) {
      return (data: null, error: await _describeFailure(error));
    }
  }

  /// True when the server lists transactions that still need a category.
  bool get canTriage => _capabilities.contains(triageCapability);

  /// True when the server proposes budgets from past spending.
  bool get canSuggestBudgets => _capabilities.contains(suggestCapability);

  /// Transactions without a real category as of the last load.
  int get triageTotal => _triageTotal;

  /// Spending that sits in no real category, in cents.
  int get triageExpenseCents => _triageExpenseCents;

  /// The next transactions to sort. Either the list or the message is set.
  Future<({List<ServerTransaction> items, int total, String? error})>
  loadTriage() async {
    try {
      final response = await _read(_apiClient.triage);
      _applyTriage(response);
      _notifyIfMounted();
      return (
        items: ServerTransaction.listFrom(response),
        total: _triageTotal,
        error: null,
      );
    } catch (error) {
      return (
        items: const <ServerTransaction>[],
        total: _triageTotal,
        error: await _describeFailure(error),
      );
    }
  }

  void _applyTriage(Map<String, dynamic> response) {
    final total = response['total'];
    final spent = response['expense_cents'];
    _triageTotal = total is int ? total : 0;
    _triageExpenseCents = spent is int ? spent : 0;
  }

  /// Budgets proposed from the last full months.
  Future<({List<BudgetSuggestion> items, int months, String? error})>
  loadBudgetSuggestions() async {
    try {
      final response = await _read(_apiClient.budgetSuggestions);
      final months = response['months'];
      return (
        items: BudgetSuggestion.listFrom(response),
        months: months is int ? months : 0,
        error: null,
      );
    } catch (error) {
      return (
        items: const <BudgetSuggestion>[],
        months: 0,
        error: await _describeFailure(error),
      );
    }
  }

  /// True when the server reports and starts fetching from the banks.
  bool get canSyncBanks => _capabilities.contains(syncCapability);

  /// State of the bank fetch as of the last load; null on older servers.
  ServerSyncStatus? get syncStatus => _syncStatus;

  /// True while a fetch started from this app is running.
  bool get bankSyncRunning => _bankSyncRunning;

  DateTime get now => _clock();

  /// Whether values of deposits and loans can be entered on this phone.
  bool get canEditAccountValues =>
      _capabilities.contains(accountValueCapability) && !isReadOnly;

  /// Enters today's value of a deposit or the remaining debt of a loan.
  /// Null when it worked, otherwise the message to show.
  Future<String?> setAccountValue(int accountId, int cents) => _write(
    () => _apiClient.setAccountValue(accountId, cents),
    capability: accountValueCapability,
  );

  /// Whether an expiring bank consent can be renewed from this phone.
  bool get canRenewBanks =>
      _capabilities.contains(bankRenewCapability) && !isReadOnly;

  /// Asks the server for the bank's page that renews a consent.
  Future<({String? url, String? error})> startBankRenewal(int id) async {
    try {
      final data = await _apiClient.startBankRenewal(id);
      final url = data['url'];
      if (url is String && url.startsWith('https://')) {
        return (url: url, error: null);
      }
      return (url: null, error: 'Der Server hat keinen Link geliefert.');
    } catch (error) {
      return (url: null, error: await _describeFailure(error));
    }
  }

  /// Hands the address from the browser to the server. Null when the consent
  /// is renewed, otherwise the message to show.
  Future<String?> completeBankRenewal(String address) => _write(
    () => _apiClient.completeBankRenewal(address),
    capability: bankRenewCapability,
  );

  /// Fetches from the banks and reloads everything afterwards. Returns the
  /// sentence to show: what arrived, or why nothing happened.
  Future<String> startBankSync() async {
    if (_bankSyncRunning) return 'Der Abruf läuft schon.';
    return _followBankSync(
      () => _apiClient.startSync(interactive: canAnswerBanks),
    );
  }

  /// Whether this phone can answer what a bank asks during a fetch.
  bool get canAnswerBanks =>
      _capabilities.contains(syncTanCapability) && !isReadOnly;

  /// What a bank asks right now; null once it was answered from here.
  BankQuestion? get bankQuestion {
    final question = canAnswerBanks ? _syncStatus?.question : null;
    return question?.qid == _answeredQid ? null : question;
  }

  /// Answers the bank's question, or gives the fetch up with [cancel]. Null
  /// when the server took it, otherwise the message to show.
  Future<String?> answerBankQuestion(
    String qid, {
    String? value,
    bool cancel = false,
  }) async {
    try {
      final answered = await _apiClient.answerSync(
        qid,
        value: value,
        cancel: cancel,
      );
      _answeredQid = qid;
      _syncStatus = ServerSyncStatus.fromJson(answered);
      _notifyIfMounted();
    } catch (error) {
      return _describeFailure(error);
    }
    // After a restart of the app nothing is watching the fetch yet.
    if (!_bankSyncRunning) {
      unawaited(_followBankSync(() => _read(_apiClient.syncStatus)));
    }
    return null;
  }

  Future<String> _followBankSync(
    Future<Map<String, dynamic>> Function() first,
  ) async {
    _bankSyncRunning = true;
    _notifyIfMounted();
    try {
      var state = ServerSyncStatus.fromJson(await first());
      // Up to two minutes; a bank that takes longer finishes on the server.
      // A question of the bank stays open for five minutes, so wait longer.
      var rounds = 40;
      for (var round = 0; state.running && round < rounds; round += 1) {
        if (state.question != null) rounds = 140;
        _syncStatus = state;
        _notifyIfMounted();
        await Future<void>.delayed(_syncPollInterval);
        if (_disposed) return '';
        state = ServerSyncStatus.fromJson(await _read(_apiClient.syncStatus));
      }
      _syncStatus = state;
      await _synchronize();
      if (state.running) {
        return 'Der Abruf läuft noch. Zieh die Seite gleich noch einmal '
            'herunter.';
      }
      if (state.errors.isNotEmpty) return state.errors.join('\n');
      return switch (state.added) {
        0 => 'Abgerufen. Es gibt keine neuen Buchungen.',
        1 => 'Abgerufen: eine neue Buchung.',
        _ => 'Abgerufen: ${state.added} neue Buchungen.',
      };
    } catch (error) {
      return _describeFailure(error);
    } finally {
      _bankSyncRunning = false;
      _notifyIfMounted();
    }
  }

  /// True when the app may add a cash account on the server.
  bool get canCreateAccounts => _capabilities.contains(accountsCapability);

  /// True when the server keeps receipts for transactions.
  bool get canUseReceipts => _capabilities.contains(receiptsCapability);

  /// True when expenses can be shared with the household.
  bool get canShareExpenses => _capabilities.contains(sharingCapability);

  /// Whether the server shows the log of changes to this phone.
  bool get canShowChanges =>
      _capabilities.contains(changesCapability) && !isReadOnly;

  /// Whether the server shows projects to this phone.
  bool get canShowProjects => _capabilities.contains(projectsCapability);

  /// Whether the server offers the year in review.
  bool get canShowYear => _capabilities.contains(yearCapability);

  /// Whether the server knows charging sessions from Ladecockpit.
  bool get canShowCharging => _capabilities.contains(chargingCapability);

  /// Whether the server computes repayment plans of loans for this phone.
  bool get canShowLoans => _capabilities.contains(loansCapability);

  /// Whether this phone can tick alerts off and plan expenses and incomes.
  bool get canManagePlans =>
      _capabilities.contains(plansCapability) && !isReadOnly;

  /// True once the server announced that it accepts manual transactions.
  bool get canWriteTransactions => _capabilities.contains(writeCapability);

  /// True when this phone belongs to a child of the household: it shows
  /// that person's own money and cannot change anything.
  bool get isReadOnly => _readOnly;

  /// True when the server answered but is older than this app expects. A
  /// read-only phone lacks the same abilities on purpose.
  bool get serverNeedsUpdate =>
      _session != null &&
      _serverVersion != null &&
      !canWriteTransactions &&
      !_readOnly;

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

  /// True when this person can keep budgets that only count own accounts.
  bool get canEditOwnBudgets => _capabilities.contains(ownBudgetCapability);

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

  /// 'own' shows only this person's accounts, 'shared' only the common
  /// ones, null both. Applies to the transactions and the analysis.
  String? get viewPart => _viewPart;

  /// Whether the transactions and the analysis can be split into what
  /// belongs to this person and what the household shares.
  bool get canFilterParts {
    if (!_capabilities.contains(partsCapability) || isReadOnly) return false;
    final household = _overview?['household'];
    return household is Map &&
        household['private_accounts'] == true &&
        household['person'] is Map;
  }

  Future<void> setViewPart(String? part) async {
    if (part == _viewPart) return;
    _viewPart = part;
    final stats = _stats != null;
    await refreshTransactions();
    if (stats) await loadStats(month: _statsMonth);
  }

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
      if (canSyncBanks) {
        try {
          _syncStatus = ServerSyncStatus.fromJson(
            await _read(_apiClient.syncStatus),
          );
        } catch (_) {
          // The figures are complete without it; the line simply stays as is.
        }
      } else {
        _syncStatus = null;
      }
      if (_capabilities.contains(newsCapability)) {
        try {
          final found = ServerNews.fromJson(await _read(_apiClient.news));
          _news = found.count > 0 ? found : null;
        } catch (_) {
          // Nice to have; the figures do not depend on it.
        }
      } else {
        _news = null;
      }
      if (canTriage) {
        try {
          _applyTriage(await _read(() => _apiClient.triage(limit: 1)));
        } catch (_) {
          // Only the hint on the budget page depends on it.
        }
      } else {
        _triageTotal = 0;
        _triageExpenseCents = 0;
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
    final household = identity['household'];
    _readOnly = household is Map && household['read_only'] == true;
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
      part: canFilterParts ? _viewPart : null,
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
    _statsMonth = month;
    _statsLoading = true;
    _statsError = null;
    _notifyIfMounted();
    try {
      final part = canFilterParts ? _viewPart : null;
      _stats = await _read(() => _apiClient.stats(month: month, part: part));
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
  /// Adds an account for entries made by hand. Returns null on success,
  /// otherwise the message to show.
  Future<String?> createCashAccount(String name, {int? balanceCents}) => _write(
    () => _apiClient.createCashAccount(name, balanceCents: balanceCents),
    capability: accountsCapability,
  );

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

  /// Receipts of one transaction. Either the list or the message is set.
  Future<({List<ServerReceipt> items, int max, String? error})> loadReceipts(
    int transactionId,
  ) async {
    try {
      final response = await _apiClient.receipts(transactionId);
      final max = response['max'];
      return (
        items: ServerReceipt.listFrom(response),
        max: max is int ? max : 10,
        error: null,
      );
    } catch (error) {
      return (
        items: const <ServerReceipt>[],
        max: 10,
        error: await _describeFailure(error),
      );
    }
  }

  /// Attaches a file to a transaction. Returns null on success, otherwise
  /// the message to show. Nothing is kept on the device.
  Future<String?> addReceipt(
    int transactionId,
    String filename,
    Uint8List bytes,
  ) async {
    try {
      await _apiClient.uploadReceipt(transactionId, filename, bytes);
      return null;
    } catch (error) {
      return _describeFailure(error);
    }
  }

  Future<String?> deleteReceipt(int receiptId) async {
    try {
      await _apiClient.deleteReceipt(receiptId);
      return null;
    } catch (error) {
      return _describeFailure(error);
    }
  }

  /// How one expense is shared with the household.
  Future<({Map<String, dynamic>? share, String? error})> loadShare(
    int id,
  ) async {
    try {
      return (share: await _apiClient.transactionShare(id), error: null);
    } catch (error) {
      return (share: null, error: await _describeFailure(error));
    }
  }

  /// Shared expenses of this person, what is open, and the payments.
  Future<({Map<String, dynamic>? data, String? error})> loadSharing() async {
    try {
      return (data: await _read(_apiClient.householdSharing), error: null);
    } catch (error) {
      return (data: null, error: await _describeFailure(error));
    }
  }

  /// Records that this person paid someone back. Null when it worked.
  Future<String?> addSettlement(int toPersonId, int cents, String note) async {
    try {
      await _apiClient.addSettlement(toPersonId, cents, note);
      return null;
    } catch (error) {
      return _describeFailure(error);
    }
  }

  /// Shares an expense with the household or takes that back.
  Future<({Map<String, dynamic>? share, String? error})> setShare(
    int id, {
    required bool shared,
  }) async {
    try {
      final share = await _apiClient.setTransactionShare(id, shared: shared);
      return (share: share, error: null);
    } catch (error) {
      return (share: null, error: await _describeFailure(error));
    }
  }

  /// The file of one receipt, held in memory only while it is shown.
  Future<({Uint8List? bytes, String? error})> receiptBytes(
    int receiptId,
  ) async {
    try {
      return (bytes: await _apiClient.receiptBytes(receiptId), error: null);
    } catch (error) {
      return (bytes: null, error: await _describeFailure(error));
    }
  }

  Future<String> _describeFailure(Object error) async {
    _unreachable = isConnectivityFailure(error);
    await _clearLocalSessionIfExpired(error);
    _notifyIfMounted();
    return describeMobileError(error);
  }

  /// Sets or, with null, removes the monthly budget of a category. Returns
  /// null on success, otherwise the message to show.
  Future<String?> setBudget(
    int categoryId,
    int? limitCents, {
    bool own = false,
  }) => _write(
    () => _apiClient.setBudget(categoryId, limitCents, own: own),
    capability: own ? ownBudgetCapability : budgetCapability,
  );

  /// Reads something once with one retry on a network hiccup; the error is
  /// the message to show.
  Future<({Map<String, dynamic>? data, String? error})> readOnce(
    Future<Map<String, dynamic>> Function(MobileApiClient api) call,
  ) async {
    try {
      return (data: await _read(() => call(_apiClient)), error: null);
    } catch (error) {
      return (data: null, error: await _describeFailure(error));
    }
  }

  /// Puts a transaction into a project or takes it out. Null when it worked.
  Future<String?> setTransactionProject(int transactionId, int? projectId) =>
      _write(
        () => _apiClient.setTransactionProject(transactionId, projectId),
        capability: projectsCapability,
      );

  /// Hides a checked anomaly. Null when it worked, otherwise the message.
  Future<String?> acknowledgeAlert(String key) => _write(
    () => _apiClient.acknowledgeAlert(key),
    capability: plansCapability,
  );

  /// Plans a one-off expense on an account this person sees.
  Future<String?> createPlanned({
    required String label,
    required int cents,
    required String dueDate,
    required int accountId,
  }) => _write(
    () => _apiClient.createPlanned(
      label: label,
      cents: cents,
      dueDate: dueDate,
      accountId: accountId,
    ),
    capability: plansCapability,
  );

  /// Notes that money comes back for an expense.
  Future<String?> createExpected(int transactionId, int cents) => _write(
    () => _apiClient.createExpected(transactionId, cents),
    capability: plansCapability,
  );

  /// Ticks a planned expense or an expected income off, or drops it.
  Future<String?> settlePlan(String kind, int id, String action) => _write(
    () => _apiClient.settlePlan(kind, id, action),
    capability: plansCapability,
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
    _readOnly = false;
    _accounts = const [];
    _categories = const [];
    _contracts = const [];
    _contractsError = null;
    _filterAccountId = null;
    _filterCategoryId = null;
    _filterSearch = '';
    _filterKind = null;
    _viewPart = null;
    _statsMonth = null;
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
