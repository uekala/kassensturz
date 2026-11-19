import 'package:flutter/material.dart';

import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';

String _kwh(dynamic value) =>
    value is num ? value.toStringAsFixed(1).replaceAll('.', ',') : '–';

String _perKwh(dynamic cents) =>
    cents is num ? '${formatEuro(cents / 100)}/kWh' : '';

/// One charging session in a line: kWh, price per kWh, place and time.
String chargingLine(Map<String, dynamic> c) {
  final started = c['started']?.toString() ?? '';
  final when = started.length >= 16
      ? '${formatShortDate(started.substring(0, 10))}, '
            '${started.substring(11, 16)}'
      : '';
  final idle = c['idle_cents'];
  final site = c['site'];
  return [
    '${_kwh(c['kwh'])} kWh',
    _perKwh(c['price_per_kwh_cents']),
    if (c['network'] == 'multipass') 'MultiPass',
    if (site is String) site,
    when,
    if (idle is int && idle > 0)
      'davon Blockiergebühr ${formatEuro(idle / 100)}',
  ].where((part) => part.isNotEmpty).join(' · ');
}

/// What Ladecockpit knows about the charging a booking paid for. Shows
/// nothing for other bookings.
class TransactionChargingSection extends StatefulWidget {
  const TransactionChargingSection({
    required this.controller,
    required this.transactionId,
    super.key,
  });

  final MobileConnectionController controller;
  final int transactionId;

  @override
  State<TransactionChargingSection> createState() =>
      _TransactionChargingSectionState();
}

class _TransactionChargingSectionState
    extends State<TransactionChargingSection> {
  Map<String, dynamic>? _charge;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.readOnce(
      (api) => api.transactionCharging(widget.transactionId),
    );
    final charge = result.data?['charging'];
    if (!mounted || charge is! Map) return;
    setState(() => _charge = Map<String, dynamic>.from(charge));
  }

  @override
  Widget build(BuildContext context) {
    final charge = _charge;
    if (charge == null) return const SizedBox.shrink();
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Laden', style: textTheme.labelMedium),
          const SizedBox(height: 4),
          Text(chargingLine(charge), style: textTheme.bodyMedium),
        ],
      ),
    );
  }
}

/// Charging of the shown month in the analysis. Shows nothing while
/// Ladecockpit has not reported any session.
class ChargingMonthCard extends StatefulWidget {
  const ChargingMonthCard({
    required this.controller,
    required this.month,
    super.key,
  });

  final MobileConnectionController controller;

  /// yyyy-MM of the month the analysis shows.
  final String month;

  @override
  State<ChargingMonthCard> createState() => _ChargingMonthCardState();
}

class _ChargingMonthCardState extends State<ChargingMonthCard> {
  List<Map<String, dynamic>> _months = const [];
  int _unlinked = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.readOnce(
      (api) => api.chargingMonths(),
    );
    final data = result.data;
    final months = data?['months'];
    if (!mounted || months is! List) return;
    final unlinked = data?['unlinked_count'];
    setState(() {
      _months = [
        for (final m in months.whereType<Map>()) Map<String, dynamic>.from(m),
      ];
      _unlinked = unlinked is int ? unlinked : 0;
    });
  }

  String _text() {
    final month = _months.where((m) => m['month'] == widget.month).firstOrNull;
    final sessions = month?['sessions'];
    final total = month?['total_cents'];
    if (month == null || sessions is! int || total is! int) {
      return 'In diesem Monat nicht geladen.';
    }
    final price = _perKwh(month['price_per_kwh_cents']);
    return [
      '$sessions ${sessions == 1 ? 'Ladevorgang' : 'Ladevorgänge'}',
      '${_kwh(month['kwh'])} kWh',
      formatEuro(total / 100),
      if (price.isNotEmpty) price,
    ].join(', ');
  }

  @override
  Widget build(BuildContext context) {
    if (_months.isEmpty) return const SizedBox.shrink();
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 26),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionTitle('Laden'),
          const SizedBox(height: 8),
          Text(_text(), style: textTheme.bodyMedium),
          if (_unlinked > 0) ...[
            const SizedBox(height: 4),
            Text(
              '$_unlinked ${_unlinked == 1 ? 'Ladevorgang hat' : 'Ladevorgänge haben'} '
              'noch keine passende Abbuchung.',
              style: textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }
}
