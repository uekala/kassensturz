import 'package:flutter/material.dart';

class MorePage extends StatelessWidget {
  const MorePage({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(
          'Einstellungen',
          style: textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          'Deine Verbindung und Geräteverwaltung.',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(17),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: colors.outlineVariant.withValues(alpha: 0.5),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF1D6),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.cloud_off_outlined,
                      color: Color(0xFF865B12),
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Noch nicht verbunden',
                          style: TextStyle(fontWeight: FontWeight.w800),
                        ),
                        SizedBox(height: 3),
                        Text(
                          'Dein eigener Kassensturz-Server',
                          style: TextStyle(
                            fontSize: 11,
                            color: Color(0xFF65736F),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 5,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF1D6),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Text(
                      'OFFLINE',
                      style: TextStyle(
                        color: Color(0xFF865B12),
                        fontSize: 9,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              const Text(
                'Die sichere Serververbindung und das Geräte-Pairing werden mit dem Mobile-Backend aktiviert.',
                style: TextStyle(
                  fontSize: 12,
                  height: 1.45,
                  color: Color(0xFF65736F),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 22),
        Text(
          'VERBINDUNG',
          style: textTheme.labelSmall?.copyWith(
            color: colors.onSurfaceVariant,
            fontWeight: FontWeight.w800,
            letterSpacing: 1,
          ),
        ),
        const SizedBox(height: 7),
        const _SettingsTile(
          icon: Icons.dns_outlined,
          title: 'Serveradresse',
          subtitle: 'Wird beim Einrichten festgelegt',
        ),
        const _SettingsTile(
          icon: Icons.qr_code_scanner_rounded,
          title: 'Gerät koppeln',
          subtitle: 'Pairing noch nicht verfügbar',
        ),
        const SizedBox(height: 18),
        Text(
          'SICHERHEIT',
          style: textTheme.labelSmall?.copyWith(
            color: colors.onSurfaceVariant,
            fontWeight: FontWeight.w800,
            letterSpacing: 1,
          ),
        ),
        const SizedBox(height: 7),
        const _SettingsTile(
          icon: Icons.phonelink_lock_outlined,
          title: 'Geräteverwaltung',
          subtitle: 'Wird vom Server aus gesteuert',
        ),
        const _SettingsTile(
          icon: Icons.privacy_tip_outlined,
          title: 'Datenschutz',
          subtitle: 'Deine Finanzdaten bleiben auf deinem Server',
        ),
        const SizedBox(height: 22),
        Center(
          child: Text(
            'Kassensturz Mobile · UI-Prototyp',
            style: textTheme.labelSmall?.copyWith(
              color: colors.onSurfaceVariant,
            ),
          ),
        ),
      ],
    );
  }
}

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Container(
      margin: const EdgeInsets.only(bottom: 7),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
      ),
      child: ListTile(
        dense: true,
        leading: Icon(icon, color: colors.primary),
        title: Text(
          title,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
        ),
        subtitle: Text(subtitle, style: const TextStyle(fontSize: 11)),
        trailing: const Icon(Icons.chevron_right_rounded, size: 19),
      ),
    );
  }
}
