import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// Opens the form for today's value of a deposit or the remaining debt of a
/// loan.
Future<void> showAccountValueSheet(
  BuildContext context, {
  required MobileConnectionController controller,
  required int accountId,
  required String name,
  required bool loan,
  int? currentCents,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: AccountValueSheet(
      controller: controller,
      accountId: accountId,
      name: name,
      loan: loan,
      currentCents: currentCents,
    ),
  ),
);

class AccountValueSheet extends StatefulWidget {
  const AccountValueSheet({
    required this.controller,
    required this.accountId,
    required this.name,
    required this.loan,
    this.currentCents,
    super.key,
  });

  final MobileConnectionController controller;
  final int accountId;
  final String name;

  /// A loan asks for the remaining debt, everything else for its value.
  final bool loan;
  final int? currentCents;

  @override
  State<AccountValueSheet> createState() => _AccountValueSheetState();
}

class _AccountValueSheetState extends State<AccountValueSheet> {
  late final TextEditingController _amount;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final cents = widget.currentCents?.abs();
    _amount = TextEditingController(
      text: cents == null || cents == 0
          ? ''
          : (cents / 100).toStringAsFixed(2).replaceAll('.', ','),
    );
  }

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final text = _amount.text.trim();
    final zero = RegExp(r'^0+([.,]0{1,2})?$').hasMatch(text);
    final cents = zero ? 0 : parseAmountToCents(text);
    if (cents == null) {
      setState(() => _error = 'Bitte gib einen Betrag ein, etwa 12.500,00.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.maybeOf(context);
    final error = await widget.controller.setAccountValue(
      widget.accountId,
      cents,
    );
    if (!mounted) return;
    if (error != null) {
      setState(() {
        _saving = false;
        _error = error;
      });
      return;
    }
    navigator.pop();
    messenger
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            widget.loan ? 'Restschuld eingetragen.' : 'Wert eingetragen.',
          ),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final klar = KlarColors.of(context);
    final what = widget.loan ? 'Restschuld' : 'Wert';
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('$what eintragen', style: textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(widget.name, style: textTheme.bodyMedium),
            const SizedBox(height: 14),
            TextField(
              controller: _amount,
              enabled: !_saving,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: InputDecoration(
                labelText: '$what heute',
                suffixText: '€',
              ),
              onSubmitted: (_) => _save(),
            ),
            const SizedBox(height: 8),
            Text(
              widget.loan
                  ? 'Der Betrag gilt ab heute als offene Schuld.'
                  : 'Der Betrag gilt ab heute; frühere Werte bleiben für den '
                        'Verlauf erhalten.',
              style: textTheme.bodySmall,
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _saving ? null : _save,
                child: Text(_saving ? 'Einen Moment …' : 'Speichern'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
