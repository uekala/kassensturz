import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_error_messages.dart';

MobileApiException _api(int status, String code, [String message = 'x']) =>
    MobileApiException(statusCode: status, code: code, message: message);

void main() {
  test('each transport failure gets its own actionable sentence', () {
    final messages = {
      for (final failure in MobileNetworkFailure.values)
        failure: describeMobileError(
          MobileNetworkException(failure, requestSent: true),
        ),
    };

    expect(messages.values.toSet(), hasLength(4));
    expect(messages[MobileNetworkFailure.unreachable], contains('Tailscale'));
    expect(messages[MobileNetworkFailure.timeout], contains('rechtzeitig'));
    expect(messages[MobileNetworkFailure.certificate], contains('sichere'));
  });

  test('server refusals are explained by cause', () {
    expect(
      describeMobileError(_api(403, 'network_not_allowed')),
      contains('Tailscale'),
    );
    expect(describeMobileError(_api(426, 'https_required')), contains('HTTPS'));
    expect(describeMobileError(_api(429, 'rate_limited')), contains('warte'));
    expect(
      describeMobileError(_api(404, 'http_error')),
      contains('aktualisiere'),
    );
    expect(describeMobileError(_api(500, 'http_error')), contains('später'));
  });

  test('messages for rejected entries come from the server unchanged', () {
    const text = 'Auf Konten mit Bankabruf geht das nicht.';
    expect(describeMobileError(_api(409, 'account_not_manual', text)), text);
    expect(describeMobileError(_api(409, 'not_deletable', text)), text);
  });

  test('an ended session asks for pairing again', () {
    expect(
      describeMobileError(const MobileSessionExpiredException()),
      contains('kopple'),
    );
  });

  test('only transport failures count as missing connectivity', () {
    expect(
      isConnectivityFailure(
        const MobileNetworkException(
          MobileNetworkFailure.timeout,
          requestSent: true,
        ),
      ),
      isTrue,
    );
    expect(isConnectivityFailure(_api(500, 'http_error')), isFalse);
    expect(isConnectivityFailure(const FormatException('x')), isFalse);
  });
}
