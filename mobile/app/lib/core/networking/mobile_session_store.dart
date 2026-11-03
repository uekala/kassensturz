import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'mobile_session.dart';

abstract interface class MobileSessionStore {
  Future<MobileSession?> read();

  Future<void> write(MobileSession session);

  Future<void> clear();
}

/// Stores the complete session as one secure-storage value so token rotation
/// cannot leave a half-written access/refresh token pair.
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

/// In-memory store used by widget tests and non-production previews.
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
