import 'dart:typed_data';

import 'package:material_ui/material_ui.dart';
import 'package:pdfx/pdfx.dart';

/// Zeigt ein PDF mit dem Renderer des Handys. Die Datei bleibt im Arbeitsspeicher; sie
/// wird weder gespeichert noch an eine andere App übergeben.
class PdfBytesView extends StatefulWidget {
  const PdfBytesView({required this.bytes, required this.errorText, super.key});

  final Uint8List bytes;
  final String errorText;

  @override
  State<PdfBytesView> createState() => _PdfBytesViewState();
}

class _PdfBytesViewState extends State<PdfBytesView> {
  late final PdfControllerPinch _controller = PdfControllerPinch(
    document: PdfDocument.openData(widget.bytes),
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PdfViewPinch(
      controller: _controller,
      builders: PdfViewPinchBuilders<DefaultBuilderOptions>(
        options: const DefaultBuilderOptions(),
        documentLoaderBuilder: (_) =>
            const Center(child: CircularProgressIndicator()),
        pageLoaderBuilder: (_) =>
            const Center(child: CircularProgressIndicator()),
        errorBuilder: (_, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(widget.errorText, textAlign: TextAlign.center),
          ),
        ),
      ),
    );
  }
}
