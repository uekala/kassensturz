import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';

/// Shown instead of financial data while the app is not paired with a
/// server. The app keeps no financial data of its own.
class ConnectRequiredPage extends StatelessWidget {
  const ConnectRequiredPage({required this.onOpenSettings, super.key});

  final VoidCallback onOpenSettings;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: klar.softBrand,
                borderRadius: BorderRadius.circular(18),
              ),
              child: Icon(
                Icons.cloud_sync_outlined,
                color: klar.brand,
                size: 30,
              ),
            ),
            const SizedBox(height: 18),
            Text(
              'Noch nicht verbunden',
              style: textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Deine Konten, Umsätze und Budgets liegen auf deinem '
              'Kassensturz-Server. Verbinde dieses Gerät, um sie zu sehen.',
              textAlign: TextAlign.center,
              style: textTheme.bodyMedium,
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: onOpenSettings,
              icon: const Icon(Icons.link_rounded),
              label: const Text('Mit Server verbinden'),
            ),
          ],
        ),
      ),
    );
  }
}
