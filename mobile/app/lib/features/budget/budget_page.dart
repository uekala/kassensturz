import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/data/demo_finance_data.dart';

class BudgetPage extends StatefulWidget {
  const BudgetPage({super.key});

  @override
  State<BudgetPage> createState() => _BudgetPageState();
}

class _BudgetPageState extends State<BudgetPage> {
  static final _months = [DateTime(2026, 11), DateTime(2026, 10)];

  int _selectedMonth = 0;
  late final Map<String, double> _limits =
      Map<String, double>.from(DemoFinanceData.defaultBudgetLimits);

  DateTime get _month => _months[_selectedMonth];
  String get _monthLabel =>
      _month.month == 11 ? 'November 2026' : 'Oktober 2026';
  double get _totalBudget => DemoFinanceData.totalBudget(_limits);
  double get _totalSpent => DemoFinanceData.spentForBudgets(_month, _limits);
  double get _remaining => _totalBudget - _totalSpent;
  double get _progress => _totalBudget <= 0
      ? 0
      : (_totalSpent / _totalBudget).clamp(0.0, 1.0).toDouble();

  List<DemoCategory> get _budgetCategories => DemoFinanceData.categories
      .where((category) => _limits.containsKey(category.id))
      .toList();

  Future<void> _addBudget() async {
    final draft = await _editBudgetDialog();
    if (draft == null) return;
    setState(() => _limits[draft.categoryId] = draft.limit);
  }

  Future<void> _editBudget(String categoryId) async {
    final draft = await _editBudgetDialog(
      currentCategoryId: categoryId,
      currentLimit: _limits[categoryId],
    );
    if (draft == null) return;

    setState(() {
      if (draft.categoryId != categoryId) {
        _limits.remove(categoryId);
      }
      _limits[draft.categoryId] = draft.limit;
    });
  }

  Future<void> _deleteBudget(String categoryId) async {
    final category = DemoFinanceData.category(categoryId);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Budget löschen?'),
        content: Text('Das Budget für ${category.name} wird entfernt.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Löschen'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      setState(() => _limits.remove(categoryId));
    }
  }

