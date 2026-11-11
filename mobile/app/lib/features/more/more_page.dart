import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_pairing_payload.dart';
import 'pairing_scanner_page.dart';

class MorePage extends StatefulWidget {
  const MorePage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<MorePage> createState() => _MorePageState();
}

class _MorePageState extends State<MorePage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _server;
  late final TextEditingController _secret;
  late final TextEditingController _device;

  @override
  void initState() {
    super.initState();
    _server = TextEditingController();
    _secret = TextEditingController();
    _device = TextEditingController(text: 'Dieses Gerät');
  }

  @override
  void dispose() {
    _server.dispose();
    _secret.dispose();
    _device.dispose();
    super.dispose();
  }

  Future<void> _checkServer() async {
    await widget.controller.checkServer(_server.text);
  }

  Future<void> _scanPairingCode() async {
    final rawValue = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const PairingScannerPage()),
    );
    if (!mounted || rawValue == null) return;

    try {
      final payload = MobilePairingPayload.fromRawValue(rawValue);
      _server.text = payload.serverUrl;
      _secret.text = payload.pairingSecret;
      FocusScope.of(context).unfocus();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Pairing-Code gelesen. Prüfe die Serveradresse und kopple das Gerät.',
          ),
        ),
      );
    } on FormatException catch (error) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.message.toString())));
    }
  }

  Future<void> _pair() async {
    if (!_formKey.currentState!.validate()) return;
    final result = await widget.controller.pair(
      serverUrl: _server.text,
      pairingSecret: _secret.text,
      deviceName: _device.text,
    );
    if (result && mounted) {
      _secret.clear();
      FocusScope.of(context).unfocus();
    }
  }

  Future<void> _disconnect() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Verbindung trennen?'),
        content: const Text(
          'Dieses Gerät wird am Server abgemeldet. Deine Daten bleiben auf '
          'dem Server. Zum erneuten Verbinden brauchst du einen neuen '
          'QR-Code aus Kassensturz.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Trennen'),
          ),
        ],
      ),
    );
    if (confirmed == true) await widget.controller.logout();
  }

  static String _formatSync(DateTime? value) {
    if (value == null) return 'Noch nicht synchronisiert';
    final local = value.toLocal();
    final day = local.day.toString().padLeft(2, '0');
    final month = local.month.toString().padLeft(2, '0');
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return '$day.$month.${local.year}, $hour:$minute Uhr';
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final state = widget.controller;
        final session = state.session;
        final connected = state.isConnected;
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          children: [
            _StatusCard(
              loading: state.isLoading,
              busy: state.isBusy,
              connected: connected,
              unreachable: state.linkState == ServerLinkState.unreachable,
              serverUrl: session?.serverUrl,
              deviceName: session?.deviceName,
              error: state.errorMessage,
              status: state.statusMessage,
              onCheck: connected && !state.isBusy
                  ? state.checkConnection
                  : null,
              onLogout: connected && !state.isBusy ? _disconnect : null,
            ),
            if (!connected) ...[
              const SizedBox(height: 22),
              _sectionTitle(context, 'MIT DEINEM SERVER VERBINDEN'),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(17),
                decoration: _cardDecoration(KlarColors.of(context)),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _fieldLabel('Serveradresse'),
                      TextFormField(
                        controller: _server,
                        keyboardType: TextInputType.url,
                        textInputAction: TextInputAction.next,
                        autocorrect: false,
                        enableSuggestions: false,
                        decoration: const InputDecoration(
                          hintText: 'https://dein-server.ts.net',
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        validator: (value) {
                          final uri = Uri.tryParse((value ?? '').trim());
                          if (uri == null ||
                              uri.scheme != 'https' ||
                              uri.host.isEmpty ||
                              uri.userInfo.isNotEmpty ||
                              uri.hasQuery ||
                              uri.hasFragment ||
                              (uri.path.isNotEmpty && uri.path != '/')) {
                            return 'Bitte eine gültige HTTPS-Adresse eingeben.';
                          }
                          return null;
                        },
                      ),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: OutlinedButton.icon(
                          onPressed: state.isBusy ? null : _checkServer,
                          icon: const Icon(Icons.wifi_tethering_rounded),
                          label: const Text('Server prüfen'),
                        ),
                      ),
                      const SizedBox(height: 14),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: OutlinedButton.icon(
                          onPressed: state.isBusy ? null : _scanPairingCode,
                          icon: const Icon(Icons.qr_code_scanner_rounded),
                          label: const Text('QR-Code scannen'),
                        ),
                      ),
                      const SizedBox(height: 6),
                      _fieldLabel('Einmaliger Pairing-Code'),
                      TextFormField(
                        controller: _secret,
                        textInputAction: TextInputAction.next,
                        autocorrect: false,
                        enableSuggestions: false,
                        decoration: const InputDecoration(
                          hintText: 'Code aus Kassensturz einfügen',
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        validator: (value) {
                          final length = (value ?? '').trim().length;
                          return length >= 43 && length <= 128
                              ? null
                              : 'Der Pairing-Code ist ungültig.';
                        },
                      ),
                      const SizedBox(height: 14),
                      _fieldLabel('Gerätename'),
                      TextFormField(
                        controller: _device,
                        textInputAction: TextInputAction.done,
                        decoration: const InputDecoration(
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        validator: (value) {
                          final name = (value ?? '').trim();
                          return name.isNotEmpty && name.length <= 64
                              ? null
                              : 'Bitte maximal 64 Zeichen eingeben.';
                        },
                        onFieldSubmitted: (_) {
                          if (!state.isBusy) _pair();
                        },
                      ),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        onPressed: state.isBusy ? null : _pair,
                        icon: const Icon(Icons.link_rounded),
                        label: const Text('Gerät sicher koppeln'),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'Den Einmal-Code erzeugst du in Kassensturz unter Einstellungen → Mobile Geräte. Er ist fünf Minuten gültig und kann nur einmal verwendet werden.',
                        style: TextStyle(
                          fontSize: 11,
                          height: 1.45,
                          color: colors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ] else ...[
              const SizedBox(height: 22),
              _sectionTitle(context, 'VERBINDUNG'),
              const SizedBox(height: 8),
              _InfoTile(
                icon: Icons.dns_outlined,
                title: 'Serveradresse',
                subtitle: session!.serverUrl,
              ),
              _InfoTile(
                icon: Icons.phonelink_lock_outlined,
                title: 'Gekoppeltes Gerät',
                subtitle: session.deviceName,
              ),
              _InfoTile(
                icon: Icons.sync_rounded,
                title: 'Letzte erfolgreiche Synchronisierung',
                subtitle: _formatSync(state.lastSyncAt),
              ),
              if (state.serverNeedsUpdate)
                const _InfoTile(
                  icon: Icons.system_update_alt_rounded,
                  title: 'Server aktualisieren',
                  subtitle:
                      'Dieser Server kann noch keine Umsätze speichern. '
                      'Aktualisiere Kassensturz in Home Assistant.',
                ),
              const SizedBox(height: 18),
              _sectionTitle(context, 'SICHERHEIT'),
              const SizedBox(height: 8),
              const _InfoTile(
                icon: Icons.privacy_tip_outlined,
                title: 'Datenschutz',
                subtitle: 'Deine Finanzdaten bleiben auf deinem Server',
              ),
            ],
            const SizedBox(height: 22),
            Center(
              child: Text(
                'Kassensturz Mobile · lokale Verbindung',
                style: textTheme.labelSmall?.copyWith(
                  color: colors.onSurfaceVariant,
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  static Widget _sectionTitle(BuildContext context, String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.labelSmall?.copyWith(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontWeight: FontWeight.w800,
        letterSpacing: 1,
      ),
    );
  }

  static Widget _fieldLabel(String value) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text(
      value,
      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
    ),
  );

  static BoxDecoration _cardDecoration(KlarColors klar) => BoxDecoration(
    color: klar.surface,
    borderRadius: BorderRadius.circular(20),
    border: Border.all(color: klar.ink, width: 1.5),
  );
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({
    required this.loading,
    required this.busy,
    required this.connected,
    required this.unreachable,
    required this.serverUrl,
    required this.deviceName,
    required this.error,
    required this.status,
    required this.onCheck,
    required this.onLogout,
  });

  final bool loading;
  final bool busy;
  final bool connected;
  final bool unreachable;
  final String? serverUrl;
  final String? deviceName;
  final String? error;
  final String? status;
  final Future<bool> Function()? onCheck;
  final Future<void> Function()? onLogout;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final colors = Theme.of(context).colorScheme;
    final online = connected && !unreachable;
    final background = online ? klar.softBrand : klar.softWarn;
    final foreground = online ? klar.brand : klar.warn;
    return Container(
      padding: const EdgeInsets.all(17),
      decoration: BoxDecoration(
        color: klar.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: klar.ink, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                backgroundColor: background,
                child: Icon(
                  online ? Icons.cloud_done_outlined : Icons.cloud_off_outlined,
                  color: foreground,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      loading
                          ? 'Sitzung wird geladen'
                          : online
                          ? 'Mit Kassensturz verbunden'
                          : connected
                          ? 'Server nicht erreichbar'
                          : 'Noch nicht verbunden',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      connected
                          ? (deviceName ?? 'Dieses Gerät')
                          : 'Dein eigener Kassensturz-Server',
                      style: TextStyle(fontSize: 12, color: klar.mutedInk),
                    ),
                  ],
                ),
              ),
              Text(
                online
                    ? 'VERBUNDEN'
                    : connected
                    ? 'NICHT ERREICHBAR'
                    : 'OFFLINE',
                style: TextStyle(
                  color: foreground,
                  fontSize: 9,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          if (serverUrl != null) ...[
            const SizedBox(height: 10),
            SelectableText(
              serverUrl!,
              style: TextStyle(fontSize: 12, color: klar.mutedInk),
            ),
          ],
          if (error != null) ...[
            const SizedBox(height: 10),
            Text(error!, style: TextStyle(color: colors.error, fontSize: 12)),
          ],
          if (status != null) ...[
            const SizedBox(height: 10),
            Text(
              status!,
              style: TextStyle(color: colors.primary, fontSize: 12),
            ),
          ],
          if (connected) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: busy ? null : onCheck,
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Verbindung testen'),
                ),
                TextButton.icon(
                  onPressed: busy ? null : onLogout,
                  style: TextButton.styleFrom(foregroundColor: klar.warn),
                  icon: const Icon(Icons.link_off_rounded),
                  label: const Text('Trennen'),
                ),
              ],
            ),
          ],
          if (busy) ...[
            const SizedBox(height: 10),
            const LinearProgressIndicator(),
          ],
        ],
      ),
    );
  }
}

class _InfoTile extends StatelessWidget {
  const _InfoTile({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final colors = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 7),
      decoration: BoxDecoration(
        color: klar.surface,
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
      ),
    );
  }
}
