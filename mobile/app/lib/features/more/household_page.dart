import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';

typedef HouseholdPerson = ({int id, String name});

/// Die anderen Personen des Haushalts, ohne die, die dieses Handy nutzt.
List<HouseholdPerson> householdOthers(Map<String, dynamic> data, int? me) {
  final persons = data['persons'];
  final others = <HouseholdPerson>[];
  if (persons is! List) return others;
  for (final person in persons.whereType<Map<dynamic, dynamic>>()) {
    final id = person['id'];
    if (id is int && id != me) {
      others.add((id: id, name: person['name'].toString()));
    }
  }
  return others;
}

/// Die Person, der dieses Handy gehört, wie die Übersicht sie meldet.
int? householdPersonId(Map<String, dynamic>? overview) {
  final household = overview?['household'];
  final person = household is Map ? household['person'] : null;
  final id = person is Map ? person['id'] : null;
  return id is int ? id : null;
}

/// Wer wem etwas schuldet: positive Cent heißen, die andere Person schuldet dieser etwas.
String openTitle(Map<String, dynamic> entry) {
  final name = _string(entry['person'], 'Jemand');
  return _integer(entry['cents']) > 0
      ? '$name schuldet dir'
      : 'Du schuldest $name';
}

String sharedDetail(Map<String, dynamic> item) {
  final payer = _string(item['payer'], 'Jemand');
  final day = formatShortDate(_string(item['booking_date'], ''));
  return '$payer hat bezahlt, $day';
}

String paymentTitle(Map<String, dynamic> payment) {
  final sender = _string(payment['from'], 'Jemand');
  final receiver = _string(payment['to'], 'jemanden');
  return '$sender an $receiver';
}

String paymentDetail(Map<String, dynamic> payment) {
  final day = formatShortDate(_string(payment['on_date'], ''));
  final note = _string(payment['note'], '');
  return note.isEmpty ? day : '$day, $note';
}

String _euro(dynamic cents) => formatEuro(_integer(cents).abs() / 100);

/// Geteilte Ausgaben des Haushalts: was zwischen dieser Person und den anderen offen ist,
/// die jüngsten geteilten Ausgaben und die von Hand eingetragenen Zahlungen.
class HouseholdPage extends StatefulWidget {
  const HouseholdPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<HouseholdPage> createState() => _HouseholdPageState();
}

class _HouseholdPageState extends State<HouseholdPage> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final result = await widget.controller.loadSharing();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = result.error;
      _data = result.data ?? _data;
    });
  }

  Future<void> _pay() async {
    final data = _data;
    if (data == null) return;
    final me = householdPersonId(widget.controller.overviewData);
    final others = householdOthers(data, me);
    if (others.isEmpty) return;
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) =>
          _SettlementDialog(controller: widget.controller, persons: others),
    );
    if (saved == true && mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final data = _data;
    final open = _maps(data?['open']);
    final items = _maps(data?['items']);
    final payments = _maps(data?['settlements']);

    Widget row(String title, String detail, String value) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(detail, style: textTheme.bodySmall),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Text(value, style: textTheme.titleMedium),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Haushalt')),
      body: SafeArea(
        child: _loading && data == null
            ? const Center(child: CircularProgressIndicator())
            : data == null
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _error ?? 'Der Haushalt ließ sich nicht laden.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
                  children: [
                    Text('Ausgleich', style: textTheme.headlineSmall),
                    const SizedBox(height: 8),
                    if (open.isEmpty)
                      const QuietMessage('Zwischen euch ist nichts offen.'),
                    for (final entry in open)
                      row(
                        openTitle(entry),
                        'aus geteilten Ausgaben, abzüglich Zahlungen',
                        _euro(entry['cents']),
                      ),
                    const SizedBox(height: 8),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton(
                        onPressed: _pay,
                        child: const Text('Zahlung eintragen'),
                      ),
                    ),
                    const SizedBox(height: 26),
                    Text('Geteilte Ausgaben', style: textTheme.headlineSmall),
                    const SizedBox(height: 8),
                    if (items.isEmpty)
                      const QuietMessage(
                        'Noch nichts geteilt. Öffne eine Ausgabe von deinem '
                        'eigenen Konto und wähle „Mit dem Haushalt teilen“.',
                      ),
                    for (final item in items)
                      row(
                        _string(item['label'], 'Buchung'),
                        sharedDetail(item),
                        _euro(item['total_cents']),
                      ),
                    if (payments.isNotEmpty) ...[
                      const SizedBox(height: 26),
                      Text('Zahlungen', style: textTheme.headlineSmall),
                      const SizedBox(height: 8),
                      for (final payment in payments)
                        row(
                          paymentTitle(payment),
                          paymentDetail(payment),
                          _euro(payment['cents']),
                        ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: 10),
                      Text(
                        _error!,
                        style: TextStyle(color: klar.warn, fontSize: 13),
                      ),
                    ],
                  ],
                ),
              ),
      ),
    );
  }
}

class _SettlementDialog extends StatefulWidget {
  const _SettlementDialog({required this.controller, required this.persons});

  final MobileConnectionController controller;
  final List<HouseholdPerson> persons;

  @override
  State<_SettlementDialog> createState() => _SettlementDialogState();
}

class _SettlementDialogState extends State<_SettlementDialog> {
  final _amount = TextEditingController();
  final _note = TextEditingController();
  late int _to = widget.persons.first.id;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _amount.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final cents = parseAmountToCents(_amount.text.trim());
    if (cents == null || cents <= 0) {
      setState(() => _error = 'Bitte gib einen Betrag ein.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final failure = await widget.controller.addSettlement(
      _to,
      cents,
      _note.text.trim(),
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
      title: const Text('Zahlung eintragen'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Hast du jemandem deinen Anteil überwiesen oder bar gegeben, '
              'trägst du das hier ein. Kassensturz bucht dabei nichts um.',
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              children: [
                for (final person in widget.persons)
                  ChoiceChip(
                    label: Text(person.name),
                    selected: person.id == _to,
                    onSelected: (_) => setState(() => _to = person.id),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _amount,
              enabled: !_saving,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Betrag in Euro',
                hintText: '0,00',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _note,
              enabled: !_saving,
              maxLength: 120,
              decoration: const InputDecoration(
                labelText: 'Notiz (freiwillig)',
                counterText: '',
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
          onPressed: _saving ? null : _save,
          child: Text(_saving ? 'Wird eingetragen …' : 'Eintragen'),
        ),
      ],
    );
  }
}

List<Map<String, dynamic>> _maps(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
}

int _integer(dynamic value) => value is int ? value : 0;

String _string(dynamic value, String fallback) =>
    value is String && value.isNotEmpty ? value : fallback;
