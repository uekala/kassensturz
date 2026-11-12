import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// Opens the sheet to set, change or remove a monthly budget.
///
/// Without [categoryId] the user first picks an expense category that has no
/// budget yet.
Future<void> showBudgetEditor(
  BuildContext context, {
  required MobileConnectionController controller,
  int? categoryId,
  String? categoryName,
  int? limitCents,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: BudgetEditorSheet(
      controller: controller,
      categoryId: categoryId,
      categoryName: categoryName,
      limitCents: limitCents,
    ),
  ),
);

class BudgetEditorSheet extends StatefulWidget {
  const BudgetEditorSheet({
    required this.controller,
    this.categoryId,
    this.categoryName,
    this.limitCents,
    super.key,
  });

  final MobileConnectionController controller;
  final int? categoryId;
  final String? categoryName;
  final int? limitCents;

  @override
  State<BudgetEditorSheet> createState() => _BudgetEditorSheetState();
}

class _BudgetEditorSheetState extends State<BudgetEditorSheet> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _amount;
  int? _categoryId;
  bool _saving = false;
  String? _error;

  bool get _isNew => widget.categoryId == null;

  @override
  void initState() {
    super.initState();
    _categoryId = widget.categoryId;
    final cents = widget.limitCents;
    _amount = TextEditingController(
      text: cents == null ? '' : _plainAmount(cents),
    );
  }

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  List<ServerCategory> get _choices =>
      widget.controller.categories
          .where((c) => c.kind == 'expense' && c.budgetCents == null)
          .toList()
        ..sort((a, b) => a.name.compareTo(b.name));

  Future<void> _save(int? cents) async {
    final categoryId = _categoryId;
    if (categoryId == null) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final error = await widget.controller.setBudget(categoryId, cents);
    if (!mounted) return;
    if (error != null) {
      setState(() {
        _saving = false;
        _error = error;
      });
      return;
    }
    final messenger = ScaffoldMessenger.maybeOf(context);
    Navigator.of(context).pop();
    messenger?.showSnackBar(
      SnackBar(
        content: Text(cents == null ? 'Budget entfernt' : 'Budget gespeichert'),
      ),
    );
  }

  void _submit() {
    if (!(_form.currentState?.validate() ?? false)) return;
    _save(parseAmountToCents(_amount.text));
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final choices = _choices;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Form(
          key: _form,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                _isNew
                    ? 'Budget anlegen'
                    : 'Budget ${widget.categoryName ?? ''}',
                style: textTheme.titleLarge,
              ),
              const SizedBox(height: 6),
              Text(
                'Gilt für jeden Monat. Ausgaben in Unterkategorien zählen mit.',
                style: textTheme.bodySmall,
              ),
              const SizedBox(height: 18),
              if (_isNew) ...[
                if (choices.isEmpty)
                  Text(
                    'Alle Ausgabenkategorien haben schon ein Budget.',
                    style: textTheme.bodyMedium,
                  )
                else
                  DropdownButtonFormField<int>(
                    initialValue: _categoryId,
                    decoration: const InputDecoration(labelText: 'Kategorie'),
                    items: [
                      for (final category in choices)
                        DropdownMenuItem(
                          value: category.id,
                          child: Text(category.name),
                        ),
                    ],
                    onChanged: _saving
                        ? null
                        : (value) => setState(() => _categoryId = value),
                    validator: (value) =>
                        value == null ? 'Bitte eine Kategorie wählen.' : null,
                  ),
                const SizedBox(height: 14),
              ],
              TextFormField(
                controller: _amount,
                enabled: !_saving,
                autofocus: !_isNew,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Betrag pro Monat in Euro',
                  hintText: '0,00',
                ),
                validator: (value) => parseAmountToCents(value ?? '') == null
                    ? 'Bitte einen Betrag größer als 0 eingeben.'
                    : null,
                onFieldSubmitted: (_) => _submit(),
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(
                  _error!,
                  style: textTheme.bodySmall?.copyWith(color: klar.warn),
                ),
              ],
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _saving || (_isNew && choices.isEmpty)
                    ? null
                    : _submit,
                child: Text(_saving ? 'Speichert …' : 'Speichern'),
              ),
              if (!_isNew) ...[
                const SizedBox(height: 8),
                TextButton(
                  onPressed: _saving ? null : () => _save(null),
                  style: TextButton.styleFrom(foregroundColor: klar.warn),
                  child: const Text('Budget entfernen'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

String _plainAmount(int cents) {
  final euros = cents ~/ 100;
  final rest = cents % 100;
  return rest == 0 ? '$euros' : '$euros,${rest.toString().padLeft(2, '0')}';
}
