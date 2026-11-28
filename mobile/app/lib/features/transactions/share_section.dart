import 'package:material_ui/material_ui.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';

/// Teilt eine vom eigenen Konto der Person bezahlte Ausgabe mit dem Haushalt:
/// Die anderen schulden dem Zahler dann ihren Teil. Zeigt nichts bei Umsätzen,
/// die sich nicht teilen lassen.
class ShareSection extends StatefulWidget {
  const ShareSection({
    required this.controller,
    required this.transactionId,
    super.key,
  });

  final MobileConnectionController controller;
  final int transactionId;

  @override
  State<ShareSection> createState() => _ShareSectionState();
}

class _ShareSectionState extends State<ShareSection> {
  Map<String, dynamic>? _share;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.loadShare(widget.transactionId);
    if (!mounted) return;
    setState(() {
      _share = result.share;
    });
  }

  Future<void> _change(bool shared) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final result = await widget.controller.setShare(
      widget.transactionId,
      shared: shared,
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = result.error;
      _share = result.share ?? _share;
    });
  }

  @override
  Widget build(BuildContext context) {
    final share = _share;
    if (share == null || share['shareable'] != true) {
      return const SizedBox.shrink();
    }
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final shared = share['shared'] == true;
    final text = shared
        ? 'Geteilt: ${shareSummary(share)}.'
        : 'Teilst du die Ausgabe, schulden die anderen dir ihren Anteil.';
    final label = shared ? 'Nicht mehr teilen' : 'Mit dem Haushalt teilen';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Haushalt', style: textTheme.labelMedium),
        const SizedBox(height: 6),
        Text(text, style: textTheme.bodyMedium),
        const SizedBox(height: 8),
        OutlinedButton(
          onPressed: _busy ? null : () => _change(!shared),
          child: Text(label),
        ),
        if (_error != null) ...[
          const SizedBox(height: 8),
          Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
        ],
      ],
    );
  }
}

/// Wer welchen Teil einer geteilten Ausgabe trägt, als eine Zeile.
String shareSummary(Map<String, dynamic> share) {
  final parts = share['parts'];
  if (parts is! List) return '';
  return parts.whereType<Map<dynamic, dynamic>>().map(_partLabel).join(', ');
}

String _partLabel(Map<dynamic, dynamic> part) {
  final cents = part['cents'];
  final amount = formatEuro((cents is int ? cents : 0) / 100);
  return '${part['name']} $amount';
}
