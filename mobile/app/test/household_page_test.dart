import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/more/household_page.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'household.sharing'];
const _budgetCapabilities = [...fullCapabilities, 'budgets.own'];

const _sharing = <String, dynamic>{
  'open': [
    {'person': 'Anna', 'cents': -1500},
  ],
  'items': [
    {
      'tx_id': 4,
      'label': 'Kino',
      'payer': 'Anna',
      'booking_date': '2026-11-09',
      'total_cents': 3000,
    },
  ],
  'settlements': <Map<String, dynamic>>[],
  'persons': [
    {'id': 1, 'name': 'Anna'},
    {'id': 2, 'name': 'Ben'},
  ],
};

void main() {
  test('household lines name who owes whom and who else there is', () {
    expect(openTitle({'person': 'Anna', 'cents': -1500}), 'Du schuldest Anna');
    expect(openTitle({'person': 'Anna', 'cents': 1500}), 'Anna schuldet dir');
    expect(paymentTitle({'from': 'Ben', 'to': 'Anna'}), 'Ben an Anna');
    expect(householdOthers(_sharing, 2), [(id: 1, name: 'Anna')]);
    expect(householdOthers(_sharing, null).length, 2);
    expect(householdOthers(const {}, 2), isEmpty);
    expect(
      householdPersonId({
        'household': {
          'person': {'id': 2, 'name': 'Ben'},
        },
      }),
      2,
    );
    expect(householdPersonId({'household': <String, dynamic>{}}), isNull);
    expect(householdPersonId(null), isNull);
  });

  test('sharing is loaded and a payment is sent to the server', () async {
    Map<String, dynamic>? sent;
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/household/sharing') {
        return jsonResponse(200, _sharing);
      }
      if (request.uri.path == '/api/v1/household/settlements') {
        sent = jsonDecode(request.body!) as Map<String, dynamic>;
        return jsonResponse(201, {'settlement': sent});
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = MobileConnectionController(
      apiClient: MobileApiClient(
        sessionStore: await pairedStore(),
        transport: transport,
        refreshRetryDelay: Duration.zero,
      ),
      readRetryDelay: Duration.zero,
    );
    await controller.restore();

    final loaded = await controller.loadSharing();
    expect(loaded.error, isNull);
    expect(householdOthers(loaded.data!, 2).single.name, 'Anna');

    expect(await controller.addSettlement(1, 1500, 'Kino'), isNull);
    expect(sent, {'to_person_id': 1, 'cents': 1500, 'note': 'Kino'});
    expect(await controller.addSettlement(0, 1500, ''), isNotNull);
  });

  test('a child phone is read-only and asks for no server update', () async {
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/me') {
        return jsonResponse(200, {
          'device': {'id': 'device-1', 'name': 'Testgerät'},
          'server': {'name': 'Kassensturz', 'version': '0.3.37'},
          'capabilities': ['overview', 'transactions', 'accounts'],
          'household': {'read_only': true},
        });
      }
      return serverAnswer(request);
    });
    final controller = MobileConnectionController(
      apiClient: MobileApiClient(
        sessionStore: await pairedStore(),
        transport: transport,
        refreshRetryDelay: Duration.zero,
      ),
      readRetryDelay: Duration.zero,
    );
    await controller.restore();
    expect(controller.isReadOnly, isTrue);
    expect(controller.canWriteTransactions, isFalse);
    expect(controller.serverNeedsUpdate, isFalse);
  });

  test('an own budget is saved under its own address', () async {
    final paths = <String>[];
    final transport = ScriptedTransport((request) {
      if (request.method == 'PUT') {
        paths.add(request.uri.path);
        return jsonResponse(200, {'budget': <String, dynamic>{}});
      }
      return serverAnswer(request, capabilities: _budgetCapabilities);
    });
    final controller = MobileConnectionController(
      apiClient: MobileApiClient(
        sessionStore: await pairedStore(),
        transport: transport,
        refreshRetryDelay: Duration.zero,
      ),
      readRetryDelay: Duration.zero,
    );
    await controller.restore();
    expect(controller.canEditOwnBudgets, isTrue);

    expect(await controller.setBudget(6, 2000, own: true), isNull);
    expect(await controller.setBudget(6, 2000), isNull);
    expect(paths, ['/api/v1/budgets/own/6', '/api/v1/budgets/6']);
  });
}
