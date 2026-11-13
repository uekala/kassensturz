import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';

/// Opens the sheet that answers "can I afford this?".
Future<void> showAffordSheet(
  BuildContext context, {
  required MobileConnectionController controller,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: AffordSheet(controller: controller),
  ),
);

class AffordSheet extends StatefulWidget {
  const AffordSheet({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<AffordSheet> createState() => _AffordSheetState();
}

class _AffordSheetState extends State<AffordSheet> {
  final _amount = TextEditingController();
  bool _loading = false;
  String? _error;
  Map<String, dynamic>? _answer;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _check() async {
    final cents = parseAmountToCents(_amount.text);
    if (cents == null) {
      setState(() {
        _answer = null;
        _error = 'Bitte einen Betrag größer als 0 eingeben.';
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    final result = await widget.controller.afford(cents);
    if (!mounted) return;
    setState(() {
      _loading = false;
      _answer = result.answer;
      _error = result.error;
    });
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final answer = _answer;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Kann ich mir das leisten?', style: textTheme.titleLarge),
            const SizedBox(height: 6),
            Text(
              'Rechnet mit deinem Kontostand, den festen Abbuchungen und dem, '
              'was du sonst im Alltag ausgibst.',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _amount,
              autofocus: true,
              enabled: !_loading,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Betrag in Euro',
                hintText: '0,00',
              ),
              onSubmitted: (_) => _check(),
            ),
            const SizedBox(height: 14),
            FilledButton(
              onPressed: _loading ? null : _check,
              child: Text(_loading ? 'Rechnet …' : 'Prüfen'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!,
                style: textTheme.bodySmall?.copyWith(color: klar.warn),
              ),
            ],
            if (answer != null) ...[
              const SizedBox(height: 18),
              OutlinedPanel(child: _AffordAnswer(answer: answer)),
            ],
          ],
        ),
      ),
    );
  }
}

class _AffordAnswer extends StatelessWidget {
  const _AffordAnswer({required this.answer});

  final Map<String, dynamic> answer;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    int cents(String key) => answer[key] is int ? answer[key] as int : 0;
    String euro(int value) => formatEuro(value / 100);

    final verdict = answer['verdict'];
    final headline = switch (verdict) {
      'yes' => 'Ja, das passt.',
      'tight' => 'Knapp.',
      _ => 'Nein, das reißt ein Loch.',
    };
    final until = answer['period_label'] == 'bis Monatsende'
        ? 'bis Monatsende'
        : 'bis zum nächsten Gehalt';
    final lines = <String>[
      if (verdict == 'no')
        'Nach den festen Abbuchungen sind nur '
            '${euro(cents('free_before_cents'))} frei. Es fehlen '
            '${euro(-cents('free_after_cents'))}.'
      else ...[
        'Danach bleiben ${euro(cents('free_after_cents'))} $until, das sind '
            '${euro(cents('per_day_after_cents'))} pro Tag statt '
            '${euro(cents('per_day_before_cents'))}.',
        if (cents('per_day_after_cents') < cents('usual_per_day_cents'))
          'Für den Alltag gibst du sonst '
              '${euro(cents('usual_per_day_cents'))} pro Tag aus.',
      ],
    ];
    final low = answer['low_point_after'];
    if (answer['below_threshold'] == true && low is Map) {
      final date = low['date'];
      final value = low['cents'];
      if (date is String && value is int) {
        lines.add(
          'Die Prognose fällt am ${formatShortDate(date)} auf ${euro(value)}.',
        );
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          headline,
          style: textTheme.titleMedium?.copyWith(
            color: verdict == 'yes' ? klar.ink : klar.warn,
          ),
        ),
        const SizedBox(height: 6),
        Text(lines.join(' '), style: textTheme.bodyMedium),
      ],
    );
  }
}
