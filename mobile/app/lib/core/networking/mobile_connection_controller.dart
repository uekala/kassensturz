import 'package:flutter/foundation.dart';

import 'mobile_api_client.dart';
import 'mobile_session.dart';
import 'mobile_session_store.dart';

class MobileConnectionController extends ChangeNotifier {
  MobileConnectionController({
    required MobileApiClient apiClient,
  }) : _apiClient = apiClient;

  factory MobileConnectionController.preview() {
    return MobileConnectionController(
      apiClient: MobileApiClient(
        sessionStore: InMemoryMobileSessionStore(),
      ),
    );
  }

  final MobileApiClient _apiClient;

  MobileSession? _session;
  bool _isBusy = false;
  bool _isLoading = false;
  String? _errorMessage;
  String? _statusMessage;
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

  Future<void> restore() async {
    _isLoading = true;
    _errorMessage = null;
    _notifyIfMounted();
    try {
      _session = await _apiClient.loadSession();
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
      _isBusy = false;
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
