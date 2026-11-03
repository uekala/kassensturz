import 'package:flutter/material.dart';

import '../../core/data/demo_finance_data.dart';
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
    final colors = Theme.of(context).colorScheme;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final data = controller.overviewData;
        if (data == null) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (controller.financeLoading)
                    const CircularProgressIndicator()
                  else
                    Icon(Icons.cloud_off_outlined, size: 42, color: colors.error),
                  const SizedBox(height: 14),
                  Text(
                    controller.financeLoading
                        ? 'Finanzdaten werden geladen'
                        : 'Finanzdaten konnten nicht geladen werden',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  if (controller.financeError != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      controller.financeError!,
                      textAlign: TextAlign.center,
                      style: TextStyle(color: colors.onSurfaceVariant),
                    ),
                  ],
                  const SizedBox(height: 14),
                  OutlinedButton.icon(
                    onPressed: controller.financeLoading
                        ? null
                        : controller.loadFinancialData,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Erneut versuchen'),
                  ),
                ],
              ),
            ),
          );
        }

        final forecast = _asMap(data['forecast']);
        final month = _asMap(data['month']);
        final accounts = _asMaps(data['accounts']);
        final budgets = _asMaps(data['budgets']);
        final alerts = _asMaps(data['alerts']);
        final balance = _asInt(forecast['balance_cents']);
        final free = _asInt(forecast['free_cents']);
        final end = forecast['month_end_cents'] is int
            ? formatEuro((forecast['month_end_cents'] as int) / 100)
            : '–';

        return RefreshIndicator(
          onRefresh: controller.loadFinancialData,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
            children: [
              Text(
                'Dein Überblick',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.6,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                'Live-Daten von deinem Kassensturz-Server',
                style: TextStyle(color: colors.onSurfaceVariant, fontSize: 12),
              ),
              const SizedBox(height: 17),
              _BalanceCard(
                free: formatEuro(free / 100),
                balance: formatEuro(balance / 100),
                monthEnd: end,
              ),
              const SizedBox(height: 18),
              _SectionTitle('DIESER MONAT'),
              const SizedBox(height: 9),
              Row(
                children: [
                  Expanded(
                    child: _MetricCard(
                      title: 'Einnahmen',
                      value: formatEuro(_asInt(month['income_cents']) / 100),
                      icon: Icons.south_west_rounded,
                      color: const Color(0xFF20836F),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _MetricCard(
                      title: 'Ausgaben',
                      value: formatEuro(_asInt(month['expense_cents']) / 100),
                      icon: Icons.north_east_rounded,
                      color: const Color(0xFF9A5B52),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              _SectionTitle('DEINE KONTEN'),
              const SizedBox(height: 8),
              if (accounts.isEmpty)
                const _EmptyText('Auf dem Server sind noch keine Konten angelegt.')
              else
                ...accounts.map((account) {
                  final known = account['balance_known'] == true;
                  return ListTile(
                    dense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 2),
                    leading: const CircleAvatar(
                      child: Icon(Icons.account_balance_outlined),
                    ),
                    title: Text(
                      account['name']?.toString() ?? 'Konto',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    subtitle: Text(account['type']?.toString() ?? 'Konto'),
                    trailing: Text(
                      known
                          ? formatEuro(_asInt(account['balance_cents']) / 100)
                          : 'Nicht verfügbar',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  );
                }),
              const SizedBox(height: 18),
              Row(
                children: [
                  const Expanded(child: _SectionTitle('BUDGETS')),
                  TextButton(
                    onPressed: onOpenBudget,
                    child: const Text('Details'),
                  ),
                ],
              ),
              if (budgets.isEmpty)
                const _EmptyText('Noch keine Budgets eingerichtet.')
              else
                ...budgets.map((budget) {
                  final limit = _asInt(budget['limit_cents']);
                  final spent = _asInt(budget['spent_cents']);
                  final remaining = _asInt(budget['remaining_cents']);
                  final progress = limit <= 0
                      ? 0.0
                      : (spent / limit).clamp(0.0, 1.0).toDouble();
                  return _BudgetRow(
                    name: budget['name']?.toString() ?? 'Kategorie',
                    spent: formatEuro(spent / 100),
                    limit: formatEuro(limit / 100),
                    remaining: formatEuro(remaining / 100),
                    progress: progress,
                    isOver: budget['state'] == 'over',
                  );
                }),
              if (alerts.isNotEmpty) ...[
                const SizedBox(height: 18),
                const _SectionTitle('HINWEISE'),
                const SizedBox(height: 8),
                ...alerts.map((alert) {
                  final level = alert['level']?.toString() ?? 'info';
                  final color = level == 'critical'
                      ? colors.error
                      : level == 'warning'
                      ? const Color(0xFFAA711B)
                      : colors.primary;
                  return Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: colors.outlineVariant),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.info_outline_rounded, color: color, size: 18),
                        const SizedBox(width: 9),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                alert['title']?.toString() ?? 'Hinweis',
                                style: const TextStyle(fontWeight: FontWeight.w700),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                alert['message']?.toString() ?? '',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: colors.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ],
              const SizedBox(height: 18),
              OutlinedButton.icon(
                onPressed: onOpenTransactions,
                icon: const Icon(Icons.receipt_long_outlined, size: 18),
                label: const Text('Alle Buchungen anzeigen'),
              ),
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

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({
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
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF176B5E), Color(0xFF10483F)],
        ),
        borderRadius: BorderRadius.circular(22),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.account_balance_wallet_outlined, color: Colors.white70, size: 17),
              SizedBox(width: 7),
              Text('Frei verfügbar', style: TextStyle(color: Colors.white70, fontSize: 13)),
              Spacer(),
              Text(
                'SERVER',
                style: TextStyle(
                  color: Color(0xFFBDE9D6),
                  fontSize: 9,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1,
                ),
              ),
            ],
          ),
          const SizedBox(height: 9),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              free,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 34,
                fontWeight: FontWeight.w800,
                letterSpacing: -1.2,
              ),
            ),
          ),
          const SizedBox(height: 18),
          Container(height: 1, color: Colors.white24),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(child: _WhiteMetric('Kontostand', balance)),
              const SizedBox(width: 12),
              Expanded(child: _WhiteMetric('Prognose Monatsende', monthEnd)),
            ],
          ),
        ],
      ),
    );
  }
}

