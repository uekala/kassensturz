import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';
import '../budget/budget_editor_sheet.dart';

/// Accounts as the server reports them; they are managed in Home Assistant.
class ServerAccountsPage extends StatelessWidget {
  const ServerAccountsPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final data = controller.overviewData;
    final accounts = _maps(data?['accounts']);
    final textTheme = Theme.of(context).textTheme;
    final known = accounts
        .where((item) => item['balance_known'] == true)
        .toList();
    final total = known.fold<int>(
      0,
      (sum, item) => sum + _integer(item['balance_cents']),
    );
    final daily = known
        .where((item) => item['in_forecast'] != false)
        .fold<int>(0, (sum, item) => sum + _integer(item['balance_cents']));
    final depots = known
        .where((item) => item['type'] == 'depot')
        .fold<int>(0, (sum, item) => sum + _integer(item['balance_cents']));
    final reserves = total - daily - depots;
    final note = [
      'Alltag ${formatEuro(daily / 100)}',
      if (reserves != 0) 'Rücklagen ${formatEuro(reserves / 100)}',
      if (depots != 0) 'Depots ${formatEuro(depots / 100)}',
    ].join(' · ');

    return RefreshIndicator(
      onRefresh: controller.loadFinancialData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          AmountHeadline(
            label: 'Vermögen',
            amount: formatEuro(total / 100),
            note: note,
          ),
          const SizedBox(height: 22),
          if (controller.financeLoading && data == null)
            const Center(child: CircularProgressIndicator())
          else if (data == null)
            _LoadError(
              message: controller.financeError,
              onRetry: controller.loadFinancialData,
            )
          else if (accounts.isEmpty)
            const QuietMessage('Der Server liefert noch keine Konten.')
          else
            for (final account in accounts) _AccountPanel(account: account),
          if (controller.financeError != null && data != null) ...[
            const SizedBox(height: 8),
            Text(
              controller.financeError!,
              style: textTheme.bodySmall?.copyWith(color: klar.warn),
            ),
          ],
          const SizedBox(height: 10),
          Text(
            'Konten legst du in Kassensturz in Home Assistant an, dort trägst '
            'du auch den Wert eines Depots ein. Umsätze von Hand gehen nur auf '
            'Konten ohne Bankabruf.',
            style: textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _AccountPanel extends StatelessWidget {
  const _AccountPanel({required this.account});

  final Map<String, dynamic> account;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final balance = _integer(account['balance_cents']);
    final known = account['balance_known'] == true;
    final date = _string(account['balance_date'], '');
    final type = _string(account['type'], '');
    final previous = account['previous_value_cents'];
    final previousDate = _string(account['previous_value_date'], '');
    final detail = [
      _typeLabels[type] ?? 'Konto',
      if (date.isNotEmpty) 'Stand ${formatShortDate(date)}',
      if (previous is int && previousDate.isNotEmpty)
        '${formatSignedEuro((balance - previous) / 100)} seit '
            '${formatShortDate(previousDate)}',
      if (!known) type == 'depot' ? 'Wert fehlt' : 'Saldo nicht bestätigt',
    ].join(' · ');

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: OutlinedPanel(
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _string(account['name'], 'Konto'),
                    style: textTheme.titleMedium,
                  ),
                  const SizedBox(height: 3),
                  Text(detail, style: textTheme.bodySmall),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Text(
              known ? formatEuro(balance / 100) : '–',
              style: textTheme.titleMedium?.copyWith(
                color: balance < 0 ? klar.warn : klar.ink,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Budgets of the current month as the server reports them.
class ServerBudgetPage extends StatelessWidget {
  const ServerBudgetPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final data = controller.overviewData;
    final budgets = _maps(data?['budgets']);
    final textTheme = Theme.of(context).textTheme;
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
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          AmountHeadline(
            label: remaining < 0 ? 'Über dem Budget' : 'Noch verfügbar',
            amount: formatEuro(remaining.abs() / 100),
            note:
                'Ausgegeben: ${formatEuro(totalSpent / 100)} '
                'von ${formatEuro(totalLimit / 100)}',
            size: 40,
          ),
          const SizedBox(height: 12),
          ThickBar(
            value: totalLimit <= 0
                ? 0.0
                : (totalSpent / totalLimit).clamp(0.0, 1.0).toDouble(),
            over: remaining < 0,
            height: 14,
          ),
          const SizedBox(height: 24),
          if (controller.financeLoading && data == null)
            const Center(child: CircularProgressIndicator())
          else if (data == null)
            _LoadError(
              message: controller.financeError,
              onRetry: controller.loadFinancialData,
            )
          else if (budgets.isEmpty)
            const QuietMessage('Noch keine Budgets.')
          else
            for (final budget in budgets)
              _BudgetBlock(
                budget: budget,
                onTap: controller.canEditBudgets
                    ? () => showBudgetEditor(
                        context,
                        controller: controller,
                        categoryId: _integer(budget['category_id']),
                        categoryName: _string(budget['name'], ''),
                        limitCents: _integer(budget['limit_cents']),
                      )
                    : null,
              ),
          if (controller.canEditBudgets && data != null) ...[
            const SizedBox(height: 4),
            OutlinedButton.icon(
              onPressed: () =>
                  showBudgetEditor(context, controller: controller),
              icon: const Icon(Icons.add),
              label: const Text('Budget anlegen'),
            ),
          ],
          if (controller.financeError != null && data != null) ...[
            const SizedBox(height: 8),
            Text(
              controller.financeError!,
              style: textTheme.bodySmall?.copyWith(color: klar.warn),
            ),
          ],
          const SizedBox(height: 6),
          Text(
            controller.canEditBudgets
                ? 'Tippe auf ein Budget, um es zu ändern oder zu entfernen.'
                : 'Budgets änderst du in Kassensturz in Home Assistant. Ab '
                      'Server 0.3.9 geht das auch hier.',
            style: textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _BudgetBlock extends StatelessWidget {
  const _BudgetBlock({required this.budget, this.onTap});

  final Map<String, dynamic> budget;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final limit = _integer(budget['limit_cents']);
    final spent = _integer(budget['spent_cents']);
    final left = _integer(budget['remaining_cents']);
    final progress = limit <= 0
        ? 0.0
        : (spent / limit).clamp(0.0, 1.0).toDouble();
    final over = spent > limit || _string(budget['state'], 'ok') == 'over';

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _string(budget['name'], 'Budget'),
                    style: textTheme.titleMedium,
                  ),
                ),
                Text(
                  '${formatEuro(spent / 100)} von ${formatEuro(limit / 100)}',
                  style: textTheme.bodyMedium,
                ),
              ],
            ),
            const SizedBox(height: 7),
            ThickBar(value: progress, over: over),
            const SizedBox(height: 6),
            Text(
              over
                  ? '${formatEuro(left.abs() / 100)} über dem Budget'
                  : '${formatEuro(left / 100)} übrig',
              style: textTheme.bodySmall?.copyWith(
                color: over ? klar.warn : klar.mutedInk,
                fontWeight: over ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ],
        ),
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

const _typeLabels = {
  'giro': 'Girokonto',
  'tagesgeld': 'Tagesgeld',
  'kreditkarte': 'Kreditkarte',
  'paypal': 'PayPal',
  'depot': 'Depot',
  'sonstiges': 'Sonstiges',
};

List<Map<String, dynamic>> _maps(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
}

int _integer(dynamic value) => value is int ? value : 0;

String _string(dynamic value, String fallback) =>
    value is String && value.isNotEmpty ? value : fallback;
