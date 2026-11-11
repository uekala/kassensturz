import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';

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
    final klar = KlarColors.of(context);
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
        final income = _asInt(month['income_cents']);
        final expense = _asInt(month['expense_cents']).abs();
        final transactions = controller.transactionItems;
        final textTheme = Theme.of(context).textTheme;

        return RefreshIndicator(
          onRefresh: controller.loadFinancialData,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
            children: [
              AmountHeadline(
                label: 'Frei verfügbar',
                amount: formatEuro(free / 100),
                size: 48,
              ),
              const SizedBox(height: 14),
              ThickBar(
                value: income <= 0
                    ? 0.0
                    : (expense / income).clamp(0.0, 1.0).toDouble(),
                over: income > 0 && expense > income,
                height: 14,
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: _Figure(
                      label: 'Ausgaben',
                      value: formatEuro(expense / 100),
                    ),
                  ),
                  Expanded(
                    child: _Figure(
                      label: 'Einnahmen',
                      value: formatEuro(income / 100),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: _Figure(
                      label: 'Kontostand',
                      value: formatEuro(balance / 100),
                    ),
                  ),
                  Expanded(
                    child: _Figure(
                      label: 'Prognose Monatsende',
                      value: monthEnd is int
                          ? formatEuro(monthEnd / 100)
                          : 'Nicht verfügbar',
                    ),
                  ),
                ],
              ),
              if (alerts.isNotEmpty) ...[
                const SizedBox(height: 20),
                for (final alert in alerts) _AlertRow(alert: alert),
              ],
              const SizedBox(height: 24),
              if (accounts.isEmpty)
                const QuietMessage(
                  'Auf dem Server sind noch keine Konten angelegt.',
                )
              else
                SizedBox(
                  height: 76,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: accounts.length,
                    separatorBuilder: (context, _) => const SizedBox(width: 10),
                    itemBuilder: (context, index) =>
                        _AccountTile(account: accounts[index]),
                  ),
                ),
              const SizedBox(height: 26),
              SectionTitle('Budgets', action: 'Alle', onAction: onOpenBudget),
              const SizedBox(height: 8),
              if (budgets.isEmpty)
                const QuietMessage('Noch keine Budgets eingerichtet.')
              else
                for (final budget in budgets) _BudgetRow(budget: budget),
              const SizedBox(height: 18),
              SectionTitle(
                'Letzte Umsätze',
                action: 'Alle',
                onAction: onOpenTransactions,
              ),
              if (transactions.isEmpty && controller.financeLoading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 20),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (transactions.isEmpty)
                const QuietMessage('Noch keine Buchungen vorhanden.')
              else
                for (var index = 0; index < 4; index++)
                  if (index < transactions.length) ...[
                    if (index > 0) const Divider(height: 1),
                    _TransactionRow(transaction: transactions[index]),
                  ],
              if (controller.financeError != null) ...[
                const SizedBox(height: 12),
                Text(
                  controller.financeError!,
                  style: textTheme.bodySmall?.copyWith(color: klar.warn),
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
}

int _asInt(dynamic value) => value is int ? value : 0;

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
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              loading ? Icons.sync_rounded : Icons.cloud_off_outlined,
              size: 30,
              color: klar.ink,
            ),
            const SizedBox(height: 14),
            Text(
              loading
                  ? 'Finanzdaten werden geladen'
                  : 'Finanzdaten sind gerade nicht verfügbar',
              textAlign: TextAlign.center,
              style: textTheme.titleMedium,
            ),
            if (error != null) ...[
              const SizedBox(height: 7),
              Text(
                error!,
                textAlign: TextAlign.center,
                style: textTheme.bodySmall,
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

class _Figure extends StatelessWidget {
  const _Figure({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: textTheme.bodySmall),
        const SizedBox(height: 2),
        Text(value, style: textTheme.titleMedium),
      ],
    );
  }
}

class _AccountTile extends StatelessWidget {
  const _AccountTile({required this.account});

  final Map<String, dynamic> account;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final known = account['balance_known'] == true;
    return SizedBox(
      width: 160,
      child: OutlinedPanel(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              account['name']?.toString() ?? 'Konto',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 4),
            Text(
              known
                  ? formatEuro(_asInt(account['balance_cents']) / 100)
                  : 'Nicht verfügbar',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: textTheme.titleMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _BudgetRow extends StatelessWidget {
  const _BudgetRow({required this.budget});

  final Map<String, dynamic> budget;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final limit = _asInt(budget['limit_cents']);
    final spent = _asInt(budget['spent_cents']);
    final remaining = _asInt(budget['remaining_cents']);
    final progress = limit <= 0
        ? 0.0
        : (spent / limit).clamp(0.0, 1.0).toDouble();
    final isOver = budget['state'] == 'over';

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  budget['name']?.toString() ?? 'Kategorie',
                  style: textTheme.bodyLarge,
                ),
              ),
              Text(
                isOver
                    ? '${formatEuro(remaining.abs() / 100)} drüber'
                    : '${formatEuro(remaining / 100)} übrig',
                style: textTheme.bodyMedium?.copyWith(
                  color: isOver ? klar.warn : klar.mutedInk,
                  fontWeight: isOver ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          ThickBar(value: progress, over: isOver),
        ],
      ),
    );
  }
}

class _AlertRow extends StatelessWidget {
  const _AlertRow({required this.alert});

  final Map<String, dynamic> alert;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final level = alert['level']?.toString() ?? 'info';
    final urgent = level == 'critical' || level == 'warning';
    final message = alert['message']?.toString() ?? '';

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: OutlinedPanel(
        padding: const EdgeInsets.all(13),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.info_outline_rounded,
              color: urgent ? klar.warn : klar.brand,
              size: 18,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    alert['title']?.toString() ?? 'Hinweis',
                    style: textTheme.titleMedium,
                  ),
                  if (message.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(message, style: textTheme.bodySmall),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TransactionRow extends StatelessWidget {
  const _TransactionRow({required this.transaction});

  final Map<String, dynamic> transaction;

  @override
  Widget build(BuildContext context) {
    final amount = _asInt(transaction['amount_cents']);
    final category = transaction['category'];
    final categoryName = category is Map ? category['name']?.toString() : null;
    final counterparty = transaction['counterparty']?.toString() ?? '';
    final purpose = transaction['purpose']?.toString() ?? '';
    final title = counterparty.isNotEmpty
        ? counterparty
        : purpose.isNotEmpty
        ? purpose
        : 'Buchung';
    final detail = <String>[
      if (categoryName != null && categoryName.isNotEmpty) categoryName,
      if (transaction['booking_date'] is String)
        formatShortDate(transaction['booking_date'] as String),
    ].join(' · ');

    return EntryRow(
      title: title,
      detail: detail.isEmpty ? 'Buchung' : detail,
      amount: formatSignedEuro(amount / 100),
      positive: amount > 0,
    );
  }
}
