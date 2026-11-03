import 'package:flutter/material.dart';

import '../core/data/account_repository.dart';
import '../core/data/budget_repository.dart';
import '../core/design/app_theme.dart';
import 'kassensturz_shell.dart';

class KassensturzApp extends StatelessWidget {
  const KassensturzApp({
    super.key,
    this.budgetRepository,
    this.accountRepository,
  });

  final BudgetRepository? budgetRepository;
  final AccountRepository? accountRepository;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Kassensturz',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: KassensturzShell(
        budgetRepository: budgetRepository,
        accountRepository: accountRepository,
      ),
    );
  }
}
