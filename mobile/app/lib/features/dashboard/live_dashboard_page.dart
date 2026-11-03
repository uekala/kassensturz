import 'package:flutter/material.dart';

import '../../core/data/demo_finance_data.dart';
import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';

class LiveDashboardPage extends StatelessWidget {
  const LiveDashboardPage({
    required this.controller,
    required this.onOpenTransactions,
    required this.onOpenBudget,
    super.key,
  });

  final MobileConnectionController controller;
  final VoidCallback onOpenTransactions;
  final VoidCallback onOpenBudget;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final data = controller.overviewData;
        if (data == null) {
          return _DashboardUnavailable(
            loading: controller.financeLoading,
            error: controller.financeError,
            onRetry: controller.loadFinancialData,
          );
        }

        final forecast = _asMap(data['forecast']);
        final month = _asMap(data['month']);
        final accounts = _asMaps(data['accounts']);
        final budgets = _asMaps(data['budgets']);
        final alerts = _asMaps(data['alerts']);
        final free = _asInt(forecast['free_cents']);
        final balance = _asInt(forecast['balance_cents']);
        final monthEnd = forecast['month_end_cents'];
        final transactions = controller.transactionItems;

        return RefreshIndicator(
          onRefresh: controller.loadFinancialData,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
            children: [
              const _DashboardHeading(),
              const SizedBox(height: 18),
              _LiveBalanceCard(
                free: formatEuro(free / 100),
                balance: formatEuro(balance / 100),
                monthEnd: monthEnd is int
                    ? formatEuro(monthEnd / 100)
                    : 'Nicht verfügbar',
              ),
              const SizedBox(height: 26),
              const _SectionHeading('Einnahmen & Ausgaben'),
              const SizedBox(height: 11),
              Row(
                children: [
                  Expanded(
                    child: _CashFlowMetric(
                      label: 'Einnahmen',
                      value: formatEuro(
                        _asInt(month['income_cents']) / 100,
                      ),
                      icon: Icons.south_west_rounded,
                      positive: true,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _CashFlowMetric(
                      label: 'Ausgaben',
                      value: formatEuro(
                        _asInt(month['expense_cents']) / 100,
                      ),
                      icon: Icons.north_east_rounded,
                      positive: false,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 26),
              Row(
                children: [
                  const Expanded(child: _SectionHeading('Deine Konten')),
                  Text(
                    accounts.length.toString(),
                    style: Theme.of(context).textTheme.labelMedium,
                  ),
                ],
              ),
              const SizedBox(height: 9),
              if (accounts.isEmpty)
                const _EmptyState(
                  'Auf dem Server sind noch keine Konten angelegt.',
                )
              else
                _AccountList(accounts: accounts),
              const SizedBox(height: 26),
              _SectionHeading(
                'Dein Budget',
                action: 'Details',
                onAction: onOpenBudget,
              ),
              const SizedBox(height: 10),
              if (budgets.isEmpty)
                const _EmptyState('Noch keine Budgets eingerichtet.')
              else
                _BudgetList(budgets: budgets),
              if (alerts.isNotEmpty) ...[
                const SizedBox(height: 26),
                const _SectionHeading('Hinweise'),
                const SizedBox(height: 9),
                ...alerts.map((alert) => _AlertRow(alert: alert)),
              ],
              const SizedBox(height: 26),
              _SectionHeading(
                'Letzte Buchungen',
                action: 'Alle anzeigen',
                onAction: onOpenTransactions,
              ),
              const SizedBox(height: 5),
              if (transactions.isEmpty && controller.financeLoading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 20),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (transactions.isEmpty)
                const _EmptyState('Noch keine Buchungen vorhanden.')
              else
                ...transactions.take(4).map(
                  (transaction) => _TransactionRow(transaction: transaction),
                ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: onOpenTransactions,
                child: const Text('Alle Buchungen anzeigen'),
              ),
              if (controller.financeError != null) ...[
                const SizedBox(height: 12),
                Text(
                  controller.financeError!,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.error,
                      ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  static Map<String, dynamic> _asMap(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

  static List<Map<String, dynamic>> _asMaps(dynamic value) {
    if (value is! List) return const [];
    return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
  }

  static int _asInt(dynamic value) => value is int ? value : 0;
}

class _DashboardUnavailable extends StatelessWidget {
  const _DashboardUnavailable({
    required this.loading,
    required this.error,
    required this.onRetry,
  });

  final bool loading;
  final String? error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              loading ? Icons.sync_rounded : Icons.cloud_off_outlined,
              size: 30,
              color: colors.onSurfaceVariant,
            ),
            const SizedBox(height: 14),
            Text(
              loading
                  ? 'Finanzdaten werden geladen'
                  : 'Finanzdaten sind gerade nicht verfügbar',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (error != null) ...[
              const SizedBox(height: 7),
              Text(
                error!,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: 14),
            OutlinedButton.icon(
              onPressed: loading ? null : onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Erneut versuchen'),
            ),
          ],
        ),
      ),
    );
  }
}

class _DashboardHeading extends StatelessWidget {
  const _DashboardHeading();

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    const months = [
      'Januar',
      'Februar',
      'März',
      'April',
      'Mai',
      'Juni',
      'Juli',
      'August',
      'September',
      'Oktober',
      'November',
      'Dezember',
    ];
    final month = '${months[now.month - 1]} ${now.year}';
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'DEIN FINANZÜBERBLICK',
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.1,
          ),
        ),
        const SizedBox(height: 5),
        Text('Dein Überblick', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 3),
        Text(month, style: theme.textTheme.bodyMedium),
      ],
    );
  }
}

