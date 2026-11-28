import 'package:material_ui/material_ui.dart';

import '../networking/mobile_connection_controller.dart';

/// Schaltet Umsätze und Auswertung um zwischen allem, was diese Person sieht,
/// nur ihren eigenen Konten und nur den gemeinsamen des Haushalts.
class PartFilter extends StatelessWidget {
  const PartFilter({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: SegmentedButton<String>(
        showSelectedIcon: false,
        segments: const [
          ButtonSegment(value: '', label: Text('Alle')),
          ButtonSegment(value: 'own', label: Text('Ich')),
          ButtonSegment(value: 'shared', label: Text('Gemeinsam')),
        ],
        selected: {controller.viewPart ?? ''},
        onSelectionChanged: (selection) => controller.setViewPart(
          selection.first.isEmpty ? null : selection.first,
        ),
      ),
    );
  }
}
