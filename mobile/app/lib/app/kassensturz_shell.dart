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
      ),
      AccountsPage(controller: _accountController),
      BudgetPage(controller: _budgetController),
      const TransactionsPage(),
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
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF1D6),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.science_outlined,
                      size: 13,
                      color: Color(0xFF865B12),
                    ),
                    SizedBox(width: 5),
                    Text(
                      'DEMO',
                      style: TextStyle(
                        color: Color(0xFF865B12),
                        fontSize: 10,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.6,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          const DemoNotice(),
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
