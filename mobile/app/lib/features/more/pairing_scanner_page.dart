import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/networking/mobile_pairing_payload.dart';

class PairingScannerPage extends StatefulWidget {
  const PairingScannerPage({super.key});

  @override
  State<PairingScannerPage> createState() => _PairingScannerPageState();
}

class _PairingScannerPageState extends State<PairingScannerPage> {
  late final MobileScannerController _scannerController;
  bool _handled = false;
  String? _scanError;

  @override
  void initState() {
    super.initState();
    _scannerController = MobileScannerController(
      detectionSpeed: DetectionSpeed.noDuplicates,
      formats: const [BarcodeFormat.qrCode],
    );
  }

  void _handleDetection(BarcodeCapture capture) {
    if (_handled) return;
    for (final barcode in capture.barcodes) {
      final rawValue = barcode.rawValue;
      if (rawValue == null || rawValue.isEmpty) continue;

      try {
        MobilePairingPayload.fromRawValue(rawValue);
        _handled = true;
        Navigator.of(context).pop(rawValue);
      } on FormatException catch (error) {
        if (mounted && _scanError != error.message) {
          setState(() => _scanError = error.message.toString());
        }
      }
      return;
    }
  }

  @override
  void dispose() {
    unawaited(_scannerController.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Pairing-QR-Code scannen')),
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(
            controller: _scannerController,
            onDetect: _handleDetection,
            errorBuilder: (context, error) {
              final message = switch (error.errorCode) {
                MobileScannerErrorCode.permissionDenied => 'Kassensturz benötigt Kamerazugriff. Erlaube die Kamera-Berechtigung in den App-Einstellungen oder nutze die manuelle Code-Eingabe.',
                MobileScannerErrorCode.unsupported => 'Auf diesem Gerät ist keine unterstützte Kamera verfügbar. Nutze die manuelle Code-Eingabe.',
                _ => 'Die Kamera konnte nicht gestartet werden. Prüfe die Berechtigung und versuche es erneut.',
              };
              return ColoredBox(
                color: Colors.black,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      message,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white),
                    ),
                  ),
                ),
              );
            },
          ),
          IgnorePointer(
            child: Center(
              child: Container(
                width: 260,
                height: 260,
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.white, width: 3),
                  borderRadius: BorderRadius.circular(24),
                ),
              ),
            ),
          ),
          Positioned(
            left: 20,
            right: 20,
            bottom: 28,
            child: SafeArea(
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.72),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      'Richte die Kamera auf den QR-Code in den Kassensturz-Einstellungen.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white),
                    ),
                    if (_scanError != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        _scanError!,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: colors.errorContainer),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
