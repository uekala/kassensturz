import 'package:flutter/material.dart';

import '../../core/data/demo_finance_data.dart';
import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';
import 'transaction_editor_page.dart';

enum _TransactionFilter { all, expenses, income }

class TransactionsPage extends StatefulWidget {
  const TransactionsPage({super.key, this.controller});

  final MobileConnectionController? controller;

  @override
  State<TransactionsPage> createState() => _TransactionsPageState();
}

class _TransactionsPageState extends State<TransactionsPage> {
  _TransactionFilter _filter = _TransactionFilter.all;

  List<DemoTransaction> get _visibleTransactions {
    final result = DemoFinanceData.transactions.where((transaction) {
      switch (_filter) {
        case _TransactionFilter.all:
          return true;
        case _TransactionFilter.expenses:
          return transaction.isExpense;
        case _TransactionFilter.income:
          return !transaction.isExpense;
      }
    }).toList()..sort((a, b) => b.date.compareTo(a.date));
    return result;
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    if (controller == null) return _buildDemo(context);
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => controller.isConnected
          ? _buildLive(context, controller)
          : _buildDemo(context),
    );
  }

  Widget _buildDemo(BuildContext context) {
    final visible = _visibleTransactions;

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
      children: [
        const _PageHeading(
          eyebrow: 'FINANZAKTIVITÄTEN',
          title: 'Buchungen',
          subtitle: 'Alle Einnahmen und Ausgaben an einem Ort.',
        ),
        const SizedBox(height: 19),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _FilterChip(
              label: 'Alle',
              selected: _filter == _TransactionFilter.all,
              onSelected: () =>
                  setState(() => _filter = _TransactionFilter.all),
            ),
            _FilterChip(
              label: 'Ausgaben',
              selected: _filter == _TransactionFilter.expenses,
              onSelected: () =>
                  setState(() => _filter = _TransactionFilter.expenses),
            ),
            _FilterChip(
              label: 'Einnahmen',
              selected: _filter == _TransactionFilter.income,
              onSelected: () =>
                  setState(() => _filter = _TransactionFilter.income),
            ),
          ],
        ),
        const SizedBox(height: 20),
        _ListHeading(
          count: visible.length,
          noun: visible.length == 1 ? 'Buchung' : 'Buchungen',
          isDemo: true,
        ),
        const SizedBox(height: 9),
        if (visible.isEmpty)
          const _EmptyState('Keine Buchungen in diesem Filter.')
        else
          _TransactionGroup(
            children: [
              for (var index = 0; index < visible.length; index++) ...[
                if (index > 0) const Divider(height: 1, indent: 58),
                _DemoTransactionTile(transaction: visible[index]),
              ],
            ],
          ),
      ],
    );
  }

  Future<void> _openEditor(
    MobileConnectionController controller, {
    Map<String, dynamic>? item,
  }) async {
    ServerTransaction? existing;
    if (item != null) {
      try {
        existing = ServerTransaction.fromJson(item);
      } on FormatException {
        // An older server does not send the fields needed for editing.
        _showMessage(
          'Bitte aktualisiere Kassensturz in Home Assistant, um Umsätze '
          'zu bearbeiten.',
        );
        return;
      }
    }
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            TransactionEditorPage(controller: controller, existing: existing),
      ),
    );
    if (saved == true) _showMessage('Auf dem Server gespeichert.');
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _chooseAccountFilter(
    MobileConnectionController controller,
  ) async {
    final picked = await _pickFilter(
      title: 'Konto',
      options: {
        for (final account in controller.accounts) account.id: account.name,
      },
    );
    if (picked == null) return;
    await controller.setTransactionFilter(
      accountId: picked == 0 ? null : picked,
      categoryId: controller.filterCategoryId,
    );
  }

  Future<void> _chooseCategoryFilter(
    MobileConnectionController controller,
  ) async {
    final picked = await _pickFilter(
      title: 'Kategorie',
      options: {
        for (final category in controller.categories)
          category.id: category.name,
      },
    );
    if (picked == null) return;
    await controller.setTransactionFilter(
      accountId: controller.filterAccountId,
      categoryId: picked == 0 ? null : picked,
    );
  }

  /// Returns the chosen id, 0 for "all" or null when the dialog was closed.
  Future<int?> _pickFilter({
    required String title,
    required Map<int, String> options,
  }) {
    return showDialog<int>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: Text(title),
        children: [
          SimpleDialogOption(
            onPressed: () => Navigator.of(dialogContext).pop(0),
            child: const Text('Alle'),
          ),
          for (final entry in options.entries)
            SimpleDialogOption(
              onPressed: () => Navigator.of(dialogContext).pop(entry.key),
              child: Text(entry.value),
            ),
        ],
      ),
    );
  }

  static String _nameOf(Map<int, String> names, int? id, String fallback) {
    if (id == null) return fallback;
    return names[id] ?? fallback;
  }

  static bool _startsDay(List<Map<String, dynamic>> items, int index) {
    if (index == 0) return true;
    return items[index]['booking_date'] != items[index - 1]['booking_date'];
  }

  static String _dayLabel(dynamic value) {
    final date = value is String ? DateTime.tryParse(value) : null;
    if (date == null) return 'Ohne Datum';
    final now = DateTime.now();
    final today = DateTime.utc(now.year, now.month, now.day);
    final day = DateTime.utc(date.year, date.month, date.day);
    final distance = today.difference(day).inDays;
    if (distance == 0) return 'Heute';
    if (distance == 1) return 'Gestern';
    return formatDemoDate(date);
  }

  Widget _buildLive(
    BuildContext context,
    MobileConnectionController controller,
  ) {
    final items = controller.transactionItems;
    final total = controller.transactionTotal;
    final textTheme = Theme.of(context).textTheme;
    final canWrite = controller.canWriteTransactions;
    final accountNames = {
      for (final account in controller.accounts) account.id: account.name,
    };
    final categoryNames = {
      for (final category in controller.categories) category.id: category.name,
    };

    return RefreshIndicator(
      onRefresh: controller.refreshTransactions,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          Text(
            '$total ${total == 1 ? 'Buchung' : 'Buchungen'}',
            style: textTheme.bodyMedium,
          ),
          if (canWrite) ...[
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _FilterButton(
                    label: _nameOf(
                      accountNames,
                      controller.filterAccountId,
                      'Alle Konten',
                    ),
                    active: controller.filterAccountId != null,
                    onPressed: () => _chooseAccountFilter(controller),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _FilterButton(
                    label: _nameOf(
                      categoryNames,
                      controller.filterCategoryId,
                      'Alle Kategorien',
                    ),
                    active: controller.filterCategoryId != null,
                    onPressed: () => _chooseCategoryFilter(controller),
                  ),
                ),
              ],
            ),
          ],
          if (controller.financeError != null) ...[
            const SizedBox(height: 10),
            Text(
              controller.financeError!,
              style: textTheme.bodySmall?.copyWith(color: AppTheme.warn),
            ),
          ],
          const SizedBox(height: 6),
          if (items.isEmpty && controller.financeLoading)
            const Padding(
              padding: EdgeInsets.all(28),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (items.isEmpty)
            const _EmptyState('Noch keine Buchungen vorhanden.')
          else
            for (var index = 0; index < items.length; index++) ...[
              if (_startsDay(items, index))
                _DayHeading(_dayLabel(items[index]['booking_date']))
              else
                const Divider(height: 1),
              _LiveTransactionTile(
                item: items[index],
                onTap: canWrite
                    ? () => _openEditor(controller, item: items[index])
                    : null,
              ),
            ],
          if (items.length < total) ...[
            const SizedBox(height: 14),
            OutlinedButton(
              onPressed: controller.financeLoading
                  ? null
                  : controller.loadMoreTransactions,
              child: controller.financeLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Weitere Buchungen laden'),
            ),
          ],
        ],
      ),
    );
  }
}

