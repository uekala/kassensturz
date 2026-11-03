import 'package:flutter/material.dart';

import '../../core/data/budget_controller.dart';
import '../../core/data/demo_finance_data.dart';
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
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

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
        final currentMonth = DateTime(2026, 11);
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

        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
          children: [
            Text(
              'Dein Überblick',
              style: textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.w800,
                letterSpacing: -0.6,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              'Deine Finanzen auf einen Blick.',
              style: textTheme.bodyMedium?.copyWith(
                color: colors.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 17),
            const _BalanceCard(),
            const SizedBox(height: 22),
            const _SectionHeading(title: 'Kurzüberblick'),
            const SizedBox(height: 10),
            Row(
              children: [
                const Expanded(
                  child: _MetricCard(
                    label: 'Fixkosten',
                    value: '1.120,00 €',
                    caption: 'pro Monat',
                    icon: Icons.event_repeat_rounded,
                    accent: Color(0xFF526A9B),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _MetricCard(
                    label: 'Budget frei',
                    value: budgetAvailable ? formatEuro(budgetRemaining) : '–',
                    caption: budgetAvailable
                        ? 'diesen Monat'
                        : budgetLoading
                        ? 'Wird geladen'
                        : 'Nicht verfügbar',
                    icon: Icons.pie_chart_outline_rounded,
                    accent: const Color(0xFF20836F),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _BudgetCard(
              onTap: onOpenBudget,
              budget: budgetTotal,
              spent: budgetSpent,
              progress: budgetProgress,
              available: budgetAvailable,
              loading: budgetLoading,
            ),
            const SizedBox(height: 24),
            _SectionHeading(
              title: 'Letzte Aktivitäten',
              trailing: Text(
                'Beispielwerte',
                style: textTheme.labelSmall?.copyWith(
                  color: colors.onSurfaceVariant,
                ),
              ),
            ),
            const SizedBox(height: 6),
            const _ActivityTile(
              icon: Icons.shopping_basket_outlined,
              title: 'REWE',
              subtitle: 'Lebensmittel · Heute',
              amount: '−48,26 €',
              negative: true,
            ),
            const _ActivityTile(
              icon: Icons.home_outlined,
              title: 'Miete',
              subtitle: 'Wohnen · 02.11.2026',
              amount: '−980,00 €',
              negative: true,
            ),
            const _ActivityTile(
              icon: Icons.payments_outlined,
              title: 'Gehalt',
              subtitle: 'Einkommen · 01.11.2026',
              amount: '+2.750,00 €',
              negative: false,
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: onOpenTransactions,
              icon: const Icon(Icons.receipt_long_outlined, size: 18),
              label: const Text('Alle Buchungen anzeigen'),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(46),
                foregroundColor: colors.primary,
                side: BorderSide(color: colors.outlineVariant),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(13),
                ),
              ),
            ),
          ],
        );
          },
        );
      },
    );
  }
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard();

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
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF10483F).withValues(alpha: 0.16),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.account_balance_wallet_outlined,
                color: Colors.white70,
                size: 17,
              ),
              SizedBox(width: 7),
              Text(
                'Frei verfügbar',
                style: TextStyle(color: Colors.white70, fontSize: 13),
              ),
              Spacer(),
              Text(
                'BEISPIEL',
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
          const FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              '2.486,30 €',
              style: TextStyle(
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
          const Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                Icons.trending_up_rounded,
                color: Color(0xFFBDE9D6),
                size: 19,
              ),
              SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Prognose zum Monatsende',
                      style: TextStyle(color: Colors.white70, fontSize: 11),
                    ),
                    SizedBox(height: 2),
                    Text(
                      '+340,20 €',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.insights_outlined, color: Colors.white54, size: 20),
            ],
          ),
        ],
      ),
    );
  }
}

class _SectionHeading extends StatelessWidget {
  const _SectionHeading({required this.title, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.2,
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.caption,
    required this.icon,
    required this.accent,
  });

  final String label;
  final String value;
  final String caption;
  final IconData icon;
  final Color accent;

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
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: accent.withValues(alpha: 0.11),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: accent, size: 18),
          ),
          const SizedBox(height: 11),
          Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.labelMedium?.copyWith(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: const TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.4,
              ),
            ),
          ),
          const SizedBox(height: 2),
          Text(
            caption,
            style: Theme.of(
              context,
            ).textTheme.labelSmall?.copyWith(color: colors.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _BudgetCard extends StatelessWidget {
  const _BudgetCard({
    required this.onTap,
    required this.budget,
    required this.spent,
    required this.progress,
    required this.available,
    required this.loading,
  });

  final VoidCallback onTap;
  final double budget;
  final double spent;
  final double progress;
  final bool available;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(17),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(17),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(17),
            border: Border.all(
              color: colors.outlineVariant.withValues(alpha: 0.5),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.pie_chart_outline_rounded, size: 18),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'Variable Ausgaben',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                  if (available)
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '${(progress * 100).round()} % genutzt',
                          style: Theme.of(context).textTheme.labelMedium
                              ?.copyWith(color: colors.onSurfaceVariant),
                        ),
                        const SizedBox(width: 4),
                        const Icon(Icons.chevron_right_rounded, size: 18),
                      ],
                    )
                  else
                    Text(
                      loading ? 'Wird geladen…' : 'Nicht verfügbar',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: colors.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 13),
              if (available) ...[
                ClipRRect(
                  borderRadius: BorderRadius.circular(20),
                  child: LinearProgressIndicator(
                    value: progress,
                    minHeight: 8,
                    backgroundColor: Color(0xFFE8EFEC),
                    valueColor: AlwaysStoppedAnimation(Color(0xFF20836F)),
                  ),
                ),
                const SizedBox(height: 9),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '${formatEuro(spent)} ausgegeben',
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF65736F),
                      ),
                    ),
                    Text(
                      formatEuro(budget),
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ] else
                Text(
                  'Budgetinformationen können derzeit nicht angezeigt werden.',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: colors.onSurfaceVariant,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActivityTile extends StatelessWidget {
  const _ActivityTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.amount,
    required this.negative,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String amount;
  final bool negative;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 2),
      leading: CircleAvatar(
        radius: 20,
        backgroundColor: colors.primaryContainer,
        foregroundColor: colors.onPrimaryContainer,
        child: Icon(icon, size: 19),
      ),
      title: Text(
        title,
        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
      ),
      subtitle: Text(subtitle, style: const TextStyle(fontSize: 11)),
      trailing: Text(
        amount,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w700,
          color: negative ? colors.onSurface : colors.primary,
        ),
      ),
    );
  }
}