class _LiveBalanceCard extends StatelessWidget {
  const _LiveBalanceCard({
    required this.free,
    required this.balance,
    required this.monthEnd,
  });

  final String free;
  final String balance;
  final String monthEnd;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
      decoration: BoxDecoration(
        color: AppTheme.brand,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Expanded(
                child: Text(
                  'FREI VERFÜGBAR',
                  style: TextStyle(
                    color: Color(0xFFD5E4DE),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
              ),
              Text(
                'SERVERDATEN',
                style: TextStyle(
                  color: Color(0xFFD5E4DE),
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.7,
                ),
              ),
            ],
          ),
          const SizedBox(height: 11),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              free,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 32,
                height: 1.15,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.9,
              ),
            ),
          ),
          const SizedBox(height: 18),
          Container(height: 1, color: Colors.white.withValues(alpha: 0.18)),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(child: _HeroMetric(label: 'Kontostand', value: balance)),
              const SizedBox(width: 12),
              Expanded(
                child: _HeroMetric(
                  label: 'Prognose Monatsende',
                  value: monthEnd,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeroMetric extends StatelessWidget {
  const _HeroMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(color: Color(0xFFD5E4DE), fontSize: 11),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _CashFlowMetric extends StatelessWidget {
  const _CashFlowMetric({
    required this.label,
    required this.value,
    required this.icon,
    required this.positive,
  });

  final String label;
  final String value;
  final IconData icon;
  final bool positive;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      constraints: const BoxConstraints(minHeight: 106),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                icon,
                size: 17,
                color: positive ? AppTheme.accent : colors.onSurfaceVariant,
              ),
              const SizedBox(width: 7),
              Text(label, style: Theme.of(context).textTheme.labelMedium),
            ],
          ),
          const SizedBox(height: 13),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.35,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeading extends StatelessWidget {
  const _SectionHeading(this.title, {this.action, this.onAction});

  final String title;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        if (action != null)
          TextButton(
            onPressed: onAction,
            style: TextButton.styleFrom(
              visualDensity: VisualDensity.compact,
              padding: const EdgeInsets.only(left: 8),
            ),
            child: Text(action!),
          ),
      ],
    );
  }
}

class _AccountList extends StatelessWidget {
  const _AccountList({required this.accounts});

  final List<Map<String, dynamic>> accounts;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Column(
        children: [
          for (var index = 0; index < accounts.length; index++) ...[
            if (index > 0) const Divider(height: 1),
            _AccountRow(account: accounts[index]),
          ],
        ],
      ),
    );
  }
}

class _AccountRow extends StatelessWidget {
  const _AccountRow({required this.account});