class _FilterButton extends StatelessWidget {
  const _FilterButton({
    required this.label,
    required this.active,
    required this.onPressed,
  });

  final String label;
  final bool active;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        backgroundColor: active ? AppTheme.softBrand : AppTheme.surface,
        foregroundColor: AppTheme.ink,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        side: BorderSide(
          color: active ? AppTheme.brand : AppTheme.fieldBorder,
          width: 1.5,
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
          const Icon(Icons.expand_more_rounded, size: 18),
        ],
      ),
    );
  }
}

class _DayHeading extends StatelessWidget {
  const _DayHeading(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 16, bottom: 2),
      child: Text(label, style: Theme.of(context).textTheme.labelMedium),
    );
  }
}

class _PageHeading extends StatelessWidget {
  const _PageHeading({
    required this.eyebrow,
    required this.title,
    required this.subtitle,
  });

  final String eyebrow;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          eyebrow,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.1,
          ),
        ),
        const SizedBox(height: 5),
        Text(title, style: theme.textTheme.headlineSmall),
        const SizedBox(height: 3),
        Text(subtitle, style: theme.textTheme.bodyMedium),
      ],
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onSelected,
  });

  final String label;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onSelected(),
      showCheckmark: false,
      labelStyle: TextStyle(
        color: selected ? colors.primary : colors.onSurfaceVariant,
        fontSize: 12,
        fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
      ),
      selectedColor: AppTheme.softBrand,
      backgroundColor: colors.surface,
      side: BorderSide(
        color: selected ? AppTheme.softBrand : colors.outlineVariant,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 7),
    );
  }
}

