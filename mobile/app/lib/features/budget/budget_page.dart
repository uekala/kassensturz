import 'package:flutter/material.dart';

class BudgetPage extends StatefulWidget {
  const BudgetPage({super.key});

  @override
  State<BudgetPage> createState() => _BudgetPageState();
}

class _BudgetPageState extends State<BudgetPage> {
  int _selectedMonth = 0;

  static const _months = [
    _BudgetMonth(
      title: 'November 2026',
      budget: 1000,
      spent: 379.60,
      categories: [
        _BudgetCategory(
          name: 'Lebensmittel',
          spent: 248.26,
          limit: 350,
          icon: Icons.shopping_basket_outlined,
          color: Color(0xFF20836F),
        ),
        _BudgetCategory(
          name: 'Mobilität',
          spent: 86,
          limit: 200,
          icon: Icons.directions_car_outlined,
          color: Color(0xFF526A9B),
        ),
        _BudgetCategory(
          name: 'Freizeit',
          spent: 45.34,
          limit: 150,
          icon: Icons.sports_esports_outlined,
          color: Color(0xFF9A6A35),
        ),
        _BudgetCategory(
          name: 'Haushalt',
          spent: 0,
          limit: 100,
          icon: Icons.chair_outlined,
          color: Color(0xFF8065A5),
        ),
        _BudgetCategory(
          name: 'Sonstiges',
          spent: 0,
          limit: 200,
          icon: Icons.more_horiz_rounded,
          color: Color(0xFF64736F),
        ),
      ],
    ),
    _BudgetMonth(
      title: 'Oktober 2026',
      budget: 1000,
      spent: 512.30,
      categories: [
        _BudgetCategory(
          name: 'Lebensmittel',
          spent: 302.10,
          limit: 350,
          icon: Icons.shopping_basket_outlined,
          color: Color(0xFF20836F),
        ),
        _BudgetCategory(
          name: 'Mobilität',
          spent: 120,
          limit: 200,
          icon: Icons.directions_car_outlined,
          color: Color(0xFF526A9B),
        ),
        _BudgetCategory(
          name: 'Freizeit',
          spent: 64.20,
          limit: 150,
          icon: Icons.sports_esports_outlined,
          color: Color(0xFF9A6A35),
        ),
        _BudgetCategory(
          name: 'Haushalt',
          spent: 26,
          limit: 100,
          icon: Icons.chair_outlined,
          color: Color(0xFF8065A5),
        ),
        _BudgetCategory(
          name: 'Sonstiges',
          spent: 0,
          limit: 200,
          icon: Icons.more_horiz_rounded,
          color: Color(0xFF64736F),
        ),
      ],
    ),
  ];

  _BudgetMonth get _month => _months[_selectedMonth];
  double get _remaining => _month.budget - _month.spent;
  double get _progress =>
      (_month.spent / _month.budget).clamp(0.0, 1.0).toDouble();

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
      children: [
        Text(
          'Deine Budgets',
          style: textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          'Behalte deine variablen Ausgaben im Blick.',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          children: List.generate(_months.length, (index) {
            return ChoiceChip(
              label: Text(_months[index].title),
              selected: _selectedMonth == index,
              showCheckmark: false,
              onSelected: (_) => setState(() => _selectedMonth = index),
              labelStyle: TextStyle(
                fontWeight: FontWeight.w700,
                color: _selectedMonth == index
                    ? colors.onPrimary
                    : colors.onSurface,
              ),
              selectedColor: colors.primary,
              backgroundColor: Colors.white,
              side: BorderSide(
                color: _selectedMonth == index
                    ? colors.primary
                    : colors.outlineVariant,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
              ),
            );
          }),
        ),
        const SizedBox(height: 14),
        _BudgetSummaryCard(
          budget: _month.budget,
          spent: _month.spent,
          remaining: _remaining,
          progress: _progress,
          month: _month.title,
        ),
        const SizedBox(height: 22),
        Row(
          children: [
            Expanded(
              child: Text(
                'Budget nach Kategorien',
                style: textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.2,
                ),
              ),
            ),
            Text(
              '${_month.categories.length} Kategorien',
              style: textTheme.labelSmall?.copyWith(
                color: colors.onSurfaceVariant,
              ),
            ),
          ],
        ),
        const SizedBox(height: 9),
        ..._month.categories.map((category) => _CategoryBudgetCard(
              category: category,
            )),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(15),
          decoration: BoxDecoration(
            color: const Color(0xFFEAF3EF),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Icons.lightbulb_outline_rounded,
                color: Color(0xFF176B5E),
                size: 20,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _remaining >= 0
                      ? 'Du hast in ${_month.title} noch ${_formatEuro(_remaining)} deines variablen Budgets übrig.'
                      : 'Dein variables Budget ist um ${_formatEuro(_remaining.abs())} überschritten.',
                  style: const TextStyle(
                    color: Color(0xFF24584E),
                    fontSize: 12,
                    height: 1.45,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Center(
          child: Text(
            'Alle Beträge sind Beispieldaten.',
            style: textTheme.labelSmall?.copyWith(
              color: colors.onSurfaceVariant,
            ),
          ),
        ),
      ],
    );
  }
}