  final Map<String, dynamic> account;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final known = account['balance_known'] == true;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: colors.surfaceContainerHigh,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(
              Icons.account_balance_outlined,
              size: 18,
              color: colors.onSurfaceVariant,
            ),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  account['name']?.toString() ?? 'Konto',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontSize: 14,
                      ),
                ),
                const SizedBox(height: 2),
                Text(
                  account['type']?.toString() ?? 'Konto',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            known
                ? formatEuro(_asInt(account['balance_cents']) / 100)
                : 'Nicht verfügbar',
            style: Theme.of(context).textTheme.labelLarge,
            textAlign: TextAlign.end,
          ),
        ],
      ),
    );
  }

  static int _asInt(dynamic value) => value is int ? value : 0;
}

class _BudgetList extends StatelessWidget {
  const _BudgetList({required this.budgets});

  final List<Map<String, dynamic>> budgets;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(15, 4, 15, 4),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Column(
        children: [
          for (var index = 0; index < budgets.length; index++) ...[
            if (index > 0) const Divider(height: 1),
            _BudgetRow(budget: budgets[index]),
          ],
        ],
      ),
    );
  }
}

class _BudgetRow extends StatelessWidget {
  const _BudgetRow({required this.budget});

  final Map<String, dynamic> budget;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final limit = _asInt(budget['limit_cents']);
    final spent = _asInt(budget['spent_cents']);
    final remaining = _asInt(budget['remaining_cents']);
    final progress = limit <= 0
        ? 0.0
        : (spent / limit).clamp(0.0, 1.0).toDouble();
    final isOver = budget['state'] == 'over';

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  budget['name']?.toString() ?? 'Kategorie',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontSize: 14,
                      ),
                ),
              ),
              Text(
                '${formatEuro(spent / 100)} / ${formatEuro(limit / 100)}',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 6,
              backgroundColor: colors.surfaceContainerHigh,
              valueColor: AlwaysStoppedAnimation(
                isOver ? colors.error : AppTheme.accent,
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            isOver
                ? '${formatEuro(remaining.abs() / 100)} über dem Budget'
                : '${formatEuro(remaining / 100)} noch verfügbar',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: isOver ? colors.error : colors.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }

  static int _asInt(dynamic value) => value is int ? value : 0;
}

class _AlertRow extends StatelessWidget {
  const _AlertRow({required this.alert});

  final Map<String, dynamic> alert;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final level = alert['level']?.toString() ?? 'info';
    final color = level == 'critical'
        ? colors.error
        : level == 'warning'
            ? const Color(0xFF95651C)
            : colors.primary;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline_rounded, color: color, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  alert['title']?.toString() ?? 'Hinweis',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontSize: 14,
                      ),
                ),
                if ((alert['message']?.toString() ?? '').isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    alert['message'].toString(),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TransactionRow extends StatelessWidget {
  const _TransactionRow({required this.transaction});

  final Map<String, dynamic> transaction;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final amount = _asInt(transaction['amount_cents']);
    final category = transaction['category'];
    final categoryName = category is Map
        ? category['name']?.toString()
        : null;
    final counterparty = transaction['counterparty']?.toString() ?? '';
    final purpose = transaction['purpose']?.toString() ?? '';
    final title = counterparty.isNotEmpty
        ? counterparty
        : purpose.isNotEmpty
            ? purpose
            : 'Buchung';
    final subtitle = <String>[
      if (categoryName != null && categoryName.isNotEmpty) categoryName,
      if (transaction['booking_date'] is String)
        _formatDate(transaction['booking_date'] as String),
    ].join(' · ');

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 2),
      minLeadingWidth: 38,
      leading: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: colors.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(11),
        ),
        child: Icon(
          amount < 0 ? Icons.north_east_rounded : Icons.south_west_rounded,
          color: colors.onSurfaceVariant,
          size: 18,
        ),
      ),
      title: Text(
        title,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(fontSize: 14),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        subtitle.isEmpty ? 'Buchung' : subtitle,
        style: Theme.of(context).textTheme.bodySmall,
      ),
      trailing: Text(
        formatSignedEuro(amount / 100),
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
              color: amount < 0 ? colors.onSurface : AppTheme.accent,
            ),
      ),
    );
  }

  static int _asInt(dynamic value) => value is int ? value : 0;

  static String _formatDate(String value) {
    final date = DateTime.tryParse(value);
    if (date == null) return value;
    return '${date.day.toString().padLeft(2, '0')}.${date.month.toString().padLeft(2, '0')}.${date.year}';
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Text(
        message,
        style: Theme.of(context).textTheme.bodyMedium,
      ),
    );
  }
}
