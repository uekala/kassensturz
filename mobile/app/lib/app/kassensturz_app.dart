import 'package:flutter/material.dart';

import '../core/data/account_repository.dart';
import '../core/data/budget_repository.dart';
import '../core/design/app_theme.dart';
import '../core/networking/mobile_connection_controller.dart';
import 'kassensturz_shell.dart';

class KassensturzApp extends StatelessWidget {
  const KassensturzApp({
    super.key,
    this.budgetRepository,
    this.accountRepository,
    this.mobileConnectionController,
  });

  final BudgetRepository? budgetRepository;
  final AccountRepository? accountRepository;
  final MobileConnectionController? mobileConnectionController;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Kassensturz',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: KassensturzShell(
        budgetRepository: budgetRepository,
        accountRepository: accountRepository,
        mobileConnectionController: mobileConnectionController,
      ),
    );
  }
}