class _BudgetSummaryCard extends StatelessWidget {
  const _BudgetSummaryCard({
    required this.budget,
    required this.spent,
    required this.remaining,
    required this.progress,
    required this.month,
  });

  final double budget;
  final double spent;
  final double remaining;
  final double progress;
  final String month;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(19),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF176B5E), Color(0xFF10483F)],
        ),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'VARIABLES BUDGET · $month',
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 10,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.7,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Noch verfügbar',
            style: TextStyle(color: Colors.white70, fontSize: 12),
          ),
          const SizedBox(height: 2),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              _formatEuro(remaining),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 31,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.8,
              ),
            ),
          ),
          const SizedBox(height: 17),
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 8,
              backgroundColor: Colors.white24,
              valueColor: const AlwaysStoppedAnimation(Color(0xFFBDE9D6)),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _SummaryValue(label: 'Ausgegeben', value: _formatEuro(spent)),
              _SummaryValue(label: 'Gesamtbudget', value: _formatEuro(budget)),
              _SummaryValue(
                label: 'Genutzt',
                value: '${(progress * 100).round()} %',
                alignEnd: true,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SummaryValue extends StatelessWidget {
  const _SummaryValue({
    required this.label,
    required this.value,
    this.alignEnd = false,
  });

  final String label;
  final String value;
  final bool alignEnd;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment:
          alignEnd ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(color: Colors.white70, fontSize: 10),
        ),
        const SizedBox(height: 3),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    );
  }
}

class _CategoryBudgetCard extends StatelessWidget {
  const _CategoryBudgetCard({required this.category});

  final _BudgetCategory category;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final rawProgress = category.spent / category.limit;
    final progress = rawProgress.clamp(0.0, 1.0).toDouble();
    final overBudget = rawProgress > 1;
    final progressColor = overBudget ? colors.error : category.color;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(
          color: colors.outlineVariant.withValues(alpha: 0.4),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: category.color.withValues(alpha: 0.11),
                  borderRadius: BorderRadius.circular(11),
                ),
                child: Icon(category.icon, color: category.color, size: 19),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Text(
                  category.name,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                ),
              ),
              Text(
                _formatEuro(category.spent),
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 13,
                ),
              ),
            ],
          ),
          const SizedBox(height: 11),
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 7,
              backgroundColor: const Color(0xFFE8EFEC),
              valueColor: AlwaysStoppedAnimation(progressColor),
            ),
          ),
          const SizedBox(height: 7),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                overBudget
                    ? 'Budget überschritten'
                    : '${(rawProgress * 100).round()} % genutzt',
                style: TextStyle(
                  color: overBudget ? colors.error : colors.onSurfaceVariant,
                  fontSize: 10,
                  fontWeight: overBudget ? FontWeight.w700 : FontWeight.w500,
                ),
              ),
              Text(
                'von ${_formatEuro(category.limit)}',
                style: TextStyle(
                  color: colors.onSurfaceVariant,
                  fontSize: 10,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _BudgetMonth {
  const _BudgetMonth({
    required this.title,
    required this.budget,
    required this.spent,
    required this.categories,
  });

  final String title;
  final double budget;
  final double spent;
  final List<_BudgetCategory> categories;
}

class _BudgetCategory {
  const _BudgetCategory({
    required this.name,
    required this.spent,
    required this.limit,
    required this.icon,
    required this.color,
  });

  final String name;
  final double spent;
  final double limit;
  final IconData icon;
  final Color color;
}

String _formatEuro(double value) {
  final parts = value.abs().toStringAsFixed(2).split('.');
  final whole = parts[0].replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => '.',
  );
  final sign = value < 0 ? '−' : '';
  return '$sign$whole,${parts[1]} €';
}
