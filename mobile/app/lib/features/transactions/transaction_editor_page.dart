import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import 'receipts_section.dart';

/// Creates a manual transaction or edits an existing one. Everything is
/// stored on the server; the page keeps no copy on the device.
class TransactionEditorPage extends StatefulWidget {
  const TransactionEditorPage({
    required this.controller,
    this.existing,
    this.receiptPicker = pickReceiptPhoto,
    super.key,
  });

  final MobileConnectionController controller;

  /// Null creates a new manual transaction.
  final ServerTransaction? existing;

  /// Where a new receipt photo comes from; replaced in tests.
  final ReceiptPicker receiptPicker;

  @override
  State<TransactionEditorPage> createState() => _TransactionEditorPageState();
}

class _TransactionEditorPageState extends State<TransactionEditorPage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _amount;
  late final TextEditingController _counterparty;
  late final TextEditingController _purpose;
  late final TextEditingController _note;

  /// Stays the same for every attempt to save this form, so a repeated
  /// request after a lost connection is recognised by the server.
  final String _requestId = newClientRequestId();

  late bool _isExpense;
  late DateTime _date;
  int? _accountId;
  int? _categoryId;
  String? _taxKind;
  bool _saving = false;
  String? _error;

  bool get _isNew => widget.existing == null;
  bool get _fullyEditable => _isNew || widget.existing!.manual;

  @override
  void initState() {
    super.initState();
    final existing = widget.existing;
    final cents = existing?.amountCents ?? 0;
    _isExpense = existing == null || cents < 0;
    _date = DateTime.tryParse(existing?.bookingDate ?? '') ?? DateTime.now();
    _accountId = existing?.accountId;
    _categoryId = existing?.categoryId;
    _taxKind = existing?.taxKind;
    _amount = TextEditingController(
      text: existing == null ? '' : _formatAmount(cents.abs()),
    );
    _counterparty = TextEditingController(text: existing?.counterparty ?? '');
    _purpose = TextEditingController(text: existing?.purpose ?? '');
    _note = TextEditingController(text: existing?.note ?? '');
    final manualAccounts = widget.controller.manualAccounts;
    if (_isNew && manualAccounts.length == 1) {
      _accountId = manualAccounts.first.id;
    }
  }

  @override
  void dispose() {
    _amount.dispose();
    _counterparty.dispose();
    _purpose.dispose();
    _note.dispose();
    super.dispose();
  }

  static String _formatAmount(int cents) {
    final euros = cents ~/ 100;
    final rest = (cents % 100).toString().padLeft(2, '0');
    return '$euros,$rest';
  }

  static String _formatDate(DateTime date) {
    final day = date.day.toString().padLeft(2, '0');
    final month = date.month.toString().padLeft(2, '0');
    return '$day.$month.${date.year}';
  }

  void _selectDirection(Set<bool> selection) {
    setState(() => _isExpense = selection.first);
  }

  Future<void> _pickDate() async {
    final today = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(2000),
      lastDate: today.add(const Duration(days: 366)),
    );
    if (picked != null && mounted) setState(() => _date = picked);
  }

  Future<void> _pickAccount() async {
    final picked = await _pick<int>(
      title: 'Konto wählen',
      options: {
        for (final account in widget.controller.manualAccounts)
          account.id: account.name,
      },
    );
    if (picked != null && mounted) setState(() => _accountId = picked);
  }

  Future<void> _pickCategory() async {
    final picked = await _pick<int>(
      title: 'Kategorie wählen',
      options: {
        for (final category in widget.controller.categories)
          category.id: category.name,
      },
    );
    if (picked != null && mounted) setState(() => _categoryId = picked);
  }

  Future<void> _pickTaxKind() async {
    final picked = await _pick<String>(
      title: 'Für die Steuererklärung',
      options: {'': 'Nicht relevant', ...taxKindLabels},
    );
    if (picked != null && mounted) {
      setState(() => _taxKind = picked.isEmpty ? null : picked);
    }
  }

  Future<T?> _pick<T>({
    required String title,
    required Map<T, String> options,
  }) {
    return showDialog<T>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: Text(title),
        children: [
          for (final entry in options.entries)
            SimpleDialogOption(
              onPressed: () => Navigator.of(dialogContext).pop(entry.key),
              child: Text(entry.value),
            ),
        ],
      ),
    );
  }

  String _accountLabel() {
    for (final account in widget.controller.accounts) {
      if (account.id == _accountId) return account.name;
    }
    return widget.existing?.accountName ?? 'Konto wählen';
  }

  String _categoryLabel() {
    for (final category in widget.controller.categories) {
      if (category.id == _categoryId) return category.name;
    }
    return widget.existing?.categoryName ?? 'Automatisch zuordnen';
  }

  Map<String, dynamic>? _buildCreateFields() {
    final cents = parseAmountToCents(_amount.text);
    final accountId = _accountId;
    if (cents == null || accountId == null) return null;
    final purpose = _purpose.text.trim();
    final note = _note.text.trim();
    return {
      'client_request_id': _requestId,
      'account_id': accountId,
      'booking_date': formatIsoDate(_date),
      'amount_cents': _isExpense ? -cents : cents,
      'counterparty': _counterparty.text.trim(),
      if (purpose.isNotEmpty) 'purpose': purpose,
      if (_categoryId != null) 'category_id': _categoryId,
      if (note.isNotEmpty) 'note': note,
    };
  }

  Map<String, dynamic> _buildChanges(ServerTransaction existing) {
    final changes = <String, dynamic>{};
    final note = _note.text.trim();
    if (note != (existing.note ?? '')) {
      changes['note'] = note.isEmpty ? null : note;
    }
    if (_categoryId != null && _categoryId != existing.categoryId) {
      changes['category_id'] = _categoryId;
    }
    if (_taxKind != existing.taxKind) changes['tax_kind'] = _taxKind;
    if (!existing.manual) return changes;

    final cents = parseAmountToCents(_amount.text);
    if (cents != null) {
      final signed = _isExpense ? -cents : cents;
      if (signed != existing.amountCents) changes['amount_cents'] = signed;
    }
    final date = formatIsoDate(_date);
    if (date != existing.bookingDate) changes['booking_date'] = date;
    final counterparty = _counterparty.text.trim();
    if (counterparty != (existing.counterparty ?? '')) {
      changes['counterparty'] = counterparty;
    }
    final purpose = _purpose.text.trim();
    if (purpose != (existing.purpose ?? '')) {
      changes['purpose'] = purpose.isEmpty ? null : purpose;
    }
    return changes;
  }

  Future<void> _save() async {
    if (_saving) return;
    if (!_formKey.currentState!.validate()) return;
    final existing = widget.existing;
    String? failure;
    if (existing == null) {
      final fields = _buildCreateFields();
      if (fields == null) {
        setState(() => _error = 'Bitte wähle ein Konto.');
        return;
      }
      setState(() {
        _saving = true;
        _error = null;
      });
      failure = await widget.controller.createTransaction(fields);
    } else {
      final changes = _buildChanges(existing);
      if (changes.isEmpty) {
        Navigator.of(context).pop(false);
        return;
      }
      setState(() {
        _saving = true;
        _error = null;
      });
      failure = await widget.controller.updateTransaction(existing.id, changes);
    }
    if (!mounted) return;
    if (failure == null) {
      final also = existing == null ? 0 : widget.controller.lastAlsoChanged;
      if (also > 0) {
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          SnackBar(
            content: Text(
              also == 1
                  ? 'Gemerkt: 1 weitere Buchung genauso zugeordnet.'
                  : 'Gemerkt: $also weitere Buchungen genauso zugeordnet.',
            ),
          ),
        );
      }
      Navigator.of(context).pop(true);
      return;
    }
    setState(() {
      _saving = false;
      _error = failure;
    });
  }

  Future<void> _delete() async {
    final existing = widget.existing;
    if (existing == null || _saving) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Umsatz löschen?'),
        content: const Text(
          'Der Umsatz wird auf dem Server gelöscht. '
          'Das lässt sich nicht rückgängig machen.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Löschen'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final failure = await widget.controller.deleteTransaction(existing.id);
    if (!mounted) return;
    if (failure == null) {
      Navigator.of(context).pop(true);
      return;
    }
    setState(() {
      _saving = false;
      _error = failure;
    });
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final existing = widget.existing;
    final amountStyle = TextStyle(
      fontFamily: AppTheme.displayFamily,
      fontFamilyFallback: AppTheme.displayFallback,
      color: klar.ink,
      fontSize: 44,
      height: 1.15,
      fontWeight: FontWeight.w700,
      letterSpacing: -1.6,
    );
    UnderlineInputBorder amountLine(Color color) {
      return UnderlineInputBorder(
        borderSide: BorderSide(color: color, width: 2),
      );
    }

    final title = _isNew
        ? 'Neuer Umsatz'
        : _fullyEditable
        ? 'Umsatz bearbeiten'
        : 'Bankumsatz';
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          if (existing != null && existing.manual)
            IconButton(
              tooltip: 'Umsatz löschen',
              onPressed: _saving ? null : _delete,
              icon: const Icon(Icons.delete_outline_rounded),
            ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
          children: [
            if (!_fullyEditable) ...[
              const _Hint(
                'Dieser Umsatz stammt von der Bank. Betrag, Datum und Text '
                'bleiben wie geliefert; alles andere kannst du ändern.',
              ),
              const SizedBox(height: 16),
            ],
            if (_fullyEditable) ...[
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: true, label: Text('Ausgabe')),
                  ButtonSegment(value: false, label: Text('Einnahme')),
                ],
                selected: {_isExpense},
                onSelectionChanged: _saving ? null : _selectDirection,
              ),
              const SizedBox(height: 16),
            ],
            const SizedBox(height: 4),
            Center(child: Text('Betrag in Euro', style: textTheme.bodyMedium)),
            TextFormField(
              controller: _amount,
              enabled: _fullyEditable && !_saving,
              textAlign: TextAlign.center,
              style: amountStyle,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: InputDecoration(
                hintText: '0,00',
                hintStyle: amountStyle.copyWith(color: klar.fieldBorder),
                filled: false,
                contentPadding: const EdgeInsets.symmetric(vertical: 6),
                border: amountLine(klar.brand),
                enabledBorder: amountLine(klar.brand),
                focusedBorder: amountLine(klar.brand),
                disabledBorder: amountLine(klar.border),
                errorBorder: amountLine(klar.warn),
                focusedErrorBorder: amountLine(klar.warn),
              ),
              validator: (value) {
                if (!_fullyEditable) return null;
                return parseAmountToCents(value ?? '') == null
                    ? 'Bitte einen Betrag größer als 0 eingeben.'
                    : null;
              },
            ),
            const SizedBox(height: 20),
            TextFormField(
              controller: _counterparty,
              enabled: _fullyEditable && !_saving,
              maxLength: 100,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Empfänger oder Zahler',
                counterText: '',
              ),
              validator: (value) {
                if (!_fullyEditable) return null;
                return (value ?? '').trim().isEmpty
                    ? 'Bitte einen Namen eingeben.'
                    : null;
              },
            ),
            const SizedBox(height: 14),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: _PickerTile(
                    label: 'Konto',
                    value: _accountLabel(),
                    onTap: _isNew && !_saving ? _pickAccount : null,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _PickerTile(
                    label: 'Datum',
                    value: _formatDate(_date),
                    onTap: _fullyEditable && !_saving ? _pickDate : null,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            _PickerTile(
              label: 'Kategorie',
              value: _categoryLabel(),
              onTap: _saving ? null : _pickCategory,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _purpose,
              enabled: _fullyEditable && !_saving,
              maxLength: 140,
              decoration: const InputDecoration(
                labelText: 'Verwendungszweck (optional)',
                counterText: '',
              ),
            ),
            const SizedBox(height: 14),
            TextFormField(
              controller: _note,
              enabled: !_saving,
              maxLength: 300,
              maxLines: 2,
              decoration: const InputDecoration(
                labelText: 'Notiz (optional)',
                counterText: '',
              ),
            ),
            if (existing != null && widget.controller.canTagTax) ...[
              const SizedBox(height: 14),
              _PickerTile(
                label: 'Für die Steuererklärung',
                value: taxKindLabels[_taxKind] ?? 'Nicht relevant',
                onTap: _saving ? null : _pickTaxKind,
              ),
            ],
            if (existing != null && widget.controller.canUseReceipts) ...[
              const SizedBox(height: 16),
              ReceiptsSection(
                controller: widget.controller,
                transactionId: existing.id,
                picker: widget.receiptPicker,
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 14),
              Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
            ],
            const SizedBox(height: 22),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(54),
                textStyle: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              onPressed: _saving ? null : _save,
              icon: _saving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.cloud_upload_outlined),
              label: Text(
                _saving
                    ? 'Wird gespeichert …'
                    : _error == null
                    ? 'Auf dem Server speichern'
                    : 'Erneut versuchen',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PickerTile extends StatelessWidget {
  const _PickerTile({
    required this.label,
    required this.value,
    required this.onTap,
  });

  final String label;
  final String value;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: textTheme.labelMedium),
        const SizedBox(height: 6),
        Material(
          color: klar.surface,
          clipBehavior: Clip.antiAlias,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(
              color: onTap == null ? klar.border : klar.fieldBorder,
              width: 1.5,
            ),
          ),
          child: InkWell(
            onTap: onTap,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 50),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        value,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.bodyLarge?.copyWith(
                          color: onTap == null ? klar.mutedInk : klar.ink,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    if (onTap != null)
                      Icon(
                        Icons.expand_more_rounded,
                        size: 18,
                        color: klar.ink,
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: klar.softBrand,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        text,
        style: TextStyle(color: klar.brand, fontSize: 12, height: 1.4),
      ),
    );
  }
}
