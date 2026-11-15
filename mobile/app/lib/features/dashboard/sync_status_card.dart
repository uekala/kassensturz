import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// Says how old the bank data is and fetches on request. Pulling the page
/// down only reloads from the server; this is the way to ask the banks.
class SyncStatusCard extends StatelessWidget {
  const SyncStatusCard({required this.controller, super.key});

  final MobileConnectionController controller;

  Future<void> _start(BuildContext context) async {
    final messenger = ScaffoldMessenger.maybeOf(context);
    final message = await controller.startBankSync();
    if (message.isEmpty) return;
    messenger
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final status = controller.syncStatus;
    if (status == null || status.sources == 0) return const SizedBox.shrink();
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final now = controller.now;
    final running = controller.bankSyncRunning || status.running;
    final last = status.lastSync;
    final next = status.nextSync;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(
        color: klar.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: klar.border, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Bankabruf', style: textTheme.labelMedium),
          const SizedBox(height: 4),
          Text(
            last == null
                ? 'Noch nicht alle Banken abgerufen'
                : 'Stand: ${formatMoment(last, now)}',
            style: textTheme.titleMedium,
          ),
          if (next != null) ...[
            const SizedBox(height: 2),
            Text(
              'Nächster von selbst: ${formatMoment(next, now)}',
              style: textTheme.bodyMedium,
            ),
          ],
          for (final problem in status.problems) ...[
            const SizedBox(height: 6),
            Text(problem, style: TextStyle(color: klar.warn, fontSize: 13)),
          ],
          const SizedBox(height: 12),
          if (running)
            Row(
              children: [
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Die Banken werden abgerufen …',
                    style: textTheme.bodyMedium,
                  ),
                ),
              ],
            )
          else if (status.canStart)
            OutlinedButton.icon(
              onPressed: () => _start(context),
              icon: const Icon(Icons.sync_rounded, size: 18),
              label: const Text('Jetzt abrufen'),
            )
          else if (status.waitMinutes > 0)
            Text(
              status.waitMinutes == 1
                  ? 'Erneut abrufen geht in einer Minute. Banken erlauben '
                        'nur wenige Abrufe am Tag.'
                  : 'Erneut abrufen geht in ${status.waitMinutes} Minuten. '
                        'Banken erlauben nur wenige Abrufe am Tag.',
              style: textTheme.bodyMedium,
            )
          else
            Text(
              'Diese Banken lassen sich nur in Home Assistant abrufen.',
              style: textTheme.bodyMedium,
            ),
        ],
      ),
    );
  }
}
