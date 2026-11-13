import 'package:flutter/material.dart';

import '../core/design/app_theme.dart';
import '../core/networking/mobile_connection_controller.dart';
import '../core/update/update_check.dart';
import 'kassensturz_shell.dart';

class KassensturzApp extends StatelessWidget {
  const KassensturzApp({
    super.key,
    this.mobileConnectionController,
    this.updateChecker,
  });

  /// Looks for newer app releases; tests pass their own.
  final UpdateChecker? updateChecker;

  /// Without a controller the app starts unpaired with an in-memory session.
  final MobileConnectionController? mobileConnectionController;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Kassensturz',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      home: KassensturzShell(
        mobileConnectionController: mobileConnectionController,
        updateChecker: updateChecker,
      ),
    );
  }
}
