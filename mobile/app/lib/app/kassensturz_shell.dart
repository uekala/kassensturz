import 'package:flutter/material.dart';

import '../core/design/app_theme.dart';
import '../core/networking/mobile_connection_controller.dart';
import '../features/accounts/server_finance_pages.dart';
import '../features/analysis/analysis_page.dart';
import '../features/budget/planning_page.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/update/update_check.dart';
import '../features/dashboard/live_dashboard_page.dart';
import '../features/more/connect_required_page.dart';
import '../features/more/more_page.dart';
import '../features/transactions/transaction_editor_page.dart';
import '../features/transactions/transactions_page.dart';

class KassensturzShell extends StatefulWidget {
  const KassensturzShell({
    super.key,
    this.mobileConnectionController,
    this.updateChecker,
  });

  final UpdateChecker? updateChecker;

  /// The app shows server data only. Without a connection it asks the user
  /// to connect; there is no example or device-local data.
  final MobileConnectionController? mobileConnectionController;

  @override
  State<KassensturzShell> createState() => _KassensturzShellState();
}

class _KassensturzShellState extends State<KassensturzShell>
    with WidgetsBindingObserver {
  int _selectedIndex = 0;
  late final MobileConnectionController _mobileConnectionController;
  late final UpdateChecker _updates = widget.updateChecker ?? UpdateChecker();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _mobileConnectionController =
        widget.mobileConnectionController ??
        MobileConnectionController.preview();
    _mobileConnectionController.restore();
    _checkForUpdate();
  }

  Future<void> _checkForUpdate() async {
    final update = await _updates.check();
    if (update == null || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.showMaterialBanner(
      MaterialBanner(
        leading: const Icon(Icons.system_update_outlined),
        content: Text(
          'Kassensturz ${update.version} ist verfügbar '
          '(installiert: ${_updates.currentVersion}).',
        ),
        actions: [
          TextButton(
            onPressed: messenger.hideCurrentMaterialBanner,
            child: const Text('Später'),
          ),
          FilledButton(
            onPressed: () async {
              messenger.hideCurrentMaterialBanner();
              var opened = false;
              try {
                opened = await launchUrl(
                  Uri.parse(update.downloadUrl),
                  mode: LaunchMode.externalApplication,
                );
              } on Object {
                opened = false;
              }
              if (!opened) _showMessage('Download-Seite: ${update.pageUrl}');
            },
            child: const Text('Update laden'),
          ),
        ],
      ),
    );
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
    _mobileConnectionController.dispose();
    super.dispose();
  }

  static const _titles = ['Heute', 'Umsätze', 'Planung', 'Konten'];

  void _openTransactions() {
    setState(() => _selectedIndex = 1);
  }

  void _openBudget() {
    setState(() => _selectedIndex = 2);
  }

  void _openAnalysis() {
    Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => AnalysisPage(controller: _mobileConnectionController),
      ),
    );
  }

  void _openSettings() {
    Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(title: const Text('Einstellungen')),
          body: MorePage(
            controller: _mobileConnectionController,
            updates: _updates,
          ),
        ),
      ),
    );
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  /// The plus button works from every tab; it explains what is missing
  /// instead of being hidden.
  Future<void> _addTransaction() async {
    final controller = _mobileConnectionController;
    if (!controller.isConnected) {
      _showMessage('Verbinde die App zuerst mit deinem Kassensturz-Server.');
      return;
    }
    if (!controller.canWriteTransactions) {
      _showMessage(
        'Bitte aktualisiere Kassensturz in Home Assistant, um Umsätze '
        'anzulegen.',
      );
      return;
    }
    if (controller.manualAccounts.isEmpty) {
      _showMessage(
        'Umsätze lassen sich nur auf Konten ohne Bankabruf anlegen. '
        'Lege dafür in Kassensturz ein Konto an, zum Beispiel Bargeld.',
      );
      return;
    }
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => TransactionEditorPage(controller: controller),
      ),
    );
    if (saved == true) _showMessage('Auf dem Server gespeichert.');
  }

  /// The four data tabs need a server connection.
  Widget _serverData(Widget page) {
    return AnimatedBuilder(
      animation: _mobileConnectionController,
      builder: (context, _) => _mobileConnectionController.isConnected
          ? page
          : ConnectRequiredPage(onOpenSettings: _openSettings),
    );
  }

  /// Null while everything is fine; the header then shows only a blue dot.
  String? _statusLabel() {
    final controller = _mobileConnectionController;
    if (controller.linkState == ServerLinkState.unreachable) {
      return 'KEINE VERBINDUNG';
    }
    if (controller.isConnected) return null;
    return 'NICHT VERBUNDEN';
  }

  /// A hint below the header, shown only when something needs attention.
  Widget _notice() {
    final klar = KlarColors.of(context);
    final controller = _mobileConnectionController;
    if (!controller.isConnected) return const SizedBox.shrink();
    final String message;
    if (controller.linkState == ServerLinkState.unreachable) {
      message =
          'Server nicht erreichbar. Angezeigt wird der zuletzt geladene '
          'Stand; Änderungen brauchen eine Verbindung.';
    } else if (controller.serverNeedsUpdate) {
      message =
          'Zum Anlegen von Umsätzen bitte Kassensturz in Home Assistant '
          'aktualisieren.';
    } else {
      return const SizedBox.shrink();
    }
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(20, 0, 20, 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: klar.warn, width: 1.5),
      ),
      child: Text(
        message,
        style: TextStyle(color: klar.warn, fontSize: 12, height: 1.4),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = _mobileConnectionController;
    final pages = [
      _serverData(
        LiveDashboardPage(
          controller: controller,
          onOpenTransactions: _openTransactions,
          onOpenBudget: _openBudget,
          onOpenAnalysis: _openAnalysis,
        ),
      ),
      _serverData(TransactionsPage(controller: controller)),
      _serverData(
        PlanningPage(
          controller: controller,
          budgets: ServerBudgetPage(controller: controller),
        ),
      ),
      _serverData(ServerAccountsPage(controller: controller)),
    ];

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            AnimatedBuilder(
              animation: _mobileConnectionController,
              builder: (context, _) => _ShellHeader(
                title: _titles[_selectedIndex],
                status: _statusLabel(),
                online: controller.linkState == ServerLinkState.connected,
                onOpenSettings: _openSettings,
              ),
            ),
            AnimatedBuilder(
              animation: _mobileConnectionController,
              builder: (context, _) => _notice(),
            ),
            Expanded(
              child: IndexedStack(index: _selectedIndex, children: pages),
            ),
          ],
        ),
      ),
      bottomNavigationBar: _ShellNavigation(
        selectedIndex: _selectedIndex,
        onSelected: (index) => setState(() => _selectedIndex = index),
        onAdd: _addTransaction,
      ),
    );
  }
}