class _WhiteMetric extends StatelessWidget {
  const _WhiteMetric(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(color: Colors.white60, fontSize: 10)),
      const SizedBox(height: 3),
      Text(
        value,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 15,
          fontWeight: FontWeight.w700,
        ),
      ),
    ],
  );
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
  });

  final String title;
  final String value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(17),
        border: Border.all(color: colors.outlineVariant.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(height: 8),
          Text(title, style: TextStyle(color: colors.onSurfaceVariant, fontSize: 11)),
          const SizedBox(height: 3),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title);

  final String title;

  @override
  Widget build(BuildContext context) => Text(
    title,
    style: Theme.of(context).textTheme.labelSmall?.copyWith(
      color: Theme.of(context).colorScheme.onSurfaceVariant,
      fontWeight: FontWeight.w800,
      letterSpacing: 1,
    ),
  );
}

class _BudgetRow extends StatelessWidget {
  const _BudgetRow({
    required this.name,
    required this.spent,
    required this.limit,
    required this.remaining,
    required this.progress,
    required this.isOver,
  });

  final String name;
  final String spent;
  final String limit;
  final String remaining;
  final double progress;
  final bool isOver;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(name, style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              Text(
                spent + ' / ' + limit,
                style: TextStyle(fontSize: 11, color: colors.onSurfaceVariant),
              ),
            ],
          ),
          const SizedBox(height: 6),
          LinearProgressIndicator(
            value: progress,
            minHeight: 6,
            borderRadius: BorderRadius.circular(8),
            color: isOver ? colors.error : colors.primary,
            backgroundColor: colors.surfaceContainerHighest,
          ),
          const SizedBox(height: 3),
          Text(
            remaining + ' übrig',
            style: TextStyle(fontSize: 10, color: colors.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _EmptyText extends StatelessWidget {
  const _EmptyText(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Text(
      text,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: 12,
      ),
    ),
  );
}
