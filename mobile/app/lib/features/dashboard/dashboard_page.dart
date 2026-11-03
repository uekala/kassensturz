import 'package:flutter/material.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(
          'Dein Überblick',
          style: textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.6,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Deine Finanzen auf einen Blick.',
          style: textTheme.bodyMedium?.copyWith(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.deepGreen,
            borderRadius: BorderRadius.circular(22),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Frei verfügbar · Beispiel',
                style: TextStyle(color: Colors.white70, fontSize: 13),
              ),
              const SizedBox(height: 8),
              const Text(
                '2.486,30 €',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -1,
                ),
              ),
              const SizedBox(height: 18),
              Container(height: 1, color: Colors.white24),
              const SizedBox(height: 14),
              const Row(
                children: [
                  Icon(Icons.trending_up_rounded,
                      color: Color(0xFFBDE9D6), size: 19),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Prognose zum Monatsende: +340,20 €',
                      style: TextStyle(color: Colors.white, fontSize: 13),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        Row(
          children: const [
            Expanded(
              child: _MetricCard(
                label: 'Fixkosten',
                value: '1.120,00 €',
                caption: 'pro Monat',
                icon: Icons.event_repeat_rounded,
              ),
            ),
            SizedBox(width: 12),
            Expanded(
              child: _MetricCard(
                label: 'Budget übrig',
                value: '620,40 €',
                caption: 'diesen Monat',
                icon: Icons.pie_chart_outline_rounded,
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Letzte Aktivitäten',
                style: textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w800)),
            Text('Beispiele',
                style: textTheme.labelMedium
                    ?.copyWith(color: colors.onSurfaceVariant)),
          ],
        ),
        const SizedBox(height: 8),
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
          subtitle: 'Wohnen · Gestern',
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
  });

  final String label;
  final String value;
  final String caption;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border:
            Border.all(color: colors.outlineVariant.withValues(alpha: 0.45)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: colors.primary, size: 20),
          const SizedBox(height: 12),
          Text(label,
              style: Theme.of(context)
                  .textTheme
                  .labelMedium
                  ?.copyWith(color: colors.onSurfaceVariant)),
          const SizedBox(height: 4),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(value,
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          ),
          const SizedBox(height: 3),
          Text(caption,
              style: Theme.of(context)
                  .textTheme
                  .labelSmall
                  ?.copyWith(color: colors.onSurfaceVariant)),
        ],
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
        backgroundColor: colors.primaryContainer,
        foregroundColor: colors.onPrimaryContainer,
        child: Icon(icon, size: 20),
      ),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(subtitle),
      trailing: Text(
        amount,
        style: TextStyle(
          fontWeight: FontWeight.w700,
          color: negative ? colors.onSurface : colors.primary,
        ),
      ),
    );
  }
}

abstract final class AppColors {
  static const deepGreen = Color(0xFF104E46);
}
