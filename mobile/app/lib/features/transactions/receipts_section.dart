import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// A photo chosen for upload. It lives in memory until the server has it.
class PickedReceipt {
  const PickedReceipt({required this.name, required this.bytes});

  final String name;
  final Uint8List bytes;
}

typedef ReceiptPicker = Future<PickedReceipt?> Function({required bool camera});

/// Takes a photo or opens the gallery. Large photos are scaled down so a
/// receipt stays readable without sending the full camera resolution.
Future<PickedReceipt?> pickReceiptPhoto({required bool camera}) async {
  final file = await ImagePicker().pickImage(
    source: camera ? ImageSource.camera : ImageSource.gallery,
    maxWidth: 2200,
    maxHeight: 2200,
    imageQuality: 82,
  );
  if (file == null) return null;
  return PickedReceipt(name: file.name, bytes: await file.readAsBytes());
}

/// Receipts of one transaction: list, add from camera or gallery, remove.
/// Every change is sent to the server right away.
class ReceiptsSection extends StatefulWidget {
  const ReceiptsSection({
    required this.controller,
    required this.transactionId,
    this.picker = pickReceiptPhoto,
    super.key,
  });

  final MobileConnectionController controller;
  final int transactionId;
  final ReceiptPicker picker;

  @override
  State<ReceiptsSection> createState() => _ReceiptsSectionState();
}

class _ReceiptsSectionState extends State<ReceiptsSection> {
  List<ServerReceipt> _items = const [];
  int _max = 10;
  bool _loading = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.loadReceipts(widget.transactionId);
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (result.error == null) {
        _items = result.items;
        _max = result.max;
      } else {
        _error = result.error;
      }
    });
  }

  Future<void> _add({required bool camera}) async {
    if (_busy) return;
    PickedReceipt? picked;
    try {
      picked = await widget.picker(camera: camera);
    } on Object {
      if (!mounted) return;
      setState(() {
        _error = camera
            ? 'Die Kamera ließ sich nicht öffnen.'
            : 'Die Galerie ließ sich nicht öffnen.';
      });
      return;
    }
    if (picked == null || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final failure = await widget.controller.addReceipt(
      widget.transactionId,
      picked.name,
      picked.bytes,
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = failure;
    });
    if (failure == null) await _load();
  }

  Future<void> _remove(ServerReceipt receipt) async {
    if (_busy) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Beleg entfernen?'),
        content: Text('„${receipt.filename}“ wird auf dem Server gelöscht.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Entfernen'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final failure = await widget.controller.deleteReceipt(receipt.id);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = failure;
    });
    if (failure == null) await _load();
  }

  void _open(ServerReceipt receipt) {
    if (!receipt.isImage) {
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        const SnackBar(
          content: Text(
            'PDF zeigt die App noch nicht an. Öffne die Buchung dafür in '
            'Kassensturz in Home Assistant.',
          ),
        ),
      );
      return;
    }
    Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) =>
            _ReceiptViewPage(controller: widget.controller, receipt: receipt),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final full = _items.length >= _max;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Belege', style: textTheme.labelMedium),
        const SizedBox(height: 6),
        if (_loading)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 10),
            child: SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          )
        else ...[
          if (_items.isEmpty && _error == null)
            Text(
              'Noch kein Beleg. Fotografiere die Rechnung oder wähle ein '
              'Foto aus.',
              style: textTheme.bodyMedium,
            ),
          for (final receipt in _items)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Material(
                color: klar.surface,
                clipBehavior: Clip.antiAlias,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(color: klar.border, width: 1.5),
                ),
                child: ListTile(
                  contentPadding: const EdgeInsets.only(left: 14, right: 4),
                  leading: Icon(
                    receipt.isImage
                        ? Icons.image_outlined
                        : Icons.picture_as_pdf_outlined,
                    color: klar.brand,
                  ),
                  title: Text(
                    receipt.filename,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(receipt.sizeLabel),
                  onTap: () => _open(receipt),
                  trailing: IconButton(
                    tooltip: 'Beleg entfernen',
                    onPressed: _busy ? null : () => _remove(receipt),
                    icon: const Icon(Icons.delete_outline_rounded),
                  ),
                ),
              ),
            ),
          if (_error != null) ...[
            const SizedBox(height: 6),
            Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
          ],
          const SizedBox(height: 8),
          if (_busy)
            Row(
              children: [
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 10),
                Text('Wird übertragen …', style: textTheme.bodyMedium),
              ],
            )
          else if (full)
            Text(
              'Mehr als $_max Belege je Buchung gehen nicht.',
              style: textTheme.bodyMedium,
            )
          else
            Wrap(
              spacing: 10,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: () => _add(camera: true),
                  icon: const Icon(Icons.photo_camera_outlined, size: 18),
                  label: const Text('Foto aufnehmen'),
                ),
                OutlinedButton.icon(
                  onPressed: () => _add(camera: false),
                  icon: const Icon(Icons.photo_library_outlined, size: 18),
                  label: const Text('Aus Galerie'),
                ),
              ],
            ),
        ],
      ],
    );
  }
}

class _ReceiptViewPage extends StatefulWidget {
  const _ReceiptViewPage({required this.controller, required this.receipt});

  final MobileConnectionController controller;
  final ServerReceipt receipt;

  @override
  State<_ReceiptViewPage> createState() => _ReceiptViewPageState();
}

class _ReceiptViewPageState extends State<_ReceiptViewPage> {
  late final Future<({Uint8List? bytes, String? error})> _file = widget
      .controller
      .receiptBytes(widget.receipt.id);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.receipt.filename)),
      body: FutureBuilder(
        future: _file,
        builder: (context, snapshot) {
          final data = snapshot.data;
          if (data == null) {
            return const Center(child: CircularProgressIndicator());
          }
          final bytes = data.bytes;
          if (bytes == null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  data.error ?? 'Der Beleg ließ sich nicht laden.',
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          return InteractiveViewer(
            maxScale: 6,
            child: Center(
              child: Image.memory(
                bytes,
                errorBuilder: (_, _, _) => const Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('Das Bild ließ sich nicht anzeigen.'),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
