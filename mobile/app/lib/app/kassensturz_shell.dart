import 'package:flutter/material.dart';

import '../core/data/account_controller.dart';
import '../core/data/account_repository.dart';
import '../core/data/budget_controller.dart';
import '../core/data/budget_repository.dart';
import '../core/design/app_theme.dart';
import '../core/widgets/demo_notice.dart';
import '../core/networking/mobile_connection_controller.dart';
import '../features/accounts/accounts_page.dart';
import '../features/accounts/server_finance_pages.dart';
import '../features/budget/budget_page.dart';
import '../features/dashboard/dashboard_page.dart';
import '../features/more/connect_required_page.dart';
import '../features/more/more_page.dart';
import '../features/transactions/transactions_page.dart';

class KassensturzShell extends StatefulWidget {
  const KassensturzShell({
    super.key,
    this.budgetRepository,
    this.accountRepository,
    this.mobileConnectionController,
    this.serverOnly = false,
  });

  final BudgetRepository? budgetRepository;
  final AccountRepository? accountRepository;
  final MobileConnectionController? mobileConnectionController;

  /// The installed app shows server data only. Without a connection it asks
  /// the user to connect instead of showing example or device-local data.
  final bool serverOnly;

  @override
  State<KassensturzShell> createState() => _KassensturzShellState();
}

class _KassensturzShellState extends State<KassensturzShell>
    with WidgetsBindingObserver {
  int _selectedIndex = 0;
  late final BudgetController _budgetController;
  late final AccountController _accountController;
  late final MobileConnectionController _mobileConnectionController;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Returning to the app is the moment to reconnect and show fresh data.
    if (state == AppLifecycleState.resumed) {
      _mobileConnectionController.refreshIfStale();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
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

  void _openSettings() {
    setState(() => _selectedIndex = 4);
  }

  /// In the installed app the four data tabs need a server connection.
  Widget _serverData(Widget page) {
    if (!widget.serverOnly) return page;
    return AnimatedBuilder(
      animation: _mobileConnectionController,
      builder: (context, _) => _mobileConnectionController.isConnected
          ? page
          : ConnectRequiredPage(onOpenSettings: _openSettings),
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final pages = [
      _serverData(
        DashboardPage(
          onOpenTransactions: _openTransactions,
          onOpenBudget: _openBudget,
          budgetController: _budgetController,
          mobileController: _mobileConnectionController,
        ),
      ),
      _serverData(
        ServerAwareAccountsPage(
          controller: _mobileConnectionController,
          fallback: AccountsPage(controller: _accountController),
        ),
      ),
      _serverData(
        ServerAwareBudgetPage(
          controller: _mobileConnectionController,
          fallback: BudgetPage(controller: _budgetController),
        ),
      ),
      _serverData(TransactionsPage(controller: _mobileConnectionController)),
      MorePage(controller: _mobileConnectionController),
    ];

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 16,
        title: Row(
          children: [
            Container(
              width: 29,
              height: 29,
              decoration: BoxDecoration(
                color: AppTheme.brand,
                borderRadius: BorderRadius.circular(8),
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
                  fontWeight: FontWeight.w700,
                  color: AppTheme.ink,
                  letterSpacing: -0.35,
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
              final unreachable =
                  _mobileConnectionController.linkState ==
                  ServerLinkState.unreachable;
              final color = connected && !unreachable
                  ? AppTheme.brand
                  : AppTheme.mutedInk;
              final label = unreachable
                  ? 'KEINE VERBINDUNG'
                  : connected
                  ? 'SERVER'
                  : widget.serverOnly
                  ? 'NICHT VERBUNDEN'
                  : 'DEMO';
              return Padding(
                padding: const EdgeInsets.only(right: 20),
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 5,
                    ),
                    decoration: BoxDecoration(
                      color: AppTheme.softBrand,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          unreachable
                              ? Icons.cloud_off_outlined
                              : connected
                              ? Icons.cloud_done_outlined
                              : Icons.science_outlined,
                          size: 13,
                          color: color,
                        ),
                        const SizedBox(width: 5),
                        Text(
                          label,
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
              final controller = _mobileConnectionController;
              if (!controller.isConnected) {
                return widget.serverOnly
                    ? const SizedBox.shrink()
                    : const DemoNotice();
              }
              final String message;
              if (controller.linkState == ServerLinkState.unreachable) {
                message =
                    'Server nicht erreichbar. Angezeigt wird der zuletzt '
                    'geladene Stand; Änderungen brauchen eine Verbindung.';
              } else if (controller.serverNeedsUpdate) {
                message =
                    'Server verbunden. Zum Anlegen von Umsätzen bitte '
                    'Kassensturz in Home Assistant aktualisieren.';
              } else {
                message =
                    'Server verbunden: Alle Daten kommen von deinem '
                    'Kassensturz-Server und werden dort gespeichert.';
              }
              return Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 9,
                ),
                color: AppTheme.softBrand,
                child: Text(
                  message,
                  style: const TextStyle(
                    color: AppTheme.brand,
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
