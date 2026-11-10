import 'package:flutter/material.dart';

import '../../core/data/demo_finance_data.dart';
import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// Read-only list of the contracts the server detected or the user entered.
class ContractsPage extends StatefulWidget {
  const ContractsPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<ContractsPage> createState() => _ContractsPageState();
}

class _ContractsPageState extends State<ContractsPage> {
  @override
  void initState() {
    super.initState();
    widget.controller.loadContracts();
  }

  static String _date(String? value) {
    final date = value == null ? null : DateTime.tryParse(value);
    if (date == null) return '';
    final day = date.day.toString().padLeft(2, '0');
    final month = date.month.toString().padLeft(2, '0');
    return '$day.$month.${date.year}';
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Verträge')),
      body: AnimatedBuilder(
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
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
              children: [
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: AppTheme.brand,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'FIXKOSTEN PRO MONAT',
                        style: TextStyle(color: Colors.white70, fontSize: 11),
                      ),
                      const SizedBox(height: 7),
                      Text(
                        formatEuro(monthly.abs() / 100),
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 27,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        '${contracts.length} laufende Verträge vom Server',
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                if (controller.contractsError != null) ...[
                  Text(
                    controller.contractsError!,
                    style: TextStyle(color: colors.error, fontSize: 12),
                  ),
                  const SizedBox(height: 10),
                ],
                if (controller.contractsLoading && contracts.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(28),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else if (contracts.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 28),
                    child: Center(
                      child: Text('Der Server kennt noch keine Verträge.'),
                    ),
                  )
                else
                  for (final contract in contracts)
                    _ContractCard(
                      contract: contract,
                      interval: contract.interval ?? '',
                      nextDue: _date(contract.nextDue),
                      deadline: _date(contract.cancellationDeadline),
                    ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _ContractCard extends StatelessWidget {
  const _ContractCard({
    required this.contract,
    required this.interval,
    required this.nextDue,
    required this.deadline,
  });

  final ServerContract contract;
  final String interval;
  final String nextDue;
  final String deadline;

  @override
  Widget build(BuildContext context) {
    final details = <String>[
      if (interval.isNotEmpty) interval,
      if (contract.categoryName != null) contract.categoryName!,
      if (nextDue.isNotEmpty) 'nächste Zahlung $nextDue',
      if (deadline.isNotEmpty) 'kündbar bis $deadline',
    ].join(' · ');
    return Card(
      margin: const EdgeInsets.only(bottom: 9),
      child: ListTile(
        title: Text(
          contract.name,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: details.isEmpty ? null : Text(details),
        trailing: Text(
          formatSignedEuro(contract.amountCents / 100),
          style: TextStyle(
            fontWeight: FontWeight.w700,
            color: contract.amountCents < 0
                ? Theme.of(context).colorScheme.onSurface
                : AppTheme.accent,
          ),
        ),
      ),
    );
  }
}
