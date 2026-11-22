import 'dart:async';

import 'package:flutter/foundation.dart';

import 'mobile_api_client.dart';
import 'mobile_error_messages.dart';
import 'mobile_models.dart';
import 'mobile_session.dart';
import 'mobile_session_store.dart';

/// Was die App gerade über ihre Verbindung zum Kassensturz-Server weiß.
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
  static const reportCapability = 'report';

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

  /// Zeitpunkt des letzten Aufrufs, der aktuelle Daten vom Server lieferte.
  DateTime? get lastSyncAt => _lastSyncAt;
  String? get serverVersion => _serverVersion;

  /// True, wenn der Server je Umsatz eine Steuerart speichert.
  bool get canTagTax => _capabilities.contains(taxCapability);

  /// True, wenn der Server je Umsatz das Ende einer Garantie speichert.
  bool get canSetWarranty => _capabilities.contains(warrantyCapability);

  /// True, wenn der Server das Vermögen über die letzten Monate meldet.
  bool get canShowNetWorthHistory => _capabilities.contains(netWorthCapability);

  /// Vermögen an Monatsenden und heute, das Älteste zuerst; leer, wenn unbekannt.
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

  /// True, wenn der Server die Steuerübersicht und Garantien zeigt.
  bool get canShowPapers => _capabilities.contains(papersCapability);

  /// Was eingetroffen ist, seit dieses Gerät es zuletzt als gelesen markiert hat; null, wenn
  /// nichts kam oder der Server älter ist.
  ServerNews? get news => _news;

  /// Markiert die Neuigkeiten auf dem Server als gelesen und blendet sie hier aus.
  Future<void> markNewsRead() async {
    _news = null;
    _notifyIfMounted();
    try {
      await _apiClient.markNewsSeen();
    } catch (error) {
      // Sie erscheinen beim nächsten Laden einfach wieder.
      await _describeFailure(error);
    }
  }

  /// Steuerübersicht und Garantien. Entweder die Daten oder die Meldung ist gesetzt.
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

  /// True, wenn der Server Umsätze auflistet, die noch eine Kategorie brauchen.
  bool get canTriage => _capabilities.contains(triageCapability);

  /// True, wenn der Server Budgets aus früheren Ausgaben vorschlägt.
  bool get canSuggestBudgets => _capabilities.contains(suggestCapability);

  /// Umsätze ohne echte Kategorie zum Stand des letzten Ladens.
  int get triageTotal => _triageTotal;

  /// Spending that sits in no real category, in cents.
  int get triageExpenseCents => _triageExpenseCents;

  /// Die nächsten zu sortierenden Umsätze. Entweder die Liste oder die Meldung ist gesetzt.
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

  /// Aus den letzten vollen Monaten vorgeschlagene Budgets.
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

  /// True, wenn der Server den Abruf bei den Banken meldet und startet.
  bool get canSyncBanks => _capabilities.contains(syncCapability);

  /// Zustand des Bankabrufs zum Stand des letzten Ladens; null bei älteren Servern.
  ServerSyncStatus? get syncStatus => _syncStatus;

  /// True, solange ein aus dieser App gestarteter Abruf läuft.
  bool get bankSyncRunning => _bankSyncRunning;

  DateTime get now => _clock();

  /// Ob sich Werte von Geldanlagen und Krediten auf diesem Handy eintragen lassen.
  bool get canEditAccountValues =>
      _capabilities.contains(accountValueCapability) && !isReadOnly;

  /// Trägt den heutigen Wert einer Geldanlage oder die Restschuld eines Kredits ein.
  /// Null, wenn es geklappt hat, sonst die anzuzeigende Meldung.
  Future<String?> setAccountValue(int accountId, int cents) => _write(
    () => _apiClient.setAccountValue(accountId, cents),
    capability: accountValueCapability,
  );

  /// Ob sich eine ablaufende Bank-Einwilligung von diesem Handy aus verlängern lässt.
  bool get canRenewBanks =>
      _capabilities.contains(bankRenewCapability) && !isReadOnly;

  /// Fragt den Server nach der Seite der Bank, die eine Einwilligung verlängert.
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

  /// Übergibt die Adresse aus dem Browser an den Server. Null, wenn die Einwilligung
  /// verlängert ist, sonst die anzuzeigende Meldung.
  Future<String?> completeBankRenewal(String address) => _write(
    () => _apiClient.completeBankRenewal(address),
    capability: bankRenewCapability,
  );

  /// Ruft bei den Banken ab und lädt danach alles neu. Gibt den anzuzeigenden
  /// Satz zurück: was eingetroffen ist oder warum nichts passiert ist.
  Future<String> startBankSync() async {
    if (_bankSyncRunning) return 'Der Abruf läuft schon.';
    return _followBankSync(
      () => _apiClient.startSync(interactive: canAnswerBanks),
    );
  }

  /// Ob dieses Handy beantworten kann, was eine Bank während eines Abrufs fragt.
  bool get canAnswerBanks =>
      _capabilities.contains(syncTanCapability) && !isReadOnly;

  /// Was eine Bank gerade fragt; null, sobald es von hier beantwortet wurde.
  BankQuestion? get bankQuestion {
    final question = canAnswerBanks ? _syncStatus?.question : null;
    return question?.qid == _answeredQid ? null : question;
  }

  /// Beantwortet die Rückfrage der Bank oder gibt den Abruf mit [cancel] auf. Null,
  /// wenn der Server es angenommen hat, sonst die anzuzeigende Meldung.
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
    // Nach einem Neustart der App beobachtet noch niemand den Abruf.
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
      // Bis zu zwei Minuten; eine Bank, die länger braucht, wird auf dem Server fertig.
      // Eine Rückfrage der Bank bleibt fünf Minuten offen, also länger warten.
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

  /// True, wenn die App ein Bargeldkonto auf dem Server anlegen darf.
  bool get canCreateAccounts => _capabilities.contains(accountsCapability);

  /// True, wenn der Server Belege zu Umsätzen aufbewahrt.
  bool get canUseReceipts => _capabilities.contains(receiptsCapability);

  /// True, wenn sich Ausgaben mit dem Haushalt teilen lassen.
  bool get canShareExpenses => _capabilities.contains(sharingCapability);

  /// Ob der Server diesem Handy das Änderungsprotokoll zeigt.
  bool get canShowChanges =>
      _capabilities.contains(changesCapability) && !isReadOnly;

  /// Ob der Server diesem Handy Projekte zeigt.
  bool get canShowProjects => _capabilities.contains(projectsCapability);

  /// Ob der Server den Monatsbericht und das Jahr als PDF schreibt.
  bool get canShowReport => _capabilities.contains(reportCapability);

  /// Ob der Server den Jahresrückblick anbietet.
  bool get canShowYear => _capabilities.contains(yearCapability);

  /// Ob der Server Ladungen aus Ladecockpit kennt.
  bool get canShowCharging => _capabilities.contains(chargingCapability);

  /// Ob der Server für dieses Handy Tilgungspläne von Krediten berechnet.
  bool get canShowLoans => _capabilities.contains(loansCapability);

  /// Ob dieses Handy Hinweise abhaken und Ausgaben und Einnahmen planen kann.
  bool get canManagePlans =>
      _capabilities.contains(plansCapability) && !isReadOnly;

  /// True, sobald der Server angekündigt hat, dass er manuelle Umsätze annimmt.
  bool get canWriteTransactions => _capabilities.contains(writeCapability);

  /// True, wenn dieses Handy einem Kind des Haushalts gehört: Es zeigt
  /// das eigene Geld dieser Person und kann nichts ändern.
  bool get isReadOnly => _readOnly;

  /// True, wenn der Server geantwortet hat, aber älter ist, als diese App erwartet. Einem
  /// Handy nur zum Lesen fehlen dieselben Fähigkeiten absichtlich.
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

  /// True, sobald der Server „Kann ich mir das leisten?“ beantwortet.
  bool get canAfford => _capabilities.contains(affordCapability);

  /// Fragt den Server, was ein Kauf bedeuten würde. Entweder die Antwort oder die
  /// anzuzeigende Meldung ist gesetzt. Nichts wird gespeichert.
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

  /// True, wenn diese Person Budgets führen kann, die nur eigene Konten zählen.
  bool get canEditOwnBudgets => _capabilities.contains(ownBudgetCapability);

  /// True, sobald der Server Vertragsänderungen annimmt und Schreiben erstellt.
  bool get canEditContracts => _capabilities.contains(contractCapability);

  /// True, sobald der Server Budgetänderungen aus der App annimmt.
  bool get canEditBudgets => _capabilities.contains(budgetCapability);

  /// True, sobald der Server die Zahlen für die Auswertungsseite anbietet.
  bool get canShowStats => _capabilities.contains(statsCapability);

  /// Die zuletzt mit [loadStats] geladene Auswertung, wie der Server sie geschickt hat.
  Map<String, dynamic>? get stats => _stats;
  bool get statsLoading => _statsLoading;
  String? get statsError => _statsError;

  /// True, sobald der Server Umsätze durchsuchen und nach Art trennen kann.
  bool get canSearchTransactions => _capabilities.contains(searchCapability);

  int? get filterAccountId => _filterAccountId;
  int? get filterCategoryId => _filterCategoryId;
  String get filterSearch => _filterSearch;

  /// 'in' für Einnahmen, 'out' für Ausgaben, null für beides.
  String? get filterKind => _filterKind;

  /// 'own' zeigt nur die Konten dieser Person, 'shared' nur die gemeinsamen,
  /// null beides. Gilt für die Umsätze und die Auswertung.
  String? get viewPart => _viewPart;

  /// Ob sich Umsätze und Auswertung in das trennen lassen, was dieser Person
  /// gehört, und das, was der Haushalt teilt.
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
      // Eine gespeicherte Sitzung, die sich nicht lesen lässt (zum Beispiel nach dem
      // Wiederherstellen einer Gerätesicherung ohne ihren Schlüssel), kann nie wieder
      // funktionieren. Sie entfernen, damit die App nicht bei jedem Start scheitert.
      _session = null;
      try {
        await _apiClient.discardSession();
      } catch (_) {
        // Mehr lässt sich nicht tun; eine neue Kopplung überschreibt den Eintrag.
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

  /// Prüft die gespeicherte Verbindung und lädt alle Daten neu, wenn sie funktioniert.
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

  /// Meldet dieses Gerät auf dem Server ab und entfernt die lokale Sitzung.
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

  /// Lädt neu, wenn die App in den Vordergrund zurückkehrt und die Daten älter
  /// als [maxAge] sind. Auch der Moment, eine verlorene Verbindung neu zu versuchen.
  Future<void> refreshIfStale({
    Duration maxAge = const Duration(minutes: 1),
  }) async {
    if (_session == null || _financeLoading || _isBusy) return;
    final last = _lastSyncAt;
    if (last != null && _clock().difference(last) < maxAge) return;
    await _synchronize();
  }

  /// Lädt Identität, Übersicht, Umsätze und Referenzlisten. Gibt false zurück,
  /// wenn der Server nicht erreichbar war oder die Sitzung endete.
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
          // Die Zahlen sind ohne das vollständig; die Zeile bleibt einfach, wie sie ist.
        }
      } else {
        _syncStatus = null;
      }
      if (_capabilities.contains(newsCapability)) {
        try {
          final found = ServerNews.fromJson(await _read(_apiClient.news));
          _news = found.count > 0 ? found : null;
        } catch (_) {
          // Eine Zugabe; die Zahlen hängen nicht davon ab.
        }
      } else {
        _news = null;
      }
      if (canTriage) {
        try {
          _applyTriage(await _read(() => _apiClient.triage(limit: 1)));
        } catch (_) {
          // Nur der Hinweis auf der Budgetseite hängt davon ab.
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

  /// Ein älterer Server ignoriert unbekannte Parameter und würde mit der ungefilterten
  /// Liste antworten, deshalb werden Suche und Art nur gesendet, wenn er sie kennt.
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

  /// Lesende Aufrufe ändern nichts auf dem Server, eine automatische Wiederholung
  /// nach einem Transportfehler ist also sicher.
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

  /// Beschränkt die Umsatzliste auf ein Konto und/oder eine Kategorie.
  Future<void> setTransactionFilter({int? accountId, int? categoryId}) async {
    if (accountId == _filterAccountId && categoryId == _filterCategoryId) {
      return;
    }
    _filterAccountId = accountId;
    _filterCategoryId = categoryId;
    await refreshTransactions();
  }

  /// Durchsucht Gegenpartei, Verwendungszweck und Notiz. Leerer Text beendet die Suche.
  Future<void> setTransactionSearch(String text) async {
    final search = text.trim();
    if (search == _filterSearch) return;
    _filterSearch = search;
    await refreshTransactions();
  }

  /// 'in' zeigt nur Einnahmen, 'out' nur Ausgaben, null beides.
  Future<void> setTransactionKind(String? kind) async {
    if (kind == _filterKind) return;
    _filterKind = kind;
    await refreshTransactions();
  }

  /// Lädt die Auswertung für [month] ('YYYY-MM'); null ist der laufende Monat.
  /// Die vorige Auswertung bleibt sichtbar, bis die neue da ist.
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

  /// Legt einen manuellen Umsatz an. Gibt bei Erfolg null zurück, sonst die
  /// anzuzeigende Meldung. Der Aufrufer behält [fields] für einen neuen Versuch unverändert,
  /// damit der Server die Wiederholung an ihrer `client_request_id` erkennt.
  /// Fügt ein Konto für von Hand erfasste Einträge hinzu. Gibt bei Erfolg null zurück,
  /// sonst die anzuzeigende Meldung.
  Future<String?> createCashAccount(String name, {int? balanceCents}) => _write(
    () => _apiClient.createCashAccount(name, balanceCents: balanceCents),
    capability: accountsCapability,
  );

  Future<String?> createTransaction(Map<String, dynamic> fields) =>
      _write(() => _apiClient.createTransaction(fields));

  /// Nach einer Kategorieänderung wendet der Server sie auf ähnliche Umsätze an;
  /// [lastAlsoChanged] sagt, wie viele der letzten Änderung gefolgt sind.
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

  /// Ändert einen Vertrag und lädt die Vertragsliste neu. Gibt bei Erfolg null
  /// zurück, sonst die anzuzeigende Meldung.
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

  /// Holt das Kündigungsschreiben. Entweder das Schreiben oder die anzuzeigende
  /// Meldung ist gesetzt. Auf dem Server wird nichts gespeichert.
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

  /// Belege eines Umsatzes. Entweder die Liste oder die Meldung ist gesetzt.
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

  /// Hängt eine Datei an einen Umsatz. Gibt bei Erfolg null zurück, sonst
  /// die anzuzeigende Meldung. Auf dem Gerät bleibt nichts.
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

  /// Wie eine Ausgabe mit dem Haushalt geteilt ist.
  Future<({Map<String, dynamic>? share, String? error})> loadShare(
    int id,
  ) async {
    try {
      return (share: await _apiClient.transactionShare(id), error: null);
    } catch (error) {
      return (share: null, error: await _describeFailure(error));
    }
  }

  /// Geteilte Ausgaben dieser Person, was offen ist, und die Zahlungen.
  Future<({Map<String, dynamic>? data, String? error})> loadSharing() async {
    try {
      return (data: await _read(_apiClient.householdSharing), error: null);
    } catch (error) {
      return (data: null, error: await _describeFailure(error));
    }
  }

  /// Hält fest, dass diese Person jemandem etwas zurückgezahlt hat. Null, wenn es geklappt hat.
  Future<String?> addSettlement(int toPersonId, int cents, String note) async {
    try {
      await _apiClient.addSettlement(toPersonId, cents, note);
      return null;
    } catch (error) {
      return _describeFailure(error);
    }
  }

  /// Teilt eine Ausgabe mit dem Haushalt oder nimmt das zurück.
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

  /// Die Datei eines Belegs, nur im Speicher gehalten, solange sie angezeigt wird.
  Future<({Uint8List? bytes, String? error})> receiptBytes(
    int receiptId,
  ) async {
    try {
      return (bytes: await _apiClient.receiptBytes(receiptId), error: null);
    } catch (error) {
      return (bytes: null, error: await _describeFailure(error));
    }
  }

  /// Ein Bericht als PDF für [period] (JJJJ-MM oder JJJJ), mit dem Teilfilter der
  /// Auswertung, wenn der Server ihn anbietet.
  Future<({Uint8List? bytes, String? error})> reportBytes({
    required String kind,
    required String period,
  }) async {
    try {
      final bytes = await _apiClient.reportBytes(
        kind: kind,
        period: period,
        part: canFilterParts ? viewPart : null,
      );
      return (bytes: bytes, error: null);
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

  /// Setzt das Monatsbudget einer Kategorie oder entfernt es mit null. Gibt bei Erfolg
  /// null zurück, sonst die anzuzeigende Meldung.
  Future<String?> setBudget(
    int categoryId,
    int? limitCents, {
    bool own = false,
  }) => _write(
    () => _apiClient.setBudget(categoryId, limitCents, own: own),
    capability: own ? ownBudgetCapability : budgetCapability,
  );

  /// Liest etwas einmal, mit einem neuen Versuch bei einem Netzaussetzer; der Fehler ist
  /// die anzuzeigende Meldung.
  Future<({Map<String, dynamic>? data, String? error})> readOnce(
    Future<Map<String, dynamic>> Function(MobileApiClient api) call,
  ) async {
    try {
      return (data: await _read(() => call(_apiClient)), error: null);
    } catch (error) {
      return (data: null, error: await _describeFailure(error));
    }
  }

  /// Legt einen Umsatz in ein Projekt oder nimmt ihn heraus. Null, wenn es geklappt hat.
  Future<String?> setTransactionProject(int transactionId, int? projectId) =>
      _write(
        () => _apiClient.setTransactionProject(transactionId, projectId),
        capability: projectsCapability,
      );

  /// Blendet eine geprüfte Auffälligkeit aus. Null, wenn es geklappt hat, sonst die Meldung.
  Future<String?> acknowledgeAlert(String key) => _write(
    () => _apiClient.acknowledgeAlert(key),
    capability: plansCapability,
  );

  /// Plant eine einmalige Ausgabe auf einem Konto, das diese Person sieht.
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

  /// Hält fest, dass für eine Ausgabe Geld zurückkommt.
  Future<String?> createExpected(int transactionId, int cents) => _write(
    () => _apiClient.createExpected(transactionId, cents),
    capability: plansCapability,
  );

  /// Hakt eine geplante Ausgabe oder eine erwartete Einnahme ab oder streicht sie.
  Future<String?> settlePlan(String kind, int id, String action) => _write(
    () => _apiClient.settlePlan(kind, id, action),
    capability: plansCapability,
  );

  /// Schreibende Aufrufe werden nie automatisch wiederholt. Nach Erfolg werden alle
  /// Ansichten neu geladen, damit Salden und Listen zeigen, was der Server gespeichert hat.
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
