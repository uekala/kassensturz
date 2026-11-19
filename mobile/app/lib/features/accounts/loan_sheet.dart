import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';

/// Opens the repayment plan of a loan.
Future<void> showLoanSheet(
  BuildContext context, {
  required MobileConnectionController controller,
  required int accountId,
  required String name,
  VoidCallback? onEditValue,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: LoanSheet(
      controller: controller,
      accountId: accountId,
      name: name,
      onEditValue: onEditValue,
    ),
  ),
);

String _span(int months) {
  final years = months ~/ 12;
  final rest = months % 12;
  final parts = [
    if (years > 0) '$years ${years == 1 ? 'Jahr' : 'Jahre'}',
    if (rest > 0) '$rest ${rest == 1 ? 'Monat' : 'Monate'}',
  ];
  return parts.isEmpty ? 'sofort' : parts.join(' und ');
}

String _percent(int milli) {
  final text = (milli / 1000)
      .toStringAsFixed(3)
      .replaceFirst(RegExp(r'0+$'), '')
      .replaceFirst(RegExp(r'\.$'), '');
  return text.replaceAll('.', ',');
}

String _monthYear(String value) {
  final date = DateTime.tryParse(value);
  if (date == null) return value;
  return '${date.month.toString().padLeft(2, '0')}/${date.year}';
}

int _whole(dynamic value) => value is int ? value : 0;

/// What the booked rates say about the estimate; null when there is nothing
/// to compare yet. The second value is true when a rate is missing.
(String, bool)? bookedRatesText(Map<String, dynamic> plan) {
  final booked = plan['booked'];
  if (booked is! Map || _whole(booked['expected']) == 0) return null;
  final payment = formatEuro(_whole(plan['payment_cents']) / 100);
  final count = _whole(booked['count']);
  final expected = _whole(booked['expected']);
  final counterparty = booked['counterparty'];
  final to = counterparty is String ? ' an $counterparty' : '';
  if (count == 0) {
    return (
      'Keine Abbuchung über genau $payment gefunden. Die Schätzung nimmt an, '
          'dass jede Rate gezahlt wurde.',
      false,
    );
  }
  final other = booked['other'] is List
      ? (booked['other'] as List).whereType<Map>().toList()
      : const <Map>[];
  final otherParts = [
    for (final item in other)
      '${formatEuro(_whole(item['cents']) / 100)} am '
          '${formatShortDate(item['date']?.toString() ?? '')}',
  ];
  final otherText = otherParts.isEmpty
      ? ''
      : ' Weitere Zahlungen$to: ${otherParts.join(', ')}. War das eine '
            'Sondertilgung, trag die Restschuld neu ein.';
  final missing = booked['missing'] is List
      ? (booked['missing'] as List).whereType<String>().toList()
      : const <String>[];
  if (missing.isEmpty) {
    return (
      '✓ Alle $expected ${expected == 1 ? 'Rate' : 'Raten'} seit dem Eintrag '
          'sind gebucht$to.$otherText',
      false,
    );
  }
  final months = [
    for (final month in missing)
      month.length == 7
          ? '${month.substring(5)}/${month.substring(0, 4)}'
          : month,
  ];
  final rest = formatEuro(_whole(booked['rest_cents']) / 100);
  return (
    'Für ${months.join(', ')} ist keine Abbuchung über $payment$to gebucht. '
        'Nach den gebuchten Raten wären es heute $rest.$otherText',
    true,
  );
}

class LoanSheet extends StatefulWidget {
  const LoanSheet({
    required this.controller,
    required this.accountId,
    required this.name,
    this.onEditValue,
    super.key,
  });

  final MobileConnectionController controller;
  final int accountId;
  final String name;

  /// Opens the form for the remaining debt; the plan closes first.
  final VoidCallback? onEditValue;

  @override
  State<LoanSheet> createState() => _LoanSheetState();
}