class _ListHeading extends StatelessWidget {
  const _ListHeading({
    required this.count,
    required this.noun,
    required this.isDemo,
  });

  final int count;
  final String noun;
  final bool isDemo;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            '$count $noun',
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
        if (isDemo)
          Text(
            'BEISPIELDATEN',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              letterSpacing: 0.7,
              fontWeight: FontWeight.w700,
            ),
          ),
      ],
    );
  }
}

class _TransactionGroup extends StatelessWidget {
  const _TransactionGroup({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Column(children: children),
    );
  }
}

class _DemoTransactionTile extends StatelessWidget {
  const _DemoTransactionTile({required this.transaction});

  final DemoTransaction transaction;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final category = DemoFinanceData.category(transaction.categoryId);

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(vertical: 5),
      minLeadingWidth: 38,
      leading: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: colors.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(10),
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
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
          color: transaction.isExpense ? colors.onSurface : AppTheme.accent,
        ),
      ),
    );
  }
}

class _LiveTransactionTile extends StatelessWidget {
  const _LiveTransactionTile({required this.item, required this.onTap});

  final Map<String, dynamic> item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final amountValue = item['amount_cents'];
    final cents = amountValue is int ? amountValue : 0;
    final category = item['category'];
    final categoryName = category is Map ? category['name']?.toString() : null;
    final counterparty = item['counterparty']?.toString() ?? '';
    final purpose = item['purpose']?.toString() ?? '';
    final title = counterparty.isNotEmpty
        ? counterparty
        : purpose.isNotEmpty
        ? purpose
        : 'Buchung';
    final detail = <String>[
      if (categoryName != null && categoryName.isNotEmpty) categoryName,
      if (item['account_name'] is String) item['account_name'] as String,
    ].join(' · ');

    return EntryRow(
      title: title,
      detail: detail.isEmpty ? 'Buchung' : detail,
      amount: formatSignedEuro(cents / 100),
      positive: cents > 0,
      badge: item['manual'] == true ? 'von Hand' : null,
      onTap: onTap,
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Center(
        child: Text(
          message,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ),
    );
  }
}
