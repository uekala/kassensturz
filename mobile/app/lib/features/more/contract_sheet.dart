import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// Details of one contract with the actions the server allows.
Future<void> showContractSheet(
  BuildContext context, {
  required MobileConnectionController controller,
  required ServerContract contract,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) =>
      ContractSheet(controller: controller, contract: contract),
);

class ContractSheet extends StatefulWidget {
  const ContractSheet({
    required this.controller,
    required this.contract,
    super.key,
  });

  final MobileConnectionController controller;
  final ServerContract contract;

  @override
  State<ContractSheet> createState() => _ContractSheetState();
}

class _ContractSheetState extends State<ContractSheet> {
  bool _saving = false;
  String? _error;

  ServerContract get _contract => widget.contract;

  Future<void> _change(Map<String, dynamic> changes, String done) async {
    setState(() {
      _saving = true;
      _error = null;
    });
    final error = await widget.controller.updateContract(
      _contract.key,
      changes,
    );
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
    messenger?.showSnackBar(SnackBar(content: Text(done)));
  }

  void _openLetter() {
    final navigator = Navigator.of(context);
    navigator.pop();
    navigator.push(
      MaterialPageRoute<void>(
        builder: (_) => CancellationLetterPage(
          controller: widget.controller,
          contract: _contract,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final contract = _contract;
    final status = contract.status ?? 'detected';
    final change = contract.priceChangeCents;
    final details = <(String, String)>[
      ('Betrag', formatSignedEuro(contract.amountCents / 100)),
      if (contract.interval != null) ('Rhythmus', contract.interval!),
      if (contract.nextDue != null)
        ('Nächste Zahlung', _date(contract.nextDue)),
      if (contract.cancellationDeadline != null)
        ('Kündbar bis', _date(contract.cancellationDeadline)),
      if (contract.accountName != null) ('Konto', contract.accountName!),
      if (contract.categoryName != null) ('Kategorie', contract.categoryName!),
      ('Status', _statusLabels[status] ?? status),
    ];

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(contract.name, style: textTheme.titleLarge),
            const SizedBox(height: 14),
            for (final (label, value) in details)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Expanded(child: Text(label, style: textTheme.bodyMedium)),
                    Text(value, style: textTheme.titleSmall),
                  ],
                ),
              ),
            if (change != null && change != 0) ...[
              const SizedBox(height: 12),
              Text(
                change < 0
                    ? 'Zuletzt ${formatEuro(change.abs() / 100)} teurer als '
                          'sonst.'
                    : 'Zuletzt ${formatEuro(change / 100)} günstiger als '
                          'sonst.',
                style: textTheme.bodyMedium?.copyWith(color: klar.warn),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!,
                style: textTheme.bodySmall?.copyWith(color: klar.warn),
              ),
            ],
            const SizedBox(height: 18),
            if (status == 'detected') ...[
              FilledButton(
                onPressed: _saving
                    ? null
                    : () =>
                          _change({'status': 'confirmed'}, 'Vertrag bestätigt'),
                child: const Text('Als Vertrag bestätigen'),
              ),
              const SizedBox(height: 8),
            ],
            if (contract.kind == 'expense' && status != 'cancelled') ...[
              OutlinedButton(
                onPressed: _saving ? null : _openLetter,
                child: const Text('Kündigungsschreiben'),
              ),
              const SizedBox(height: 8),
            ],
            if (change != null && change != 0) ...[
              OutlinedButton(
                onPressed: _saving
                    ? null
                    : () => _change({
                        'price_change_ack': true,
                      }, 'Preisänderung übernommen'),
                child: const Text('Neuen Preis übernehmen'),
              ),
              const SizedBox(height: 8),
            ],
            if (status != 'cancelled')
              TextButton(
                onPressed: _saving
                    ? null
                    : () => _change({
                        'status': 'cancelled',
                      }, 'Als gekündigt markiert'),
                child: const Text('Als gekündigt markieren'),
              ),
            if (!contract.manual)
              TextButton(
                onPressed: _saving
                    ? null
                    : () => _change({
                        'status': 'ignored',
                      }, 'Vertrag ausgeblendet'),
                style: TextButton.styleFrom(foregroundColor: klar.warn),
                child: const Text('Ist kein Vertrag – ausblenden'),
              ),
          ],
        ),
      ),
    );
  }
}