class _LoanSheetState extends State<LoanSheet> {
  final _extra = TextEditingController();
  Map<String, dynamic>? _plan;
  Map<String, dynamic>? _extraResult;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _extra.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final result = await widget.controller.readOnce(
      (api) => api.loanPlan(widget.accountId),
    );
    if (!mounted) return;
    setState(() {
      _plan = result.data;
      _error = result.error;
    });
  }

  Future<void> _calculate() async {
    final cents = parseAmountToCents(_extra.text);
    if (cents == null) {
      setState(() => _error = 'Bitte einen Betrag größer als 0 eingeben.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final result = await widget.controller.readOnce(
      (api) => api.loanPlan(widget.accountId, extraCents: cents),
    );
    if (!mounted) return;
    final extra = result.data?['extra'];
    setState(() {
      _busy = false;
      _error = result.error;
      _extraResult = extra is Map ? Map<String, dynamic>.from(extra) : null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final plan = _plan;
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.85,
        ),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          children: [
            Text('Tilgungsplan ${widget.name}', style: textTheme.titleLarge),
            if (widget.onEditValue != null)
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  onPressed: () {
                    Navigator.of(context).pop();
                    widget.onEditValue!();
                  },
                  child: const Text('Restschuld eintragen'),
                ),
              ),
            const SizedBox(height: 12),
            if (plan == null && _error == null)
              const Center(child: CircularProgressIndicator())
            else if (plan == null)
              QuietMessage(_error!)
            else
              ..._content(context, plan),
          ],
        ),
      ),
    );
  }

  int _int(dynamic value) => value is int ? value : 0;

  List<Widget> _content(BuildContext context, Map<String, dynamic> plan) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    if (plan['ready'] != true) {
      const needs = {
        'rate': 'den Sollzins',
        'payment': 'die Monatsrate',
        'balance': 'die Restschuld',
      };
      final missing = plan['missing'] is List
          ? (plan['missing'] as List).map((item) => needs[item] ?? '$item')
          : const <String>[];
      return [
        Text(
          'Für den Tilgungsplan fehlt noch: ${missing.join(', ')}. '
          'Eintragen geht in Kassensturz in Home Assistant am Konto.',
          style: textTheme.bodyMedium,
        ),
      ];
    }
    final today = _int(plan['today_cents']);
    final since = _int(plan['months_since_entry']);
    if (plan['covers_interest'] != true) {
      return [
        AmountHeadline(
          label: 'Restschuld',
          amount: formatEuro(today / 100),
          size: 36,
        ),
        const SizedBox(height: 12),
        Text(
          'Die Rate deckt die Zinsen nicht: Im Monat fallen '
          '${formatEuro(_int(plan['first_interest_cents']) / 100)} Zinsen an, '
          'die Rate beträgt ${formatEuro(_int(plan['payment_cents']) / 100)}. '
          'So wächst die Schuld.',
          style: textTheme.bodyMedium?.copyWith(color: klar.warn),
        ),
      ];
    }
    final end = plan['end_date'];
    final extra = _extraResult;
    final years = plan['years'] is List
        ? (plan['years'] as List).whereType<Map>().toList()
        : const <Map>[];
    return [
      AmountHeadline(
        label: since > 0 ? 'Restschuld, geschätzt' : 'Restschuld',
        amount: formatEuro(today / 100),
        note: since > 0
            ? 'Eingetragen waren '
                  '${formatEuro(_int(plan['entered_cents']) / 100)} am '
                  '${formatShortDate(plan['entered_on']?.toString() ?? '')}, '
                  'seitdem $since ${since == 1 ? 'Rate' : 'Raten'}.'
            : null,
        size: 36,
      ),
      if (bookedRatesText(plan) case (final text, final missing)) ...[
        const SizedBox(height: 10),
        Text(
          text,
          style: textTheme.bodySmall?.copyWith(
            color: missing ? klar.warn : null,
          ),
        ),
      ],
      const SizedBox(height: 14),
      _Fact('Sollzins', '${_percent(_int(plan['rate_milli']))} % pro Jahr'),
      _Fact(
        'Monatsrate',
        '${formatEuro(_int(plan['payment_cents']) / 100)}, davon zurzeit '
            '${formatEuro(_int(plan['first_interest_cents']) / 100)} Zinsen',
      ),
      _Fact(
        'Fertig',
        end is String
            ? '${_monthYear(end)}, in ${_span(_int(plan['months']))}'
            : 'in mehr als 60 Jahren',
      ),
      _Fact('Noch Zinsen', formatEuro(_int(plan['interest_cents']) / 100)),
      const SizedBox(height: 18),
      Text('Sondertilgung', style: textTheme.titleMedium),
      const SizedBox(height: 8),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: _extra,
              enabled: !_busy,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(labelText: 'Betrag in Euro'),
              onSubmitted: (_) => _calculate(),
            ),
          ),
          const SizedBox(width: 10),
          FilledButton(
            onPressed: _busy ? null : _calculate,
            child: const Text('Rechnen'),
          ),
        ],
      ),
      if (_error != null) ...[
        const SizedBox(height: 8),
        Text(_error!, style: textTheme.bodySmall?.copyWith(color: klar.warn)),
      ],
      if (extra != null) ...[
        const SizedBox(height: 12),
        OutlinedPanel(
          child: Text(
            _int(extra['months']) == 0
                ? 'Damit wäre der Kredit sofort getilgt.'
                : 'Fertig ${_monthYear(extra['end_date']?.toString() ?? '')}, '
                      '${_span(_int(extra['months_saved']))} früher. Du '
                      'sparst ${formatEuro(_int(extra['interest_saved_cents']) / 100)} '
                      'Zinsen. Ob du ohne Gebühr sondertilgen darfst, steht im '
                      'Vertrag.',
            style: textTheme.bodyMedium,
          ),
        ),
      ],
      if (years.isNotEmpty) ...[
        const SizedBox(height: 18),
        Text('Plan je Jahr', style: textTheme.titleMedium),
        const SizedBox(height: 6),
        for (final year in years.take(40))
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Row(
              children: [
                SizedBox(width: 52, child: Text('${year['year']}')),
                Expanded(
                  child: Text(
                    '${formatEuro(_int(year['paid_cents']) / 100)} gezahlt, '
                    'davon ${formatEuro(_int(year['interest_cents']) / 100)} '
                    'Zinsen',
                    style: textTheme.bodySmall,
                  ),
                ),
                Text(formatEuro(_int(year['rest_cents']) / 100)),
              ],
            ),
          ),
      ],
      const SizedBox(height: 12),
      Text(
        'Geschätzt mit monatlicher Verrechnung und gleichbleibendem Zins. '
        'Verbindlich ist der Auszug der Bank.',
        style: textTheme.bodySmall,
      ),
    ];
  }
}

class _Fact extends StatelessWidget {
  const _Fact(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 110, child: Text(label, style: textTheme.bodySmall)),
          Expanded(child: Text(value, style: textTheme.bodyMedium)),
        ],
      ),
    );
  }
}
