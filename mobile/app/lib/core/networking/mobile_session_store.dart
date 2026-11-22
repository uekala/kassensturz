import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'mobile_session.dart';

abstract interface class MobileSessionStore {
  Future<MobileSession?> read();

  Future<void> write(MobileSession session);

  Future<void> clear();
}

/// Speichert die ganze Sitzung als einen Wert im sicheren Speicher, damit die Token-Rotation
/// kein halb geschriebenes Paar aus Access- und Refresh-Token hinterlassen kann.
class SecureMobileSessionStore implements MobileSessionStore {
  SecureMobileSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'kassensturz.mobile.session.v1';

  final FlutterSecureStorage _storage;

  @override
  Future<MobileSession?> read() async {
    final encoded = await _storage.read(key: _key);
    if (encoded == null) return null;
    return MobileSession.fromStoredJson(encoded);
  }

  @override
  Future<void> write(MobileSession session) =>
      _storage.write(key: _key, value: session.toStoredJson());

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

/// Speicher im Arbeitsspeicher für Widget-Tests und Vorschauen außerhalb der Produktion.
class InMemoryMobileSessionStore implements MobileSessionStore {
  MobileSession? _session;

  @override
  Future<MobileSession?> read() async => _session;

  @override
  Future<void> write(MobileSession session) async {
    _session = session;
  }

  @override
  Future<void> clear() async {
    _session = null;
  }
}
