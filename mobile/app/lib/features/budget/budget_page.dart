import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/data/budget_controller.dart';
import '../../core/data/demo_finance_data.dart';
import '../../core/design/app_theme.dart';

class BudgetPage extends StatefulWidget {
  const BudgetPage({super.key, required this.controller});

  final BudgetController controller;

  @override
  State<BudgetPage> createState() => _BudgetPageState();
}

class _BudgetPageState extends State<BudgetPage> {
  static final _months = [
    DateTime.now(),
    DateTime(DateTime.now().year, DateTime.now().month - 1),
  ];

  int _selectedMonth = 0;

  Map<String, double> get _limits => widget.controller.limits;
  DateTime get _month => _months[_selectedMonth];
  String get _monthLabel {
    const names = [
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
    return '${names[_month.month - 1]} ${_month.year}';
  }

  double get _totalBudget => DemoFinanceData.totalBudget(_limits);
  double get _totalSpent => DemoFinanceData.spentForBudgets(_month, _limits);
  double get _remaining => _totalBudget - _totalSpent;
  double get _progress => _totalBudget <= 0
      ? 0
      : (_totalSpent / _totalBudget).clamp(0.0, 1.0).toDouble();

  List<DemoCategory> get _budgetCategories => DemoFinanceData.categories
      .where((category) => _limits.containsKey(category.id))
      .toList();

  Future<void> _saveLimits(Map<String, double> nextLimits) async {
    final saved = await widget.controller.saveLimits(nextLimits);
    if (!saved && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Budget konnte nicht gespeichert werden. Bitte erneut versuchen.',
          ),
        ),
      );
    }
  }

  Future<void> _addBudget() async {
    final draft = await _editBudgetDialog();
    if (draft == null) return;

    final next = Map<String, double>.from(_limits)
      ..[draft.categoryId] = draft.limit;
    await _saveLimits(next);
  }

  Future<void> _editBudget(String categoryId) async {
    final draft = await _editBudgetDialog(
      currentCategoryId: categoryId,
      currentLimit: _limits[categoryId],
    );
    if (draft == null) return;

    final next = Map<String, double>.from(_limits);
    if (draft.categoryId != categoryId) {
      next.remove(categoryId);
    }
    next[draft.categoryId] = draft.limit;
    await _saveLimits(next);
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
      final next = Map<String, double>.from(_limits)..remove(categoryId);
      await _saveLimits(next);
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
          content: Text(
            'Für alle verfügbaren Kategorien gibt es bereits Budgets.',
          ),
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
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
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
                    if (amount == null || amount <= 0 || !amount.isFinite) {
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
                  _BudgetDraft(categoryId: selectedCategoryId, limit: limit),
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
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, child) {
        if (widget.controller.isLoading) {
          return const Center(child: CircularProgressIndicator());
        }

        if (widget.controller.loadError != null) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline_rounded, size: 34),
                  const SizedBox(height: 10),
                  const Text(
                    'Deine Budgets konnten nicht geladen werden.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Die gespeicherten Werte bleiben unverändert. '
                    'Prüfe den Gerätespeicher und versuche es erneut.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.tonalIcon(
                    onPressed: widget.controller.load,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Erneut laden'),
                  ),
                ],
              ),
            ),
          );
        }

        return _buildBudgetList(context);
      },
    );
  }

  Widget _buildBudgetList(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
      children: [
        Text(
          'Deine Budgets',
          style: textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.55,
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
              final label = _formatMonth(_months[index]);
              return ChoiceChip(
                label: Text(label),
                selected: _selectedMonth == index,
                showCheckmark: false,
                onSelected: widget.controller.isSaving
                    ? null
                    : (_) => setState(() => _selectedMonth = index),
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
                  borderRadius: BorderRadius.circular(10),
                ),
              );
            }),
            FilledButton.tonalIcon(
              onPressed: widget.controller.isSaving ? null : _addBudget,
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
                  fontWeight: FontWeight.w600,
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
              enabled: !widget.controller.isSaving,
              onEdit: () => _editBudget(category.id),
              onDelete: () => _deleteBudget(category.id),
            );
          }),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(15),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: colors.outlineVariant),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Icons.lightbulb_outline_rounded,
                color: AppTheme.accent,
                size: 20,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _remaining >= 0
                      ? 'Im $_monthLabel sind noch ${formatEuro(_remaining)} deines Budgets übrig.'
                      : 'Dein Budget ist um ${formatEuro(_remaining.abs())} überschritten.',
                  style: TextStyle(
                    color: colors.onSurface,
                    fontSize: 13,
                    height: 1.45,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Center(
          child: Text(
            'Budgetlimits werden auf diesem Gerät gespeichert. Demo-Buchungen bleiben Beispieldaten.',
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
        color: AppTheme.brand,
        borderRadius: BorderRadius.circular(16),
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
              valueColor: const AlwaysStoppedAnimation(Color(0xFFC9D6FB)),
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
                value: budget <= 0
                    ? '0 %'
                    : '${(spent / budget * 100).round()} %',
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
      crossAxisAlignment: alignEnd
          ? CrossAxisAlignment.end
          : CrossAxisAlignment.start,
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
    required this.enabled,
    required this.onEdit,
    required this.onDelete,
  });

  final DemoCategory category;
  final double spent;
  final double limit;
  final bool enabled;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final rawProgress = limit <= 0 ? 0.0 : spent / limit;
    final progress = rawProgress.clamp(0.0, 1.0).toDouble();
    final overBudget = rawProgress > 1;
    final progressColor = overBudget ? colors.error : AppTheme.accent;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: colors.surfaceContainerHigh,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(
                  category.icon,
                  color: colors.onSurfaceVariant,
                  size: 19,
                ),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Text(
                  category.name,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
              ),
              Text(
                formatEuro(spent),
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              IconButton(
                tooltip: 'Budget bearbeiten: ${category.name}',
                onPressed: enabled ? onEdit : null,
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.edit_outlined, size: 17),
              ),
              IconButton(
                tooltip: 'Budget löschen: ${category.name}',
                onPressed: enabled ? onDelete : null,
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
              backgroundColor: colors.surfaceContainerHigh,
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
                style: TextStyle(color: colors.onSurfaceVariant, fontSize: 10),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

String _formatMonth(DateTime date) {
  const names = [
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
  return '${names[date.month - 1]} ${date.year}';
}

class _BudgetDraft {
  const _BudgetDraft({required this.categoryId, required this.limit});

  final String categoryId;
  final double limit;
}
