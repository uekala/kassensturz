import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';

/// Read-only list of the contracts the server detected or the user entered.
/// Loads them when it is first shown.
class ContractsView extends StatefulWidget {
  const ContractsView({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<ContractsView> createState() => _ContractsViewState();
}

class _ContractsViewState extends State<ContractsView> {
  @override
  void initState() {
    super.initState();
    // Loading notifies listeners at once; wait until this build is finished.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.controller.loadContracts();
    });
  }

  static String _date(String? value) {
    final date = value == null ? null : DateTime.tryParse(value);
    if (date == null) return '';
    return formatDate(date);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final contracts = controller.contracts
            .where((contract) => contract.running)
            .toList();
        final monthly = contracts
            .where((contract) => contract.kind == 'expense')
            .fold<int>(0, (sum, contract) => sum + contract.monthlyCents);
        return RefreshIndicator(
          onRefresh: controller.loadContracts,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
            children: [
              AmountHeadline(
                label: 'Fixkosten pro Monat',
                amount: formatEuro(monthly.abs() / 100),
                note: '${contracts.length} laufende Verträge',
                size: 40,
              ),
              const SizedBox(height: 18),
              if (controller.contractsError != null) ...[
                Text(
                  controller.contractsError!,
                  style: textTheme.bodySmall?.copyWith(color: AppTheme.warn),
                ),
                const SizedBox(height: 10),
              ],
              if (controller.contractsLoading && contracts.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(28),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (contracts.isEmpty)
                const QuietMessage('Der Server kennt noch keine Verträge.')
              else
                for (var index = 0; index < contracts.length; index++) ...[
                  if (index > 0) const Divider(height: 1),
                  _ContractRow(
                    contract: contracts[index],
                    nextDue: _date(contracts[index].nextDue),
                    deadline: _date(contracts[index].cancellationDeadline),
                  ),
                ],
            ],
          ),
        );
      },
    );
  }
}

class _ContractRow extends StatelessWidget {
  const _ContractRow({
    required this.contract,
    required this.nextDue,
    required this.deadline,
  });

  final ServerContract contract;
  final String nextDue;
  final String deadline;

  @override
  Widget build(BuildContext context) {
    final interval = contract.interval ?? '';
    final details = <String>[
      if (interval.isNotEmpty) interval,
      if (contract.categoryName != null) contract.categoryName!,
      if (nextDue.isNotEmpty) 'nächste Zahlung $nextDue',
      if (deadline.isNotEmpty) 'kündbar bis $deadline',
    ].join(' · ');
    return EntryRow(
      title: contract.name,
      detail: details.isEmpty ? 'Vertrag' : details,
      amount: formatSignedEuro(contract.amountCents / 100),
      positive: contract.amountCents > 0,
    );
  }
}
