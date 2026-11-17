import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/transactions/share_section.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'household.sharing'];

const _parts = [
  {'person_id': 1, 'name': 'Anna', 'cents': 1501},
  {'person_id': 2, 'name': 'Ben', 'cents': 1500},
];

/// A server that remembers whether transaction 4 is shared.
class _ShareServer {
  bool shared = false;

  late final transport = ScriptedTransport(_json);

  MobileHttpResponse _json(RecordedRequest request) {
    if (request.uri.path == '/api/v1/transactions/4/share') {
      if (request.method == 'PUT') shared = true;
      if (request.method == 'DELETE') shared = false;
      return jsonResponse(200, {
        'shareable': true,
        'shared': shared,
        'payer': 'Anna',
        'total_cents': 3001,
        'parts': shared ? _parts : const <Map<String, dynamic>>[],
      });
    }
    return serverAnswer(request, capabilities: _capabilities);
  }
}

void main() {
  test('an expense is shared and taken back through the controller', () async {
    final server = _ShareServer();
    final controller = MobileConnectionController(
      apiClient: MobileApiClient(
        sessionStore: await pairedStore(),
        transport: server.transport,
        refreshRetryDelay: Duration.zero,
      ),
      readRetryDelay: Duration.zero,
    );
    await controller.restore();
    expect(controller.canShareExpenses, isTrue);

    final before = await controller.loadShare(4);
    expect(before.error, isNull);
    expect(before.share?['shared'], isFalse);

    final after = await controller.setShare(4, shared: true);
    expect(after.error, isNull);
    expect(server.shared, isTrue);
    expect(shareSummary(after.share!), 'Anna 15,01 €, Ben 15,00 €');

    final undone = await controller.setShare(4, shared: false);
    expect(undone.share?['shared'], isFalse);
    expect(server.shared, isFalse);
    expect(shareSummary(undone.share!), '');
  });
}
