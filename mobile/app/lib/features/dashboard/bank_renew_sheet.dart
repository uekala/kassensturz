import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';

/// Opens the two steps that renew a bank consent: approve at the bank in the
/// browser, then hand the address of the page it ends on back to the server.
Future<void> showBankRenewSheet(
  BuildContext context, {
  required MobileConnectionController controller,
  required int id,
  required String name,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: BankRenewSheet(controller: controller, id: id, name: name),
  ),
);

class BankRenewSheet extends StatefulWidget {
  const BankRenewSheet({
    required this.controller,
    required this.id,
    required this.name,
    this.openUrl,
    super.key,
  });

  final MobileConnectionController controller;
  final int id;
  final String name;

  /// Opens the bank's page; replaced in tests.
  final Future<bool> Function(Uri url)? openUrl;

  @override
  State<BankRenewSheet> createState() => _BankRenewSheetState();
}

class _BankRenewSheetState extends State<BankRenewSheet> {
  final _address = TextEditingController();
  bool _busy = false;
  bool _opened = false;
  String? _error;

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
  }

  Future<void> _open() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final started = await widget.controller.startBankRenewal(widget.id);
    if (!mounted) return;
    var opened = false;
    final url = started.url;
    if (url != null) {
      try {
        final open =
            widget.openUrl ??
            (Uri uri) => launchUrl(uri, mode: LaunchMode.externalApplication);
        opened = await open(Uri.parse(url));
      } on Object {
        opened = false;
      }
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _opened = opened;
      _error =
          started.error ??
          (opened ? null : 'Die Seite der Bank ließ sich nicht öffnen.');
    });
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim() ?? '';
    if (text.isNotEmpty) setState(() => _address.text = text);
  }

  Future<void> _finish() async {
    final address = _address.text.trim();
    if (address.isEmpty) {
      setState(() => _error = 'Füge die Adresse der letzten Seite ein.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.maybeOf(context);
    final error = await widget.controller.completeBankRenewal(address);
    if (!mounted) return;
    if (error != null) {
      setState(() {
        _busy = false;
        _error = error;
      });
      return;
    }
    navigator.pop();
    messenger
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text('Freigabe für ${widget.name} erneuert.')),
      );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final klar = KlarColors.of(context);
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Freigabe erneuern', style: textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(widget.name, style: textTheme.bodyMedium),
            const SizedBox(height: 16),
            Text('1. Bei der Bank freigeben', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'Die Seite der Bank öffnet sich im Browser. Melde dich dort an '
              'und gib die Konten frei.',
              style: textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _busy ? null : _open,
              icon: const Icon(Icons.open_in_new_rounded, size: 18),
              label: Text(_opened ? 'Noch einmal öffnen' : 'Bank öffnen'),
            ),
            const SizedBox(height: 18),
            Text('2. Adresse einfügen', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'Nach der Freigabe landest du auf einer Seite von Enable '
              'Banking. Kopiere ihre Adresse aus der Adresszeile und füge sie '
              'hier ein.',
              style: textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _address,
              enabled: !_busy,
              keyboardType: TextInputType.url,
              autocorrect: false,
              minLines: 1,
              maxLines: 3,
              decoration: InputDecoration(
                labelText: 'Adresse der letzten Seite',
                suffixIcon: IconButton(
                  tooltip: 'Einfügen',
                  onPressed: _busy ? null : _paste,
                  icon: const Icon(Icons.content_paste_rounded),
                ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _busy ? null : _finish,
                child: Text(_busy ? 'Einen Moment …' : 'Freigabe abschließen'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
