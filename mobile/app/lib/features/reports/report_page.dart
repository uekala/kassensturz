import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/pdf_bytes_view.dart';

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

/// Der Titel eines Berichts: "Monatsbericht Oktober 2026" oder
/// "Jahresrückblick 2026".
String reportTitle(String kind, String period) {
  if (kind == 'year') return 'Jahresrückblick $period';
  final month = period.length == 7 ? int.tryParse(period.substring(5)) : null;
  if (month == null || month < 1 || month > 12) return 'Monatsbericht';
  return 'Monatsbericht ${_monthNames[month - 1]} ${period.substring(0, 4)}';
}

/// Zeigt einen Bericht, den der Server als PDF geschrieben hat. Er bleibt im Arbeitsspeicher des Handys.
class ReportPage extends StatefulWidget {
  const ReportPage({
    required this.controller,
    required this.kind,
    required this.period,
    super.key,
  });

  final MobileConnectionController controller;
  final String kind;
  final String period;

  @override
  State<ReportPage> createState() => _ReportPageState();
}

class _ReportPageState extends State<ReportPage> {
  late final Future<({Uint8List? bytes, String? error})> _file = widget
      .controller
      .reportBytes(kind: widget.kind, period: widget.period);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(reportTitle(widget.kind, widget.period))),
      body: FutureBuilder(
        future: _file,
        builder: (context, snapshot) {
          final data = snapshot.data;
          if (data == null) {
            return const Center(child: CircularProgressIndicator());
          }
          final bytes = data.bytes;
          if (bytes == null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  data.error ?? 'Der Bericht ließ sich nicht laden.',
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          return PdfBytesView(
            bytes: bytes,
            errorText:
                'Der Bericht ließ sich nicht anzeigen. Du findest ihn auch in '
                'Kassensturz in Home Assistant unter Budgets.',
          );
        },
      ),
    );
  }
}
