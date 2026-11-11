import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';
import 'transaction_editor_page.dart';

class TransactionsPage extends StatefulWidget {
  const TransactionsPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<TransactionsPage> createState() => _TransactionsPageState();
}

class _TransactionsPageState extends State<TransactionsPage> {
  final _search = TextEditingController();
  Timer? _searchDelay;

  @override
  void dispose() {
    _searchDelay?.cancel();
    _search.dispose();
    super.dispose();
  }

  /// Waits for a pause in typing so not every letter asks the server.
  void _onSearchChanged(String value) {
    setState(() {});
    _searchDelay?.cancel();
    _searchDelay = Timer(
      const Duration(milliseconds: 400),
      () => widget.controller.setTransactionSearch(value),
    );
  }

  void _applySearch(String value) {
    _searchDelay?.cancel();
    widget.controller.setTransactionSearch(value);
  }

  void _clearSearch() {
    _search.clear();
    setState(() {});
    _applySearch('');
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) => _buildLive(context, widget.controller),
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
    return formatDate(date);
  }

  Widget _buildLive(
    BuildContext context,
    MobileConnectionController controller,
  ) {
    final klar = KlarColors.of(context);
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
          if (controller.canSearchTransactions) ...[
            const SizedBox(height: 14),
            TextField(
              controller: _search,
              textInputAction: TextInputAction.search,
              onChanged: _onSearchChanged,
              onSubmitted: _applySearch,
              decoration: InputDecoration(
                hintText: 'Empfänger, Zweck oder Notiz suchen',
                prefixIcon: const Icon(Icons.search_rounded),
                suffixIcon: _search.text.isEmpty
                    ? null
                    : IconButton(
                        tooltip: 'Suche leeren',
                        onPressed: _clearSearch,
                        icon: const Icon(Icons.close_rounded),
                      ),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: SegmentedButton<String>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: '', label: Text('Alle')),
                  ButtonSegment(value: 'in', label: Text('Einnahmen')),
                  ButtonSegment(value: 'out', label: Text('Ausgaben')),
                ],
                selected: {controller.filterKind ?? ''},
                onSelectionChanged: (selection) =>
                    controller.setTransactionKind(
                      selection.first.isEmpty ? null : selection.first,
                    ),
              ),
            ),
          ],
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
              style: textTheme.bodySmall?.copyWith(color: klar.warn),
            ),
          ],
          const SizedBox(height: 6),
          if (items.isEmpty && controller.financeLoading)
            const Padding(
              padding: EdgeInsets.all(28),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (items.isEmpty)
            _EmptyState(
              controller.hasTransactionFilter
                  ? 'Keine Buchungen für diese Auswahl.'
                  : 'Noch keine Buchungen vorhanden.',
            )
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
    final klar = KlarColors.of(context);
    return OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        backgroundColor: active ? klar.softBrand : klar.surface,
        foregroundColor: klar.ink,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        side: BorderSide(
          color: active ? klar.brand : klar.fieldBorder,
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
