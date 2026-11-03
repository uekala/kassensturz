import 'package:flutter/material.dart';

import '../../core/data/demo_finance_data.dart';
import '../../core/networking/mobile_connection_controller.dart';

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

  Widget _buildLive(
    BuildContext context,
    MobileConnectionController controller,
  ) {
    final colors = Theme.of(context).colorScheme;
    final items = controller.transactionItems;
    final total = controller.transactionTotal;
    return RefreshIndicator(
      onRefresh: controller.refreshTransactions,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
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
            'Live-Daten von deinem Kassensturz-Server.',
            style: TextStyle(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 13),
          Text(
            total.toString() + (total == 1 ? ' Buchung auf dem Server' : ' Buchungen auf dem Server'),
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: colors.onSurfaceVariant,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (controller.financeError != null) ...[
            const SizedBox(height: 8),
            Text(
              controller.financeError!,
              style: TextStyle(color: colors.error, fontSize: 12),
            ),
          ],
          if (items.isEmpty && controller.financeLoading)
            const Padding(
              padding: EdgeInsets.all(28),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (items.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 36),
              child: Center(child: Text('Noch keine Buchungen vorhanden.')),
            )
          else
            ...items.map((item) {
              final amountValue = item['amount_cents'];
              final cents = amountValue is int ? amountValue : 0;
              final category = item['category'];
              final categoryName = category is Map
                  ? category['name']?.toString()
                  : null;
              final counterparty = item['counterparty']?.toString() ?? '';
              final purpose = item['purpose']?.toString() ?? '';
              final title = counterparty.isNotEmpty
                  ? counterparty
                  : purpose.isNotEmpty
                  ? purpose
                  : 'Buchung';
              final subtitle = <String>[
                if (categoryName != null && categoryName.isNotEmpty) categoryName,
                if (item['account_name'] is String) item['account_name'] as String,
                if (item['booking_date'] is String) _formatDate(item['booking_date'] as String),
              ].join(' · ');
              return ListTile(
                contentPadding: const EdgeInsets.symmetric(horizontal: 2),
                leading: CircleAvatar(
                  backgroundColor: colors.secondaryContainer,
                  foregroundColor: colors.onSecondaryContainer,
                  child: Icon(
                    cents < 0 ? Icons.north_east_rounded : Icons.south_west_rounded,
                    size: 19,
                  ),
                ),
                title: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(
                  subtitle.isEmpty ? 'Buchung' : subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: Text(
                  formatSignedEuro(cents / 100),
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: cents < 0 ? colors.onSurface : colors.primary,
                  ),
                ),
              );
            }),
          if (items.length < total) ...[
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: controller.financeLoading ? null : controller.loadMoreTransactions,
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

  static String _formatDate(String value) {
    final date = DateTime.tryParse(value);
    if (date == null) return value;
    return date.day.toString().padLeft(2, '0') +
        '.' +
        date.month.toString().padLeft(2, '0') +
        '.' +
        date.year.toString();
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