class _ShellHeader extends StatelessWidget {
  const _ShellHeader({
    required this.title,
    required this.status,
    required this.online,
    required this.onOpenSettings,
  });

  final String title;
  final String? status;
  final bool online;
  final VoidCallback onOpenSettings;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
          ),
          if (status != null) ...[
            Text(
              status!,
              style: TextStyle(
                color: klar.mutedInk,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.6,
              ),
            ),
            const SizedBox(width: 10),
          ],
          Stack(
            clipBehavior: Clip.none,
            children: [
              IconButton.outlined(
                tooltip: 'Einstellungen',
                onPressed: onOpenSettings,
                style: IconButton.styleFrom(
                  foregroundColor: klar.ink,
                  minimumSize: const Size(44, 44),
                  side: BorderSide(color: klar.ink, width: 1.5),
                ),
                icon: const Icon(Icons.tune_rounded, size: 20),
              ),
              Positioned(
                right: 0,
                top: 0,
                child: IgnorePointer(
                  child: Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      color: online ? klar.brand : klar.warn,
                      shape: BoxShape.circle,
                      border: Border.all(color: klar.surface, width: 2),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ShellNavigation extends StatelessWidget {
  const _ShellNavigation({
    required this.selectedIndex,
    required this.onSelected,
    required this.onAdd,
  });

  final int selectedIndex;
  final ValueChanged<int> onSelected;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    return Material(
      color: klar.surface,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: klar.border)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 72,
            child: Row(
              children: [
                _NavigationItem(
                  label: 'Heute',
                  icon: Icons.home_outlined,
                  selected: selectedIndex == 0,
                  onTap: () => onSelected(0),
                ),
                _NavigationItem(
                  label: 'Umsätze',
                  icon: Icons.receipt_long_outlined,
                  selected: selectedIndex == 1,
                  onTap: () => onSelected(1),
                ),
                Expanded(
                  child: Center(
                    child: IconButton.filled(
                      tooltip: 'Umsatz anlegen',
                      onPressed: onAdd,
                      style: IconButton.styleFrom(
                        backgroundColor: klar.brand,
                        foregroundColor: klar.onBrand,
                        minimumSize: const Size(52, 52),
                      ),
                      icon: const Icon(Icons.add_rounded, size: 28),
                    ),
                  ),
                ),
                _NavigationItem(
                  label: 'Planung',
                  icon: Icons.bar_chart_rounded,
                  selected: selectedIndex == 2,
                  onTap: () => onSelected(2),
                ),
                _NavigationItem(
                  label: 'Konten',
                  icon: Icons.account_balance_wallet_outlined,
                  selected: selectedIndex == 3,
                  onTap: () => onSelected(3),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _NavigationItem extends StatelessWidget {
  const _NavigationItem({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final color = selected ? klar.brand : klar.mutedInk;
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 24, color: color),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 11,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
