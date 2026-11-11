import 'package:flutter/material.dart';

import '../../core/networking/mobile_connection_controller.dart';
import '../more/contracts_page.dart';

/// Budgets and contracts behind one tab.
class PlanningPage extends StatefulWidget {
  const PlanningPage({
    required this.controller,
    required this.budgets,
    super.key,
  });

  final MobileConnectionController controller;
  final Widget budgets;

  @override
  State<PlanningPage> createState() => _PlanningPageState();
}

class _PlanningPageState extends State<PlanningPage> {
  bool _showContracts = false;

  /// Contracts are loaded from the server the first time they are opened.
  bool _contractsOpened = false;

  void _select(Set<bool> selection) {
    setState(() {
      _showContracts = selection.first;
      if (_showContracts) _contractsOpened = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 10),
          child: SizedBox(
            width: double.infinity,
            child: SegmentedButton<bool>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: false, label: Text('Budgets')),
                ButtonSegment(value: true, label: Text('Verträge')),
              ],
              selected: {_showContracts},
              onSelectionChanged: _select,
            ),
          ),
        ),
        Expanded(
          child: IndexedStack(
            index: _showContracts ? 1 : 0,
            children: [
              widget.budgets,
              if (_contractsOpened)
                _Contracts(controller: widget.controller)
              else
                const SizedBox.shrink(),
            ],
          ),
        ),
      ],
    );
  }
}

class _Contracts extends StatelessWidget {
  const _Contracts({required this.controller});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        if (!controller.isConnected) {
          return const _Notice(
            'Verträge siehst du, sobald die App mit deinem Server '
            'verbunden ist.',
          );
        }
        if (!controller.canWriteTransactions) {
          return const _Notice(
            'Bitte aktualisiere Kassensturz in Home Assistant, um Verträge '
            'zu sehen.',
          );
        }
        return ContractsView(controller: controller);
      },
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(28),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.bodyMedium,
      ),
    );
  }
}
