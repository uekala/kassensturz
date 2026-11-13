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

  /// Looks for newer app releases; tests pass their own.
  final UpdateChecker? updateChecker;

  /// Without a controller the app starts unpaired with an in-memory session.
  final MobileConnectionController? mobileConnectionController;

  @override
  Widget build(BuildContext context) {
    final lock = appLock ?? AppLock();
    return MaterialApp(
      title: 'Kassensturz',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      // Above the navigator, so the lock also covers open pages and sheets.
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
