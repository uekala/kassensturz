import 'package:flutter/material.dart';

import '../core/widgets/demo_notice.dart';
import '../features/accounts/accounts_page.dart';
import '../features/dashboard/dashboard_page.dart';
import '../features/more/more_page.dart';
import '../features/transactions/transactions_page.dart';

class KassensturzShell extends StatefulWidget {
  const KassensturzShell({super.key});

  @override
  State<KassensturzShell> createState() => _KassensturzShellState();
}

class _KassensturzShellState extends State<KassensturzShell> {
  int _selectedIndex = 0;

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
      icon: Icon(Icons.receipt_long_outlined),
      selectedIcon: Icon(Icons.receipt_long_rounded),
      label: 'Buchungen',
    ),
    NavigationDestination(
      icon: Icon(Icons.more_horiz_rounded),
      selectedIcon: Icon(Icons.more_horiz_rounded),
      label: 'Mehr',
    ),
  ];

  static const _pages = [
    DashboardPage(),
    AccountsPage(),
    TransactionsPage(),
    MorePage(),
  ];

  static const _titles = [
    'Kassensturz',
    'Deine Konten',
    'Buchungen',
    'Mehr',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_selectedIndex]),
        titleTextStyle: Theme.of(context).textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.w800,
              color: const Color(0xFF152A27),
              letterSpacing: -0.3,
            ),
      ),
      body: Column(
        children: [
          const DemoNotice(),
          Expanded(
            child: IndexedStack(
              index: _selectedIndex,
              children: _pages,
            ),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        destinations: _destinations,
        onDestinationSelected: (index) {
          setState(() => _selectedIndex = index);
        },
      ),
    );
  }
}