  Future<_BudgetDraft?> _editBudgetDialog({
    String? currentCategoryId,
    double? currentLimit,
  }) {
    final availableCategories = DemoFinanceData.categories.where((category) {
      final isBudgetable = category.id != 'housing' && category.id != 'income';
      final isCurrent = category.id == currentCategoryId;
      return isBudgetable && (!_limits.containsKey(category.id) || isCurrent);
    }).toList();

    if (availableCategories.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content:
              Text('Für alle verfügbaren Kategorien gibt es bereits Budgets.'),
        ),
      );
      return Future.value(null);
    }

    var selectedCategoryId = currentCategoryId ?? availableCategories.first.id;
    var amountText = currentLimit?.toStringAsFixed(2) ?? '';
    final formKey = GlobalKey<FormState>();

    return showDialog<_BudgetDraft>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(
            currentCategoryId == null
                ? 'Budget hinzufügen'
                : 'Budget bearbeiten',
          ),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: selectedCategoryId,
                  decoration: const InputDecoration(
                    labelText: 'Kategorie',
                    border: OutlineInputBorder(),
                  ),
                  items: availableCategories
                      .map(
                        (category) => DropdownMenuItem(
                          value: category.id,
                          child: Text(category.name),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    if (value != null) {
                      setDialogState(() => selectedCategoryId = value);
                    }
                  },
                ),
                const SizedBox(height: 14),
                TextFormField(
                  initialValue: amountText,
                  autofocus: true,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  inputFormatters: [
                    FilteringTextInputFormatter.allow(RegExp(r'[0-9,.]')),
                  ],
                  decoration: const InputDecoration(
                    labelText: 'Monatliches Limit',
                    suffixText: '€',
                    border: OutlineInputBorder(),
                  ),
                  onSaved: (value) => amountText = value ?? '',
                  validator: (value) {
                    final normalized = (value ?? '').replaceAll(',', '.');
                    final amount = double.tryParse(normalized);
                    if (amount == null || amount <= 0) {
                      return 'Bitte einen Betrag größer 0 eingeben.';
                    }
                    return null;
                  },
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Abbrechen'),
            ),
            FilledButton(
              onPressed: () {
                if (!formKey.currentState!.validate()) return;
                formKey.currentState!.save();
                final limit = double.parse(amountText.replaceAll(',', '.'));
                Navigator.pop(
                  dialogContext,
                  _BudgetDraft(
                    categoryId: selectedCategoryId,
                    limit: limit,
                  ),
                );
              },
              child: const Text('Speichern'),
            ),
          ],
        ),
      ),
    );
  }

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
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            ...List.generate(_months.length, (index) {
              final label =
                  _months[index].month == 11 ? 'November 2026' : 'Oktober 2026';
              return ChoiceChip(
                label: Text(label),
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
            FilledButton.tonalIcon(
              onPressed: _addBudget,
              icon: const Icon(Icons.add_rounded, size: 18),
              label: const Text('Hinzufügen'),
            ),
          ],
        ),
        const SizedBox(height: 14),
        _BudgetSummaryCard(
          budget: _totalBudget,
          spent: _totalSpent,
          remaining: _remaining,
          progress: _progress,
          month: _monthLabel,
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
              '${_budgetCategories.length} Kategorien',
              style: textTheme.labelSmall?.copyWith(
                color: colors.onSurfaceVariant,
              ),
            ),
          ],
        ),
        const SizedBox(height: 9),
        if (_budgetCategories.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 28),
            child: Center(child: Text('Noch keine Budgets angelegt.')),
          )
        else
          ..._budgetCategories.map((category) {
            final limit = _limits[category.id]!;
            final spent = DemoFinanceData.spentForCategory(category.id, _month);
            return _CategoryBudgetCard(
              category: category,
              spent: spent,
              limit: limit,
              onEdit: () => _editBudget(category.id),
              onDelete: () => _deleteBudget(category.id),
            );
          }),
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
                      ? 'Im $_monthLabel sind noch ${formatEuro(_remaining)} deines Budgets übrig.'
                      : 'Dein Budget ist um ${formatEuro(_remaining.abs())} überschritten.',
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
            'Ausgaben aus den Buchungen berechnet. Änderungen gelten nur in dieser Demo-Sitzung.',
            textAlign: TextAlign.center,
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
              formatEuro(remaining),
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
              _SummaryValue(label: 'Ausgegeben', value: formatEuro(spent)),
              _SummaryValue(label: 'Gesamtbudget', value: formatEuro(budget)),
              _SummaryValue(
                label: 'Genutzt',
                value:
                    budget <= 0 ? '0 %' : '${(spent / budget * 100).round()} %',
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
  const _CategoryBudgetCard({
    required this.category,
    required this.spent,
    required this.limit,
    required this.onEdit,
    required this.onDelete,
  });

  final DemoCategory category;
  final double spent;
  final double limit;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final rawProgress = limit <= 0 ? 0.0 : spent / limit;
    final progress = rawProgress.clamp(0.0, 1.0).toDouble();
    final overBudget = rawProgress > 1;
    final progressColor = overBudget ? colors.error : category.color;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
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
                formatEuro(spent),
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 13,
                ),
              ),
              IconButton(
                tooltip: 'Budget bearbeiten: ${category.name}',
                onPressed: onEdit,
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.edit_outlined, size: 17),
              ),
              IconButton(
                tooltip: 'Budget löschen: ${category.name}',
                onPressed: onDelete,
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.delete_outline_rounded, size: 18),
              ),
            ],
          ),
          const SizedBox(height: 8),
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
                'von ${formatEuro(limit)}',
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

class _BudgetDraft {
  const _BudgetDraft({
    required this.categoryId,
    required this.limit,
  });

  final String categoryId;
  final double limit;
}
