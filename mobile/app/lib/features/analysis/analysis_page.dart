import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';

const _monthNames = [
  'Januar',
  'Februar',
  'März',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
];

/// Spending by category, the last twelve months and the balance curve.
/// All figures come from the server; the page only draws them.
class AnalysisPage extends StatefulWidget {
  const AnalysisPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<AnalysisPage> createState() => _AnalysisPageState();
}

class _AnalysisPageState extends State<AnalysisPage> {
  late DateTime _month;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _month = DateTime(now.year, now.month);
    // Loading notifies listeners at once; wait until this build is finished.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.controller.loadStats(month: _key(_month));
    });
  }

  bool get _isCurrentMonth {
    final now = DateTime.now();
    return _month.year == now.year && _month.month == now.month;
  }

  static String _key(DateTime month) {
    return '${month.year}-${month.month.toString().padLeft(2, '0')}';
  }

  void _shift(int months) {
    setState(() => _month = DateTime(_month.year, _month.month + months));
    widget.controller.loadStats(month: _key(_month));
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Auswertung')),
      body: AnimatedBuilder(
        animation: widget.controller,
        builder: (context, _) {
          final controller = widget.controller;
          final stats = controller.stats;
          final month = _map(stats?['month']);
          final shown = month['month'] == _key(_month);
          final categories = shown
              ? _maps(stats?['categories'])
              : const <Map<String, dynamic>>[];
          final history = _maps(stats?['history']);
          final curve = _map(stats?['balance_curve']);
          final expense = shown ? _int(month['expense_cents']) : 0;
          final income = shown ? _int(month['income_cents']) : 0;

          return RefreshIndicator(
            onRefresh: () => controller.loadStats(month: _key(_month)),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 32),
              children: [
                Row(
                  children: [
                    IconButton(
                      tooltip: 'Vorheriger Monat',
                      onPressed: () => _shift(-1),
                      icon: const Icon(Icons.chevron_left_rounded),
                    ),
                    Expanded(
                      child: Text(
                        '${_monthNames[_month.month - 1]} ${_month.year}',
                        textAlign: TextAlign.center,
                        style: textTheme.titleLarge,
                      ),
                    ),
                    IconButton(
                      tooltip: 'Nächster Monat',
                      onPressed: _isCurrentMonth ? null : () => _shift(1),
                      icon: const Icon(Icons.chevron_right_rounded),
                    ),
                  ],
                ),
                if (controller.statsLoading)
                  const LinearProgressIndicator(minHeight: 2)
                else
                  const SizedBox(height: 2),
                if (controller.statsError != null) ...[
                  const SizedBox(height: 10),
                  Text(
                    controller.statsError!,
                    style: textTheme.bodySmall?.copyWith(color: klar.warn),
                  ),
                ],
                const SizedBox(height: 14),
                AmountHeadline(
                  label: 'Ausgaben',
                  amount: formatEuro(expense / 100),
                  note:
                      'Einnahmen ${formatEuro(income / 100)} · '
                      'Saldo ${formatSignedEuro((income - expense) / 100)}',
                  size: 40,
                ),
                const SizedBox(height: 24),
                const SectionTitle('Nach Kategorie'),
                const SizedBox(height: 10),
                if (categories.isEmpty)
                  QuietMessage(
                    controller.statsLoading
                        ? 'Wird geladen …'
                        : 'In diesem Monat gibt es keine Ausgaben.',
                  )
                else
                  for (final category in categories)
                    _CategoryRow(category: category),
                const SizedBox(height: 14),
                const SectionTitle('Letzte 12 Monate'),
                const SizedBox(height: 12),
                if (history.isEmpty)
                  const QuietMessage('Noch keine Monatswerte vorhanden.')
                else
                  _HistoryBars(history: history, selected: _key(_month)),
                const SizedBox(height: 26),
                const SectionTitle('Kontostand'),
                const SizedBox(height: 4),
                Text(
                  'Die letzten Tage wie gebucht, die kommenden als Prognose.',
                  style: textTheme.bodySmall,
                ),
                const SizedBox(height: 14),
                _BalanceCurve(curve: curve),
              ],
            ),
          );
        },
      ),
    );
  }
}

Map<String, dynamic> _map(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

List<Map<String, dynamic>> _maps(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
}

int _int(dynamic value) => value is int ? value : 0;

double _double(dynamic value) => value is num ? value.toDouble() : 0.0;

class _CategoryRow extends StatelessWidget {
  const _CategoryRow({required this.category});

  final Map<String, dynamic> category;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final share = _double(category['share']).clamp(0.0, 1.0).toDouble();
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
              Text(
                '${formatEuro(_int(category['cents']) / 100)} · '
                '${(share * 100).round()} %',
                style: textTheme.bodyMedium,
              ),
            ],
          ),
          const SizedBox(height: 6),
          ThickBar(value: share),
        ],
      ),
    );
  }
}

