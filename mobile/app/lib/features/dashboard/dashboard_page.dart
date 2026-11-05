import 'package:flutter/material.dart';

import '../../core/data/budget_controller.dart';
import '../../core/data/demo_finance_data.dart';
import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import 'live_dashboard_page.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({
    super.key,
    required this.onOpenTransactions,
    required this.onOpenBudget,
    required this.budgetController,
    required this.mobileController,
  });

  final VoidCallback onOpenTransactions;
  final VoidCallback onOpenBudget;
  final BudgetController budgetController;
  final MobileConnectionController mobileController;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: mobileController,
      builder: (context, _) {
        if (mobileController.isConnected) {
          return LiveDashboardPage(
            controller: mobileController,
            onOpenTransactions: onOpenTransactions,
            onOpenBudget: onOpenBudget,
          );
        }

        return AnimatedBuilder(
          animation: budgetController,
          builder: (context, child) {
            final currentMonth = DateTime.now();
            final budgetLoading = budgetController.isLoading;
            final budgetAvailable =
                !budgetLoading && budgetController.loadError == null;
            final budgetLimits = budgetController.limits;
            final budgetTotal = DemoFinanceData.totalBudget(budgetLimits);
            final budgetSpent = DemoFinanceData.spentForBudgets(
              currentMonth,
              budgetLimits,
            );
            final budgetRemaining = budgetTotal - budgetSpent;
            final budgetProgress = budgetTotal <= 0
                ? 0.0
                : (budgetSpent / budgetTotal).clamp(0.0, 1.0).toDouble();

            final monthTransactions =
                DemoFinanceData.transactions
                    .where(
                      (transaction) =>
                          transaction.date.year == currentMonth.year &&
                          transaction.date.month == currentMonth.month,
                    )
                    .toList()
                  ..sort((a, b) => b.date.compareTo(a.date));
            final income = monthTransactions
                .where((transaction) => !transaction.isExpense)
                .fold<double>(
                  0,
                  (total, transaction) => total + transaction.amount,
                );
            final expenses = monthTransactions
                .where((transaction) => transaction.isExpense)
                .fold<double>(
                  0,
                  (total, transaction) => total + transaction.amount.abs(),
                );
            final monthlyBalance = income - expenses;

            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
              children: [
                _DashboardHeading(month: _monthLabel(currentMonth)),
                const SizedBox(height: 18),
                _DemoBalanceCard(
                  balance: monthlyBalance,
                  month: _monthLabel(currentMonth),
                ),
                const SizedBox(height: 26),
                const _SectionHeading(title: 'Einnahmen & Ausgaben'),
                const SizedBox(height: 11),
                Row(
                  children: [
                    Expanded(
                      child: _CashFlowMetric(
                        label: 'Einnahmen',
                        value: formatEuro(income),
                        icon: Icons.south_west_rounded,
                        positive: true,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _CashFlowMetric(
                        label: 'Ausgaben',
                        value: formatEuro(expenses),
                        icon: Icons.north_east_rounded,
                        positive: false,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 25),
                _SectionHeading(
                  title: 'Dein Budget',
                  action: 'Details',
                  onAction: onOpenBudget,
                ),
                const SizedBox(height: 10),
                _BudgetSummary(
                  onTap: onOpenBudget,
                  budget: budgetTotal,
                  spent: budgetSpent,
                  remaining: budgetRemaining,
                  progress: budgetProgress,
                  available: budgetAvailable,
                  loading: budgetLoading,
                ),
                const SizedBox(height: 26),
                _SectionHeading(
                  title: 'Letzte Buchungen',
                  action: 'Alle anzeigen',
                  onAction: onOpenTransactions,
                ),
                const SizedBox(height: 5),
                if (monthTransactions.isEmpty)
                  const _EmptyState(
                    message: 'Für diesen Monat liegen keine Beispieldaten vor.',
                  )
                else
                  ...monthTransactions
                      .take(4)
                      .map(
                        (transaction) =>
                            _DemoTransactionTile(transaction: transaction),
                      ),
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: onOpenTransactions,
                  child: const Text('Alle Buchungen anzeigen'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  static String _monthLabel(DateTime date) {
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
    return '${months[date.month - 1]} ${date.year}';
  }
}

class _DashboardHeading extends StatelessWidget {
  const _DashboardHeading({required this.month});

  final String month;

  @override
  Widget build(BuildContext context) {
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

class _DemoBalanceCard extends StatelessWidget {
  const _DemoBalanceCard({required this.balance, required this.month});

  final double balance;
  final String month;

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
          Row(
            children: [
              const Expanded(
                child: Text(
                  'MONATSBILANZ',
                  style: TextStyle(
                    color: Color(0xFFD5E4DE),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text(
                  'BEISPIEL',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.7,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 11),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              formatSignedEuro(balance),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 32,
                height: 1.15,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.9,
              ),
            ),
          ),
          const SizedBox(height: 7),
          Text(
            'Einnahmen minus Ausgaben · $month',
            style: const TextStyle(color: Color(0xFFD5E4DE), fontSize: 12),
          ),
        ],
      ),
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
  const _SectionHeading({required this.title, this.action, this.onAction});

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

class _BudgetSummary extends StatelessWidget {
  const _BudgetSummary({
    required this.onTap,
    required this.budget,
    required this.spent,
    required this.remaining,
    required this.progress,
    required this.available,
    required this.loading,
  });

  final VoidCallback onTap;
  final double budget;
  final double spent;
  final double remaining;
  final double progress;
  final bool available;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Material(
      color: colors.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: colors.outlineVariant),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'Variable Ausgaben',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                  if (available)
                    Text(
                      '${(progress * 100).round()} %',
                      style: Theme.of(context).textTheme.labelMedium,
                    )
                  else
                    Text(
                      loading ? 'Wird geladen' : 'Nicht verfügbar',
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  const SizedBox(width: 4),
                  const Icon(Icons.chevron_right_rounded, size: 18),
                ],
              ),
              const SizedBox(height: 14),
              if (available) ...[
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: progress,
                    minHeight: 7,
                    backgroundColor: colors.surfaceContainerHigh,
                    valueColor: const AlwaysStoppedAnimation(AppTheme.accent),
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '${formatEuro(spent)} ausgegeben',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    Text(
                      formatEuro(budget),
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  ],
                ),
                const SizedBox(height: 7),
                Text(
                  '${formatEuro(remaining)} noch verfügbar',
                  style: Theme.of(
                    context,
                  ).textTheme.labelMedium?.copyWith(color: AppTheme.accent),
                ),
              ] else
                Text(
                  loading
                      ? 'Budgetdaten werden geladen.'
                      : 'Budgetinformationen können derzeit nicht angezeigt werden.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DemoTransactionTile extends StatelessWidget {
  const _DemoTransactionTile({required this.transaction});

  final DemoTransaction transaction;

  @override
  Widget build(BuildContext context) {
    final category = DemoFinanceData.category(transaction.categoryId);
    final colors = Theme.of(context).colorScheme;
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
        child: Icon(category.icon, size: 18, color: colors.onSurfaceVariant),
      ),
      title: Text(
        transaction.title,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(fontSize: 14),
      ),
      subtitle: Text(
        '${category.name} · ${formatDemoDate(transaction.date)}',
        style: Theme.of(context).textTheme.bodySmall,
      ),
      trailing: Text(
        formatSignedEuro(transaction.amount),
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
          fontSize: 13,
          color: transaction.isExpense ? colors.onSurface : AppTheme.accent,
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 18),
      child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
    );
  }
}
