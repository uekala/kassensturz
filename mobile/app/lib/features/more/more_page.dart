import 'package:flutter/material.dart';

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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message.toString())),
      );
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
            _StatusCard(
              loading: state.isLoading,
              busy: state.isBusy,
              connected: connected,
              serverUrl: session?.serverUrl,
              deviceName: session?.deviceName,
              error: state.errorMessage,
              status: state.statusMessage,
              onCheck: connected && !state.isBusy
                  ? state.checkConnection
                  : null,
              onLogout: connected && !state.isBusy ? state.logout : null,
            ),
            if (!connected) ...[
              const SizedBox(height: 22),
              _sectionTitle(context, 'MIT DEINEM SERVER VERBINDEN'),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(17),
                decoration: _cardDecoration(colors),
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

  static BoxDecoration _cardDecoration(ColorScheme colors) => BoxDecoration(
    color: Colors.white,
    borderRadius: BorderRadius.circular(18),
    border: Border.all(color: colors.outlineVariant.withValues(alpha: 0.5)),
  );
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({
    required this.loading,
    required this.busy,
    required this.connected,
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
  final String? serverUrl;
  final String? deviceName;
  final String? error;
  final String? status;
  final Future<bool> Function()? onCheck;
  final Future<void> Function()? onLogout;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final background = connected
        ? const Color(0xFFE8F5EE)
        : const Color(0xFFFFF1D6);
    final foreground = connected
        ? const Color(0xFF22613D)
        : const Color(0xFF865B12);
    return Container(
      padding: const EdgeInsets.all(17),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: colors.outlineVariant.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                backgroundColor: background,
                child: Icon(
                  connected
                      ? Icons.cloud_done_outlined
                      : Icons.cloud_off_outlined,
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
                          : connected
                          ? 'Mit Kassensturz verbunden'
                          : 'Noch nicht verbunden',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      connected
                          ? (deviceName ?? 'Dieses Gerät')
                          : 'Dein eigener Kassensturz-Server',
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF65736F),
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                connected ? 'VERBUNDEN' : 'OFFLINE',
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
              style: const TextStyle(fontSize: 11, color: Color(0xFF65736F)),
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
                  label: const Text('Verbindung prüfen'),
                ),
                TextButton.icon(
                  onPressed: busy ? null : onLogout,
                  icon: const Icon(Icons.logout_rounded),
                  label: const Text('Abmelden'),
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
      ),
    );
  }
}
