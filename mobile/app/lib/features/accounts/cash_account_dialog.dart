import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// Asks for a name and an optional balance and creates a cash account on the
/// server. Completes with true once the account exists.
Future<bool> showCashAccountDialog(
  BuildContext context,
  MobileConnectionController controller,
) async {
  final created = await showDialog<bool>(
    context: context,
    builder: (_) => _CashAccountDialog(controller: controller),
  );
  return created == true;
}

class _CashAccountDialog extends StatefulWidget {
  const _CashAccountDialog({required this.controller});

  final MobileConnectionController controller;

  @override
  State<_CashAccountDialog> createState() => _CashAccountDialogState();
}

class _CashAccountDialogState extends State<_CashAccountDialog> {
  final _name = TextEditingController(text: 'Bargeld');
  final _balance = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _balance.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Bitte gib dem Konto einen Namen.');
      return;
    }
    final typed = _balance.text.trim();
    final zero = RegExp(r'^0+([.,]0*)?$').hasMatch(typed);
    final cents = typed.isEmpty || zero ? null : parseAmountToCents(typed);
    if (typed.isNotEmpty && !zero && cents == null) {
      setState(() => _error = 'Der Bestand ist kein gültiger Betrag.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final failure = await widget.controller.createCashAccount(
      name,
      balanceCents: zero ? 0 : cents,
    );
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
    return AlertDialog(
      title: const Text('Konto für Bargeld anlegen'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Umsätze von Hand gehen nur auf ein Konto ohne Bankabruf. Die '
              'Konten deiner Bank füllt der Abruf selbst.',
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _name,
              enabled: !_saving,
              maxLength: 60,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Name',
                counterText: '',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _balance,
              enabled: !_saving,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Aktueller Bestand in Euro (freiwillig)',
                hintText: '0,00',
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Abbrechen'),
        ),
        FilledButton(
          onPressed: _saving ? null : _create,
          child: Text(_saving ? 'Wird angelegt …' : 'Anlegen'),
        ),
      ],
    );
  }
}
