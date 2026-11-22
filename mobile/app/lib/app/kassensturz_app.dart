import 'package:flutter/material.dart';

import '../core/design/app_theme.dart';
import '../core/networking/mobile_connection_controller.dart';
import '../core/security/app_lock.dart';
import '../core/update/update_check.dart';
import 'kassensturz_shell.dart';

class KassensturzApp extends StatelessWidget {
  const KassensturzApp({
    super.key,
    this.mobileConnectionController,
    this.updateChecker,
    this.appLock,
  });

  /// Fingerprint lock; tests pass their own.
  final AppLock? appLock;

  /// Sucht nach neueren App-Releases; Tests geben ihre eigene Prüfung mit.
  final UpdateChecker? updateChecker;

  /// Ohne Controller startet die App ungekoppelt mit einer Sitzung im Speicher.
  final MobileConnectionController? mobileConnectionController;

  @override
  Widget build(BuildContext context) {
    final lock = appLock ?? AppLock();
    return MaterialApp(
      title: 'Kassensturz',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      // Über dem Navigator, damit die Sperre auch offene Seiten und Blätter abdeckt.
      builder: (context, child) =>
          AppLockGate(lock: lock, child: child ?? const SizedBox.shrink()),
      home: KassensturzShell(
        mobileConnectionController: mobileConnectionController,
        updateChecker: updateChecker,
        appLock: lock,
      ),
    );
  }
}
