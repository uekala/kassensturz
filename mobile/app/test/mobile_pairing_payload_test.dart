import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_pairing_payload.dart';

String secret(String character) => List<String>.filled(43, character).join();

void main() {
  test('parses a valid Kassensturz pairing invitation', () {
    final payload = MobilePairingPayload.fromRawValue(
      '{"type":"kassensturz-pairing","version":1,'
      '"server_url":"https://green.example.ts.net",'
      '"pairing_secret":"${secret('p')}"}',
    );

    expect(payload.serverUrl, 'https://green.example.ts.net');
    expect(payload.pairingSecret, secret('p'));
  });

  test('rejects another QR format', () {
    expect(
      () => MobilePairingPayload.fromRawValue('https://example.com'),
      throwsFormatException,
    );
    expect(
      () => MobilePairingPayload.fromRawValue('{"type":"other","version":1}'),
      throwsFormatException,
    );
  });

  test('rejects HTTP and QR payloads with short secrets', () {
    expect(
      () => MobilePairingPayload.fromRawValue(
        '{"type":"kassensturz-pairing","version":1,'
        '"server_url":"http://green.local",'
        '"pairing_secret":"${secret('p')}"}',
      ),
      throwsFormatException,
    );
    expect(
      () => MobilePairingPayload.fromRawValue(
        '{"type":"kassensturz-pairing","version":1,'
        '"server_url":"https://green.example.ts.net",'
        '"pairing_secret":"short"}',
      ),
      throwsFormatException,
    );
  });

  test('rejects URL paths, fragments and embedded credentials', () {
    for (final url in [
      'https://user:password@green.example.ts.net',
      'https://green.example.ts.net/api',
      'https://green.example.ts.net/#secret',
    ]) {
      expect(
        () => MobilePairingPayload.fromRawValue(
          '{"type":"kassensturz-pairing","version":1,'
          '"server_url":"$url","pairing_secret":"${secret('p')}"}',
        ),
        throwsFormatException,
      );
    }
  });
}
