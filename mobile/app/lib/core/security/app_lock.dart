import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';

import '../design/app_theme.dart';

/// Optional lock: the app asks for fingerprint, face or the phone's own PIN
/// before it shows anything. Off unless the user turns it on.
class AppLock {
  AppLock({
    Future<String?> Function()? read,
    Future<void> Function(String value)? write,
    Future<bool> Function()? deviceSupported,
    Future<bool> Function(String reason)? authenticate,
  }) : _read = read ?? _storageRead,
       _write = write ?? _storageWrite,
       _deviceSupported = deviceSupported ?? _platformSupported,
       _authenticate = authenticate ?? _platformAuthenticate;

  /// A lock that only lives in memory, for tests.
  factory AppLock.inMemory({
    bool enabled = false,
    bool supported = true,
    required Future<bool> Function(String reason) authenticate,
  }) {
    String? value = enabled ? 'on' : null;
    return AppLock(
      read: () async => value,
      write: (next) async => value = next,
      deviceSupported: () async => supported,
      authenticate: authenticate,
    );
  }

  static const _key = 'app_lock';
  static const _storage = FlutterSecureStorage();

  final Future<String?> Function() _read;
  final Future<void> Function(String value) _write;
  final Future<bool> Function() _deviceSupported;
  final Future<bool> Function(String reason) _authenticate;

  static Future<String?> _storageRead() => _storage.read(key: _key);

  static Future<void> _storageWrite(String value) =>
      _storage.write(key: _key, value: value);

  static Future<bool> _platformSupported() =>
      LocalAuthentication().isDeviceSupported();

  static Future<bool> _platformAuthenticate(String reason) =>
      LocalAuthentication().authenticate(localizedReason: reason);

  /// True when the phone has a screen lock the app can ask for. A phone
  /// without one never locks the app, so nobody is shut out.
  Future<bool> get supported async {
    try {
      return await _deviceSupported();
    } on Object {
      return false;
    }
  }

  Future<bool> get enabled async {
    try {
      // A storage that does not answer must not leave the app blank.
      return (await _read().timeout(const Duration(seconds: 3))) == 'on';
    } on Object {
      return false;
    }
  }

  Future<void> setEnabled(bool value) => _write(value ? 'on' : 'off');

  /// Asks the phone to confirm its owner. False when cancelled or failed.
  Future<bool> unlock(String reason) async {
    try {
      return await _authenticate(reason);
    } on Object {
      return false;
    }
  }
}

/// Covers the whole app while it is locked. Locks at start and after the app
/// was in the background for [relockAfter].
class AppLockGate extends StatefulWidget {
  const AppLockGate({
    required this.child,
    required this.lock,
    this.relockAfter = const Duration(minutes: 1),
    super.key,
  });

  final Widget child;
  final AppLock lock;
  final Duration relockAfter;

  @override
  State<AppLockGate> createState() => _AppLockGateState();
}

class _AppLockGateState extends State<AppLockGate> with WidgetsBindingObserver {
  // null until the setting has been read.
  bool? _locked;
  bool _asking = false;
  DateTime? _pausedAt;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _lockIfEnabled();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      _pausedAt ??= DateTime.now();
    } else if (state == AppLifecycleState.resumed) {
      final pausedAt = _pausedAt;
      _pausedAt = null;
      // The system dialog itself pauses the app; do not lock again for it.
      if (_asking || _locked == true || pausedAt == null) return;
      if (DateTime.now().difference(pausedAt) >= widget.relockAfter) {
        _lockIfEnabled();
      }
    }
  }

  Future<void> _lockIfEnabled() async {
    final lock = await widget.lock.enabled && await widget.lock.supported;
    if (!mounted) return;
    setState(() => _locked = lock);
    if (lock) await _ask();
  }

  Future<void> _ask() async {
    if (_asking) return;
    _asking = true;
    final ok = await widget.lock.unlock('Kassensturz entsperren');
    _asking = false;
    if (ok && mounted) setState(() => _locked = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_locked == false) return widget.child;
    final klar = KlarColors.of(context);
    return Stack(
      children: [
        // Kept in the tree so the app is ready after unlocking, but neither
        // visible nor reachable while locked.
        ExcludeSemantics(child: IgnorePointer(child: widget.child)),
        Positioned.fill(
          child: Material(
            color: klar.surface,
            child: _locked == null
                ? const SizedBox.shrink()
                : Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.lock_outline_rounded,
                          size: 44,
                          color: klar.mutedInk,
                        ),
                        const SizedBox(height: 14),
                        Text(
                          'Kassensturz ist gesperrt',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: _ask,
                          icon: const Icon(Icons.fingerprint, size: 20),
                          label: const Text('Entsperren'),
                        ),
                      ],
                    ),
                  ),
          ),
        ),
      ],
    );
  }
}