class _HistoryBars extends StatelessWidget {
  const _HistoryBars({required this.history, required this.selected});

  final List<Map<String, dynamic>> history;
  final String selected;

  static const _chartHeight = 120.0;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    var highest = 1;
    for (final item in history) {
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

    Widget legend(String label, Color color) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(label, style: textTheme.bodySmall),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (final item in history)
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
                    Text(
                      _initial(item['month']),
                      style: textTheme.bodySmall?.copyWith(
                        color: item['month'] == selected
                            ? klar.brand
                            : klar.mutedInk,
                        fontWeight: item['month'] == selected
                            ? FontWeight.w700
                            : FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            legend('Einnahmen', klar.brand),
            const SizedBox(width: 16),
            legend('Ausgaben', klar.ink),
          ],
        ),
      ],
    );
  }

  /// First letter of the month name for a 'YYYY-MM' key.
  static String _initial(dynamic key) {
    if (key is! String || key.length < 7) return '';
    final month = int.tryParse(key.substring(5, 7));
    if (month == null || month < 1 || month > 12) return '';
    return _monthNames[month - 1].substring(0, 1);
  }
}

class _BalanceCurve extends StatelessWidget {
  const _BalanceCurve({required this.curve});

  final Map<String, dynamic> curve;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final points = _maps(curve['points']);
    if (points.length < 2) {
      return const QuietMessage('Noch kein Verlauf vorhanden.');
    }
    final booked = [
      for (final point in points)
        if (point['forecast'] != true) _double(point['cents']),
    ];
    final planned = [
      for (final point in points)
        if (point['forecast'] == true) _double(point['cents']),
    ];
    final low = _map(curve['low_point']);
    final lowCents = _int(low['cents']);
    final lowDate = low['date'] is String
        ? formatShortDate(low['date'] as String)
        : '';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 120,
          width: double.infinity,
          child: CustomPaint(
            painter: _CurvePainter(
              booked: booked,
              planned: planned,
              line: klar.brand,
              guide: klar.border,
              surface: klar.surface,
            ),
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: Text(
                formatShortDate(points.first['date']?.toString() ?? ''),
                style: textTheme.bodySmall,
              ),
            ),
            Text('heute', style: textTheme.labelMedium),
            Expanded(
              child: Text(
                formatShortDate(points.last['date']?.toString() ?? ''),
                textAlign: TextAlign.end,
                style: textTheme.bodySmall,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Text(
          'Tiefster erwarteter Stand: ${formatEuro(lowCents / 100)}'
          '${lowDate.isEmpty ? '' : ' am $lowDate'}',
          style: textTheme.bodyMedium?.copyWith(
            color: lowCents < 0 ? klar.warn : klar.mutedInk,
            fontWeight: lowCents < 0 ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ],
    );
  }
}

/// Booked days as a solid line, forecast days dashed, a ring marks today.
class _CurvePainter extends CustomPainter {
  _CurvePainter({
    required this.booked,
    required this.planned,
    required this.line,
    required this.guide,
    required this.surface,
  });

  final List<double> booked;
  final List<double> planned;
  final Color line;
  final Color guide;
  final Color surface;

  @override
  void paint(Canvas canvas, Size size) {
    final all = [...booked, ...planned];
    if (all.length < 2) return;
    var low = all.reduce(math.min);
    var high = all.reduce(math.max);
    if (high - low < 1) {
      high += 1;
      low -= 1;
    }
    const inset = 6.0;
    final height = size.height - inset * 2;
    final step = size.width / (all.length - 1);
    Offset at(int index) {
      final share = (all[index] - low) / (high - low);
      return Offset(index * step, inset + height - share * height);
    }

    final todayIndex = booked.isEmpty ? 0 : booked.length - 1;
    final today = at(todayIndex);
    canvas.drawLine(
      Offset(today.dx, 0),
      Offset(today.dx, size.height),
      Paint()
        ..color = guide
        ..strokeWidth = 1,
    );

    final solid = Paint()
      ..color = line
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    if (todayIndex > 0) {
      final path = Path()..moveTo(at(0).dx, at(0).dy);
      for (var index = 1; index <= todayIndex; index++) {
        path.lineTo(at(index).dx, at(index).dy);
      }
      canvas.drawPath(path, solid);
    }

    final dashed = Paint()
      ..color = line.withValues(alpha: 0.6)
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    for (var index = todayIndex; index < all.length - 1; index += 2) {
      canvas.drawLine(at(index), at(index + 1), dashed);
    }

    canvas.drawCircle(today, 4.5, Paint()..color = surface);
    canvas.drawCircle(
      today,
      4.5,
      Paint()
        ..color = line
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2,
    );
  }

  @override
  bool shouldRepaint(covariant _CurvePainter oldDelegate) {
    return oldDelegate.booked != booked ||
        oldDelegate.planned != planned ||
        oldDelegate.line != line ||
        oldDelegate.guide != guide ||
        oldDelegate.surface != surface;
  }
}