/// Builds the cancellation letter on the server and offers it for copying.
class CancellationLetterPage extends StatefulWidget {
  const CancellationLetterPage({
    required this.controller,
    required this.contract,
    super.key,
  });

  final MobileConnectionController controller;
  final ServerContract contract;

  @override
  State<CancellationLetterPage> createState() => _CancellationLetterPageState();
}

class _CancellationLetterPageState extends State<CancellationLetterPage> {
  String _mode = 'ordentlich';
  DateTime? _date;
  bool _loading = false;
  String? _error;
  Map<String, dynamic>? _letter;

  bool get _priceRaised => (widget.contract.priceChangeCents ?? 0) < 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    if (_mode == 'termin' && _date == null) {
      setState(() {
        _letter = null;
        _error = 'Bitte ein Datum wählen.';
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    final result = await widget.controller.contractLetter(
      widget.contract.key,
      mode: _mode,
      date: _mode == 'termin' ? formatIsoDate(_date!) : null,
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      _letter = result.letter;
      _error = result.error;
    });
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? now.add(const Duration(days: 30)),
      firstDate: now,
      lastDate: now.add(const Duration(days: 3 * 365)),
    );
    if (picked == null || !mounted) return;
    setState(() => _date = picked);
    await _load();
  }

  Future<void> _copy(String text, String done) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(done)));
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final letter = _letter;
    final email = letter?['email'];
    final text = letter?['letter'];
    final subject = letter?['subject'];

    return Scaffold(
      appBar: AppBar(title: const Text('Kündigungsschreiben')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          Text(widget.contract.name, style: textTheme.titleLarge),
          const SizedBox(height: 14),
          SegmentedButton<String>(
            segments: [
              const ButtonSegment(
                value: 'ordentlich',
                label: Text('Fristgerecht'),
              ),
              const ButtonSegment(value: 'termin', label: Text('Zum Termin')),
              if (_priceRaised)
                const ButtonSegment(value: 'sonder', label: Text('Sonder')),
            ],
            selected: {_mode},
            onSelectionChanged: _loading
                ? null
                : (value) {
                    setState(() => _mode = value.first);
                    if (_mode == 'termin' && _date == null) {
                      _pickDate();
                    } else {
                      _load();
                    }
                  },
          ),
          if (_mode == 'termin') ...[
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _loading ? null : _pickDate,
              icon: const Icon(Icons.event),
              label: Text(
                _date == null ? 'Datum wählen' : 'Zum ${formatDate(_date!)}',
              ),
            ),
          ],
          const SizedBox(height: 18),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            ),
          if (_error != null)
            Text(
              _error!,
              style: textTheme.bodyMedium?.copyWith(color: klar.warn),
            ),
          if (letter != null && !_loading) ...[
            if (letter['profile_complete'] != true) ...[
              Text(
                'Name und Anschrift fehlen noch. Trag sie in Kassensturz in '
                'Home Assistant unter Einstellungen ein, dann stehen sie im '
                'Schreiben.',
                style: textTheme.bodySmall?.copyWith(color: klar.warn),
              ),
              const SizedBox(height: 12),
            ],
            DecoratedBox(
              decoration: BoxDecoration(
                border: Border.all(color: klar.border),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: SelectableText(
                  text is String ? text : '',
                  style: textTheme.bodyMedium,
                ),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: text is String
                  ? () => _copy(text, 'Schreiben kopiert')
                  : null,
              icon: const Icon(Icons.copy),
              label: const Text('Schreiben kopieren'),
            ),
            if (subject is String) ...[
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => _copy(subject, 'Betreff kopiert'),
                child: const Text('Betreff kopieren'),
              ),
            ],
            if (email is String && email.isNotEmpty) ...[
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => _copy(email, 'E-Mail-Adresse kopiert'),
                child: Text('E-Mail-Adresse kopieren ($email)'),
              ),
            ],
            const SizedBox(height: 10),
            Text(
              'Nach dem Absenden den Vertrag als gekündigt markieren, damit '
              'Prognose und Fixkosten stimmen.',
              style: textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }
}

const _statusLabels = {
  'detected': 'erkannt',
  'confirmed': 'bestätigt',
  'cancelled': 'gekündigt',
  'ignored': 'ausgeblendet',
};

String _date(String? value) {
  final date = value == null ? null : DateTime.tryParse(value);
  return date == null ? (value ?? '') : formatDate(date);
}
