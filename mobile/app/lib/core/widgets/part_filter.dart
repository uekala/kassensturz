import 'package:flutter/material.dart';

import '../networking/mobile_connection_controller.dart';

/// Switches the transactions and the analysis between everything this person
/// sees, only their own accounts and only the shared ones of the household.
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
