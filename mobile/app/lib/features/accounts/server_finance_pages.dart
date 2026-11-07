import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/data/demo_finance_data.dart';

/// Switches to server-backed account data when a mobile session is active.
/// The existing local account editor remains available in demo mode.
class ServerAwareAccountsPage extends StatelessWidget {
  const ServerAwareAccountsPage({
    required this.controller,
    required this.fallback,
    super.key,
  });

  final MobileConnectionController controller;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => controller.isConnected
          ? _ServerAccountsPage(controller: controller)
          : fallback,
    );
  }
}

class _ServerAccountsPage extends StatelessWidget {
  const _ServerAccountsPage({required this.controller});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    final data = controller.overviewData;
    final accounts = _maps(data?['accounts']);
    final colors = Theme.of(context).colorScheme;
    final total = accounts.fold<int>(
      0,
      (sum, item) => sum + _integer(item['balance_cents']),
    );

    return RefreshIndicator(
      onRefresh: controller.loadFinancialData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
        children: [
          Text(
            'Deine Konten',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 5),
          Text(
            'Konten und Salden direkt von deinem Kassensturz-Server.',
            style: TextStyle(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: AppTheme.brand,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'GESAMTSALDO',
                  style: TextStyle(color: Colors.white70, fontSize: 11),
                ),
                const SizedBox(height: 7),
                Text(
                  formatEuro(total / 100),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 27,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  '${accounts.length} ${accounts.length == 1 ? 'Konto' : 'Konten'} '
                  'vom Server',
                  style: const TextStyle(color: Colors.white70, fontSize: 11),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          if (controller.financeLoading && data == null)
            const Center(child: CircularProgressIndicator())
          else if (data == null)
            _LoadError(
              message: controller.financeError,
              onRetry: controller.loadFinancialData,
            )
          else if (accounts.isEmpty)
            const _EmptyServerState(
              message: 'Der Server liefert noch keine Konten.',
            )
          else
            ...accounts.map((account) {
              final name = _string(account['name'], 'Konto');
              final balance = _integer(account['balance_cents']);
              final known = account['balance_known'] == true;
              final type = _string(account['type'], 'Konto');
              final date = _string(account['balance_date'], '');
              return Card(
                margin: const EdgeInsets.only(bottom: 9),
                child: ListTile(
                  leading: const CircleAvatar(
                    child: Icon(Icons.account_balance_outlined),
                  ),
                  title: Text(name),
                  subtitle: Text([
                    type,
                    if (date.isNotEmpty) 'Stand: $date',
                    if (!known) 'Saldo nicht bestätigt',
                  ].join(' · ')),
                  trailing: Text(
                    known ? formatEuro(balance / 100) : '–',
                    style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                  ),
                ),
              );
            }),
          if (controller.financeError != null && data != null) ...[
            const SizedBox(height: 8),
            Text(
              controller.financeError!,
              style: TextStyle(color: colors.error, fontSize: 12),
            ),
          ],
          const SizedBox(height: 8),
          Text(
            'Serveransicht · Änderungen an Konten erfolgen weiterhin in der '
            'Kassensturz-Administration.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: colors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

/// Switches to server-backed budget data when a mobile session is active.
/// Local budget editing remains available in demo mode.
class ServerAwareBudgetPage extends StatelessWidget {
  const ServerAwareBudgetPage({
    required this.controller,
    required this.fallback,
    super.key,
  });

  final MobileConnectionController controller;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => controller.isConnected
          ? _ServerBudgetPage(controller: controller)
          : fallback,
    );
  }
}

class _ServerBudgetPage extends StatelessWidget {
  const _ServerBudgetPage({required this.controller});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    final data = controller.overviewData;
    final budgets = _maps(data?['budgets']);
    final colors = Theme.of(context).colorScheme;
    final totalLimit = budgets.fold<int>(
      0,
      (sum, item) => sum + _integer(item['limit_cents']),
    );
    final totalSpent = budgets.fold<int>(
      0,
      (sum, item) => sum + _integer(item['spent_cents']),
    );
    final remaining = totalLimit - totalSpent;

    return RefreshIndicator(
      onRefresh: controller.loadFinancialData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
        children: [
          Text(
            'Deine Budgets',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 5),
          Text(
            'Budgetlimits und Ausgaben aus deinem Kassensturz-Server.',
            style: TextStyle(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: AppTheme.brand,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'NOCH VERFÜGBAR',
                  style: TextStyle(color: Colors.white70, fontSize: 11),
                ),
                const SizedBox(height: 7),
                Text(
                  formatEuro(remaining / 100),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 27,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  'Ausgegeben: ${formatEuro(totalSpent / 100)} von ${formatEuro(totalLimit / 100)}',
                  style: const TextStyle(color: Colors.white70, fontSize: 11),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          if (controller.financeLoading && data == null)
            const Center(child: CircularProgressIndicator())
          else if (data == null)
            _LoadError(
              message: controller.financeError,
              onRetry: controller.loadFinancialData,
            )
          else if (budgets.isEmpty)
            const _EmptyServerState(
              message: 'Der Server liefert noch keine Budgets.',
            )
          else
            ...budgets.map((budget) {
              final name = _string(budget['name'], 'Budget');
              final limit = _integer(budget['limit_cents']);
              final spent = _integer(budget['spent_cents']);
              final left = _integer(budget['remaining_cents']);
              final progress =
                  limit <= 0 ? 0.0 : (spent / limit).clamp(0.0, 1.0);
              final over = spent > limit;
              final state = _string(budget['state'], 'ok');
              final color = over || state == 'over'
                  ? colors.error
                  : state == 'warn'
                      ? colors.tertiary
                      : AppTheme.accent;
              return Card(
                margin: const EdgeInsets.only(bottom: 9),
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              name,
                              style: const TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                          Text(
                            '${formatEuro(spent / 100)} / '
                            '${formatEuro(limit / 100)}',
                            style: const TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(20),
                        child: LinearProgressIndicator(
                          value: progress,
                          minHeight: 7,
                          color: color,
                          backgroundColor: colors.surfaceContainerHighest,
                        ),
                      ),
                      const SizedBox(height: 7),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            over
                                ? 'Budget überschritten'
                                : '${(spent / (limit == 0 ? 1 : limit) * 100).round()} % genutzt',
                            style: TextStyle(color: color, fontSize: 11),
                          ),
                          Text(
                            '${formatEuro(left / 100)} übrig',
                            style: TextStyle(
                              color: colors.onSurfaceVariant,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            }),
          if (controller.financeError != null && data != null) ...[
            const SizedBox(height: 8),
            Text(
              controller.financeError!,
              style: TextStyle(color: colors.error, fontSize: 12),
            ),
          ],
          const SizedBox(height: 8),
          Text(
            'Serveransicht · Budgetlimits werden aktuell in der '
            'Kassensturz-Administration verwaltet.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: colors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _LoadError extends StatelessWidget {
  const _LoadError({required this.message, required this.onRetry});

  final String? message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off_outlined, size: 32),
          const SizedBox(height: 10),
          const Text('Serverdaten konnten nicht geladen werden.'),
          if (message != null) Text(message!, textAlign: TextAlign.center),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Erneut versuchen'),
          ),
        ],
      ),
    ),
  );
}

class _EmptyServerState extends StatelessWidget {
  const _EmptyServerState({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 28),
    child: Center(child: Text(message, textAlign: TextAlign.center)),
  );
}

List<Map<String, dynamic>> _maps(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
}

int _integer(dynamic value) => value is int ? value : 0;

String _string(dynamic value, String fallback) =>
    value is String && value.isNotEmpty ? value : fallback;
