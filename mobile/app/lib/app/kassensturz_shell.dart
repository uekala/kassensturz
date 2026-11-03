import 'package:flutter/material.dart';

import '../core/data/account_controller.dart';
import '../core/data/account_repository.dart';
import '../core/data/budget_controller.dart';
import '../core/data/budget_repository.dart';
import '../core/widgets/demo_notice.dart';
import '../core/networking/mobile_connection_controller.dart';
import '../features/accounts/accounts_page.dart';
import '../features/budget/budget_page.dart';
import '../features/dashboard/dashboard_page.dart';
import '../features/more/more_page.dart';
import '../features/transactions/transactions_page.dart';

class KassensturzShell extends StatefulWidget {
  const KassensturzShell({
    super.key,
    this.budgetRepository,
    this.accountRepository,
    this.mobileConnectionController,
  });

  final BudgetRepository? budgetRepository;
  final AccountRepository? accountRepository;
  final MobileConnectionController? mobileConnectionController;

  @override
  State<KassensturzShell> createState() => _KassensturzShellState();
}

class _KassensturzShellState extends State<KassensturzShell> {
  int _selectedIndex = 0;
  late final BudgetController _budgetController;
  late final AccountController _accountController;
  late final MobileConnectionController _mobileConnectionController;

  @override
  void initState() {
    super.initState();
    _budgetController = BudgetController(
      repository: widget.budgetRepository ?? InMemoryBudgetRepository(),
    );
    _budgetController.load();
    _accountController = AccountController(
      repository: widget.accountRepository ?? InMemoryAccountRepository(),
    );
    _accountController.load();
    _mobileConnectionController =
        widget.mobileConnectionController ??
        MobileConnectionController.preview();
    _mobileConnectionController.restore();
  }

  @override
  void dispose() {
    _budgetController.dispose();
    _accountController.dispose();
    _mobileConnectionController.dispose();
    super.dispose();
  }

  static const _destinations = [
    NavigationDestination(
      icon: Icon(Icons.space_dashboard_outlined),
      selectedIcon: Icon(Icons.space_dashboard_rounded),
      label: 'Übersicht',
    ),
    NavigationDestination(
      icon: Icon(Icons.account_balance_wallet_outlined),
      selectedIcon: Icon(Icons.account_balance_wallet_rounded),
      label: 'Konten',
    ),
    NavigationDestination(
      icon: Icon(Icons.pie_chart_outline_rounded),
      selectedIcon: Icon(Icons.pie_chart_rounded),
      label: 'Budget',
    ),
    NavigationDestination(
      icon: Icon(Icons.receipt_long_outlined),
      selectedIcon: Icon(Icons.receipt_long_rounded),
      label: 'Buchungen',
    ),
    NavigationDestination(
      icon: Icon(Icons.tune_rounded),
      selectedIcon: Icon(Icons.tune_rounded),
      label: 'Mehr',
    ),
  ];

  static const _titles = [
    'Kassensturz',
    'Deine Konten',
    'Budgets & Auswertung',
    'Buchungen',
    'Einstellungen',
  ];

  void _openTransactions() {
    setState(() => _selectedIndex = 3);
  }

  void _openBudget() {
    setState(() => _selectedIndex = 2);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final pages = [
      DashboardPage(
        onOpenTransactions: _openTransactions,
        onOpenBudget: _openBudget,
        budgetController: _budgetController,
        mobileController: _mobileConnectionController,
      ),
      AccountsPage(controller: _accountController),
      BudgetPage(controller: _budgetController),
      TransactionsPage(controller: _mobileConnectionController),
      MorePage(controller: _mobileConnectionController),
    ];

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 16,
        title: Row(
          children: [
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary,
                borderRadius: BorderRadius.circular(9),
              ),
              child: const Icon(
                Icons.account_balance_wallet_rounded,
                color: Colors.white,
                size: 18,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                _titles[_selectedIndex],
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w800,
                  color: const Color(0xFF152A27),
                  letterSpacing: -0.3,
                ),
              ),
            ),
          ],
        ),
        actions: [
          AnimatedBuilder(
            animation: _mobileConnectionController,
            builder: (context, _) {
              final connected = _mobileConnectionController.isConnected;
              final color = connected
                  ? const Color(0xFF22613D)
                  : const Color(0xFF865B12);
              return Padding(
                padding: const EdgeInsets.only(right: 16),
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 5,
                    ),
                    decoration: BoxDecoration(
                      color: connected
                          ? const Color(0xFFE8F5EE)
                          : const Color(0xFFFFF1D6),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          connected
                              ? Icons.cloud_done_outlined
                              : Icons.science_outlined,
                          size: 13,
                          color: color,
                        ),
                        const SizedBox(width: 5),
                        Text(
                          connected ? 'SERVER' : 'DEMO',
                          style: TextStyle(
                            color: color,
                            fontSize: 10,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.6,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          AnimatedBuilder(
            animation: _mobileConnectionController,
            builder: (context, _) {
              if (!_mobileConnectionController.isConnected) {
                return const DemoNotice();
              }
              return Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 9,
                ),
                color: const Color(0xFFE8F5EE),
                child: const Text(
                  'Server verbunden: Übersicht und Buchungen zeigen Serverdaten. Konten und Budgets sind noch lokale App-Funktionen.',
                  style: TextStyle(
                    color: Color(0xFF22613D),
                    fontSize: 11,
                    height: 1.35,
                  ),
                ),
              );
            },
          ),
          Expanded(
            child: IndexedStack(index: _selectedIndex, children: pages),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        destinations: _destinations,
        onDestinationSelected: (index) {
          setState(() => _selectedIndex = index);
        },
      ),
    );
  }
}
