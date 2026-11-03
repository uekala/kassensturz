import 'package:flutter/material.dart';

import '../../core/data/demo_finance_data.dart';

enum _TransactionFilter { all, expenses, income }

class TransactionsPage extends StatefulWidget {
  const TransactionsPage({super.key});

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
    final colors = Theme.of(context).colorScheme;
    final visible = _visibleTransactions;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(
          'Buchungen',
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          'Deine letzten Buchungen im Überblick.',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
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
        const SizedBox(height: 13),
        Text(
          '${visible.length} ${visible.length == 1 ? 'Buchung' : 'Buchungen'} · Beispieldaten',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: colors.onSurfaceVariant,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 5),
        if (visible.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 36),
            child: Center(child: Text('Keine Buchungen in diesem Filter.')),
          )
        else
          ...visible.map((transaction) => _TransactionTile(transaction)),
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
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onSelected(),
      showCheckmark: false,
      labelStyle: TextStyle(
        fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
        color: selected
            ? Theme.of(context).colorScheme.onPrimary
            : Theme.of(context).colorScheme.onSurface,
      ),
      selectedColor: Theme.of(context).colorScheme.primary,
      backgroundColor: Colors.white,
      side: BorderSide(
        color: selected
            ? Theme.of(context).colorScheme.primary
            : Theme.of(context).colorScheme.outlineVariant,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    );
  }
}

class _TransactionTile extends StatelessWidget {
  const _TransactionTile(this.transaction);

  final DemoTransaction transaction;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final category = DemoFinanceData.category(transaction.categoryId);

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 2),
      leading: CircleAvatar(
        backgroundColor: colors.secondaryContainer,
        foregroundColor: colors.onSecondaryContainer,
        child: Icon(transaction.icon, size: 20),
      ),
      title: Text(
        transaction.title,
        style: const TextStyle(fontWeight: FontWeight.w700),
      ),
      subtitle: Text('${category.name} · ${formatDemoDate(transaction.date)}'),
      trailing: Text(
        formatSignedEuro(transaction.amount),
        style: TextStyle(
          fontWeight: FontWeight.w700,
          color: transaction.isExpense ? colors.onSurface : colors.primary,
        ),
      ),
    );
  }
}
