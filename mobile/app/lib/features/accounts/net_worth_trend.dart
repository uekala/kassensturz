import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';

/// Vermögen über die letzten Monate als Linie, mit der Veränderung in Worten.
/// Zeigt nichts, bis der Server mindestens zwei Punkte hat.
class NetWorthTrend extends StatefulWidget {
  const NetWorthTrend({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<NetWorthTrend> createState() => _NetWorthTrendState();
}

class _NetWorthTrendState extends State<NetWorthTrend> {
  List<({DateTime day, int cents})> _points = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final points = await widget.controller.loadNetWorthHistory();
    if (mounted) setState(() => _points = points);
  }

  static const _months = [
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

  @override
  Widget build(BuildContext context) {
    if (_points.length < 2) return const SizedBox.shrink();
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final first = _points.first;
    final change = _points.last.cents - first.cents;
    final since = 'Ende ${_months[first.day.month - 1]} ${first.day.year}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 84,
            width: double.infinity,
            child: CustomPaint(
              painter: _TrendPainter(
                values: [for (final point in _points) point.cents.toDouble()],
                line: klar.brand,
                guide: klar.border,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            change == 0
                ? 'Unverändert seit $since'
                : '${formatSignedEuro(change / 100)} seit $since',
            style: textTheme.bodyMedium?.copyWith(
              color: change < 0 ? klar.warn : null,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _TrendPainter extends CustomPainter {
  _TrendPainter({
    required this.values,
    required this.line,
    required this.guide,
  });

  final List<double> values;
  final Color line;
  final Color guide;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;
    var low = values.reduce(math.min);
    var high = values.reduce(math.max);
    if (high - low < 1) {
      high += 1;
      low -= 1;
    }
    const inset = 6.0;
    final height = size.height - inset * 2;
    final step = size.width / (values.length - 1);
    Offset at(int index) => Offset(
      index * step,
      inset + height - (values[index] - low) / (high - low) * height,
    );

    if (low < 0 && high > 0) {
      final zero = inset + height - (0 - low) / (high - low) * height;
      canvas.drawLine(
        Offset(0, zero),
        Offset(size.width, zero),
        Paint()
          ..color = guide
          ..strokeWidth = 1,
      );
    }
    final path = Path()..moveTo(at(0).dx, at(0).dy);
    for (var index = 1; index < values.length; index++) {
      path.lineTo(at(index).dx, at(index).dy);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = line
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
    canvas.drawCircle(at(values.length - 1), 4, Paint()..color = line);
  }

  @override
  bool shouldRepaint(_TrendPainter old) =>
      old.values != values || old.line != line || old.guide != guide;
}
