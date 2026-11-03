import 'package:flutter/foundation.dart';

import 'mobile_api_client.dart';
import 'mobile_session.dart';
import 'mobile_session_store.dart';

class MobileConnectionController extends ChangeNotifier {
  MobileConnectionController({required MobileApiClient apiClient})
    : _apiClient = apiClient;

  factory MobileConnectionController.preview() {
    return MobileConnectionController(
      apiClient: MobileApiClient(sessionStore: InMemoryMobileSessionStore()),
    );
  }

  final MobileApiClient _apiClient;

  MobileSession? _session;
  bool _isBusy = false;
  bool _isLoading = false;
  String? _errorMessage;
  String? _statusMessage;
  Map<String, dynamic>? _overview;
  Map<String, dynamic>? _transactionPage;
  bool _financeLoading = false;
  String? _financeError;
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

  Future<void> restore() async {
    _isLoading = true;
    _errorMessage = null;
    _notifyIfMounted();
    try {
      _session = await _apiClient.loadSession();
      if (_session != null) await loadFinancialData();
    } catch (_) {
      _session = null;
      _errorMessage =
          'Die gespeicherte Sitzung konnte nicht gelesen werden. Bitte richte die Verbindung erneut ein.';
    } finally {
      _isLoading = false;
      _notifyIfMounted();
    }
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
      _statusMessage = 'Gerät wurde sicher mit Kassensturz gekoppelt.';
      await loadFinancialData();
      return true;
    } catch (error) {
      _errorMessage = _messageFor(error);
      return false;
    } finally {
      _isBusy = false;
      _notifyIfMounted();
    }
  }

  Future<bool> checkConnection() async {
    _isBusy = true;
    _errorMessage = null;
    _statusMessage = null;
    _notifyIfMounted();
    try {
      final identity = await _apiClient.me();
      final server = identity['server'];
      final serverName = server is Map ? server['name'] : null;
      _statusMessage = serverName is String
          ? 'Verbunden mit ' + serverName + '.'
          : 'Verbindung erfolgreich geprüft.';
      _session = await _apiClient.loadSession();
      await loadFinancialData();
      return true;
    } catch (error) {
      _errorMessage = _messageFor(error);
      return false;
    } finally {
      _isBusy = false;
      _notifyIfMounted();
    }
  }

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
          _messageFor(error) + ' Die lokale Sitzung wurde trotzdem entfernt.';
    } finally {
      _session = await _apiClient.loadSession();
      if (_session == null) {
        _overview = null;
        _transactionPage = null;
        _financeError = null;
      }
      _isBusy = false;
      _notifyIfMounted();
    }
  }

  Future<void> loadFinancialData() async {
    if (_session == null) return;
    _financeLoading = true;
    _financeError = null;
    _notifyIfMounted();
    try {
      final results = await Future.wait([
        _apiClient.overview(),
        _apiClient.transactions(),
      ]);
      _overview = results[0];
      _transactionPage = results[1];
    } catch (error) {
      _financeError = _messageFor(error);
    } finally {
      _financeLoading = false;
      _notifyIfMounted();
    }
  }

  Future<void> loadMoreTransactions() async {
    if (_session == null || _financeLoading) return;
    final current = _transactionPage;
    if (current == null) {
      await loadFinancialData();
      return;
    }
    final offset = (current['offset'] as int? ?? 0) +
        (current['limit'] as int? ?? 50);
    if (offset >= transactionTotal) return;
    _financeLoading = true;
    _financeError = null;
    _notifyIfMounted();
    try {
      final next = await _apiClient.transactions(offset: offset);
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
    } catch (error) {
      _financeError = _messageFor(error);
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
      _transactionPage = await _apiClient.transactions();
    } catch (error) {
      _financeError = _messageFor(error);
    } finally {
      _financeLoading = false;
      _notifyIfMounted();
    }
  }

  static String _messageFor(Object error) {
    if (error is FormatException) return error.message.toString();
    if (error is MobileApiException) return error.message;
    return 'Der Server konnte nicht erreicht werden. Prüfe Adresse und VPN-Verbindung.';
  }

  @override
  void dispose() {
    _disposed = true;
    _apiClient.close();
    super.dispose();
  }
}
