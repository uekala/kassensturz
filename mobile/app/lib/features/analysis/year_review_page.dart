import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';

const _monthInitials = [
  'J',
  'F',
  'M',
  'A',
  'M',
  'J',
  'J',
  'A',
  'S',
  'O',
  'N',
  'D',
];

Map<String, dynamic> _map(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

List<Map<String, dynamic>> _maps(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
}

int _int(dynamic value) => value is int ? value : 0;

String _euro(int cents) => formatEuro(cents / 100);

/// "+12 % zum Vorjahr" or similar; empty without a year before.
String _change(int cents, dynamic previous) {
  if (previous is! int) return '';
  if (previous == 0) return cents == 0 ? '' : ' · neu';
  final percent = ((cents - previous) / previous * 100).round();
  if (percent == 0) return ' · wie im Vorjahr';
  return ' · ${percent > 0 ? '+' : '−'}${percent.abs()} % zum Vorjahr';
}

/// The sentences under the totals, from the figures the server sends.
String yearReviewText(Map<String, dynamic> review) {
  final lines = <String>[];
  final saved = _int(review['saved_cents']);
  final rate = review['savings_rate'];
  if (saved > 0 && rate is num) {
    lines.add('Gespart ${_euro(saved)}, Sparquote ${(rate * 100).round()} %.');
  } else if (saved < 0) {
    lines.add('${_euro(-saved)} mehr ausgegeben als eingenommen.');
  }
  final previous = review['previous'];
  if (previous is Map) {
    final change =
        _int(review['expense_cents']) - _int(previous['expense_cents']);
    final until = review['running'] == true ? ' bis zum selben Tag' : '';
    lines.add(
      change.abs() < 5000
          ? 'Ausgaben etwa wie im Vorjahr$until.'
          : 'Ausgaben ${_euro(change.abs())} '
                '${change > 0 ? 'höher' : 'niedriger'} als im Vorjahr$until.',
    );
  }
  final expense = _int(review['expense_cents']);
  final fixed = _int(review['fixed_cents']);
  if (expense > 0 && fixed > 0) {
    lines.add(
      '${(fixed / expense * 100).round()} % der Ausgaben waren feste '
      'Zahlungen aus Verträgen.',
    );
  }
  final best = review['best_month'];
  final worst = review['worst_month'];
  if (best is Map && worst is Map && best['month'] != worst['month']) {
    lines.add(
      'Bester Monat: ${best['label']} (${_euro(_int(best['saldo_cents']))}), '
      'schwächster: ${worst['label']} '
      '(${_euro(_int(worst['saldo_cents']))}).',
    );
  }
  return lines.join(' ');
}

/// A whole year: totals, months, categories and the biggest single expenses,
/// compared with the year before. All figures come from the server.
class YearReviewPage extends StatefulWidget {
  const YearReviewPage({required this.controller, this.year, super.key});

  final MobileConnectionController controller;
  final int? year;

  @override
  State<YearReviewPage> createState() => _YearReviewPageState();
}

class _YearReviewPageState extends State<YearReviewPage> {
  late int _year;
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _year = widget.year ?? DateTime.now().year;
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final controller = widget.controller;
    final part = controller.canFilterParts ? controller.viewPart : null;
    final result = await controller.readOnce(
      (api) => api.yearReview(year: _year, part: part),
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = result.error;
      if (result.data != null) _data = result.data;
    });
  }

  void _show(int year) {
    if (year == _year) return;
    _year = year;
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final data = _data ?? const <String, dynamic>{};
    final shown = _data != null && data['year'] == _year;
    final rawYears = data['years'];
    final years = rawYears is List
        ? rawYears.whereType<int>().toList()
        : <int>[];
    final biggest = _maps(data['biggest']);
    final previous = shown ? _map(data['previous']) : <String, dynamic>{};
    final hasPrevious = shown && data['previous'] is Map;
    final until = shown && data['running'] == true
        ? ' bis ${formatShortDate(data['until']?.toString() ?? '')}'
        : '';
    final text = shown ? yearReviewText(data) : '';

    return Scaffold(
      appBar: AppBar(title: Text('Jahresrückblick $_year')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 32),
          children: [
            if (years.length > 1) ...[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final year in years)
                    ChoiceChip(
                      label: Text('$year'),
                      selected: year == _year,
                      onSelected: (_) => _show(year),
                    ),
                ],
              ),
              const SizedBox(height: 10),
            ],
            if (_loading)
              const LinearProgressIndicator(minHeight: 2)
            else
              const SizedBox(height: 2),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(
                _error!,
                style: textTheme.bodySmall?.copyWith(color: klar.warn),
              ),
            ],
            const SizedBox(height: 14),
            if (!shown)
              QuietMessage(_loading ? 'Wird geladen …' : 'Nichts zu zeigen.')
            else if (data['has_data'] != true)
              QuietMessage('Für $_year gibt es keine Buchungen.')
            else ...[
              AmountHeadline(
                label: 'Ausgaben$until',
                amount: _euro(_int(data['expense_cents'])),
                note:
                    'Einnahmen ${_euro(_int(data['income_cents']))} · '
                    'Saldo ${formatSignedEuro(_int(data['saved_cents']) / 100)}',
                size: 40,
              ),
              if (hasPrevious) ...[
                const SizedBox(height: 6),
                Text(
                  'Vorjahr: Ausgaben ${_euro(_int(previous['expense_cents']))}'
                  ', Einnahmen ${_euro(_int(previous['income_cents']))}',
                  style: textTheme.bodySmall,
                ),
              ],
              if (text.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(text, style: textTheme.bodyMedium),
              ],
              const SizedBox(height: 24),
              const SectionTitle('Je Monat'),
              const SizedBox(height: 12),
              _MonthBars(months: _maps(data['months'])),
              const SizedBox(height: 26),
              const SectionTitle('Wofür das Geld ging'),
              const SizedBox(height: 10),
              for (final category in _maps(data['categories']))
                _CategoryRow(category: category),
              if (biggest.isNotEmpty) ...[
                const SizedBox(height: 14),
                const SectionTitle('Größte Einzelausgaben'),
                const SizedBox(height: 4),
                Text('ohne Verträge', style: textTheme.bodySmall),
                const SizedBox(height: 6),
                for (final item in biggest)
                  EntryRow(
                    title: item['name']?.toString() ?? 'Ohne Empfänger',
                    detail: formatShortDate(item['date']?.toString() ?? ''),
                    amount: _euro(-_int(item['amount_cents'])),
                  ),
              ],
              const SizedBox(height: 16),
              Text(
                '${_int(data['count'])} Buchungen, ohne Umbuchungen zwischen '
                'eigenen Konten.',
                style: textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _CategoryRow extends StatelessWidget {
  const _CategoryRow({required this.category});

  final Map<String, dynamic> category;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final raw = category['share'];
    final share = (raw is num ? raw.toDouble() : 0.0).clamp(0.0, 1.0);
    final cents = _int(category['cents']);
    final percent = share < 0.005 ? 'unter 1 %' : '${(share * 100).round()} %';
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  category['name']?.toString() ?? 'Ohne Kategorie',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: textTheme.titleMedium,
                ),
              ),
              const SizedBox(width: 10),
              Text(_euro(cents), style: textTheme.bodyMedium),
            ],
          ),
          const SizedBox(height: 6),
          ThickBar(value: share.toDouble()),
          const SizedBox(height: 4),
          Text(
            '$percent der Ausgaben'
            '${_change(cents, category['previous_cents'])}',
            style: textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _MonthBars extends StatelessWidget {
  const _MonthBars({required this.months});

  final List<Map<String, dynamic>> months;

  static const _chartHeight = 120.0;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    var highest = 1;
    for (final item in months) {
      highest = math.max(highest, _int(item['income_cents']));
      highest = math.max(highest, _int(item['expense_cents']));
    }

    Widget bar(int cents, Color color) {
      return Container(
        width: 7,
        height: math.max(2.0, _chartHeight * cents / highest),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(3.5),
        ),
      );
    }

    String initial(dynamic key) {
      if (key is! String || key.length < 7) return '';
      final month = int.tryParse(key.substring(5, 7));
      if (month == null || month < 1 || month > 12) return '';
      return _monthInitials[month - 1];
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (final item in months)
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      height: _chartHeight,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          bar(_int(item['income_cents']), klar.brand),
                          const SizedBox(width: 2),
                          bar(_int(item['expense_cents']), klar.ink),
                        ],
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(initial(item['month']), style: textTheme.bodySmall),
                  ],
                ),
              ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            _Legend(label: 'Einnahmen', color: klar.brand),
            const SizedBox(width: 16),
            _Legend(label: 'Ausgaben', color: klar.ink),
          ],
        ),
      ],
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
