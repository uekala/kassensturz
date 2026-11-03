import 'package:flutter/material.dart';

class MorePage extends StatelessWidget {
  const MorePage({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(
          'Verbindung & Einstellungen',
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 6),
        Text(
          'Die Verbindung zu deinem eigenen Server folgt mit dem sicheren Mobile-Backend.',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 18),
        Card(
          elevation: 0,
          color: Colors.white,
          child: ListTile(
            leading: Icon(Icons.dns_outlined, color: colors.primary),
            title: const Text('Kassensturz-Server'),
            subtitle: const Text('Noch nicht verbunden'),
            trailing: const Icon(Icons.lock_outline_rounded),
          ),
        ),
        Card(
          elevation: 0,
          color: Colors.white,
          child: ListTile(
            leading: Icon(Icons.devices_outlined, color: colors.primary),
            title: const Text('Dieses Gerät'),
            subtitle: const Text('Pairing noch nicht verfügbar'),
            trailing: const Icon(Icons.info_outline_rounded),
          ),
        ),
        const SizedBox(height: 18),
        Text(
          'Kassensturz Mobile · Prototyp',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(color: colors.onSurfaceVariant),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
