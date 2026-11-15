import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';

/// What arrived since the last visit. Stays until it is marked as read.
class NewsCard extends StatelessWidget {
  const NewsCard({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    final news = controller.news;
    if (news == null) return const SizedBox.shrink();
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final sums = [
      if (news.incomeCents > 0) formatSignedEuro(news.incomeCents / 100),
      if (news.expenseCents > 0) formatSignedEuro(-news.expenseCents / 100),
    ].join(' und ');

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 8, 10),
      decoration: BoxDecoration(
        color: klar.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: klar.ink, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Seit deinem letzten Besuch', style: textTheme.labelMedium),
          const SizedBox(height: 4),
          Text(
            news.count == 1
                ? 'Eine neue Buchung'
                : '${news.count} neue Buchungen',
            style: textTheme.titleMedium,
          ),
          if (sums.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(sums, style: textTheme.bodyMedium),
          ],
          const SizedBox(height: 8),
          for (final entry in news.largest)
            Padding(
              padding: const EdgeInsets.only(right: 8, bottom: 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      entry.label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.bodyMedium,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    formatSignedEuro(entry.amountCents / 100),
                    style: textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          if (news.count > news.largest.length)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Text(
                news.count - news.largest.length == 1
                    ? 'und eine weitere'
                    : 'und ${news.count - news.largest.length} weitere',
                style: textTheme.bodySmall,
              ),
            ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: controller.markNewsRead,
              child: const Text('Gelesen'),
            ),
          ),
        ],
      ),
    );
  }
}
