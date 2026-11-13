import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/accounts/cash_account_dialog.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'accounts.write'];

Future<MobileConnectionController> _controller(
  ScriptedTransport transport,
) async {
  final controller = MobileConnectionController(
    apiClient: MobileApiClient(
      sessionStore: await pairedStore(),
      transport: transport,
      refreshRetryDelay: Duration.zero,
    ),
    readRetryDelay: Duration.zero,
  );
  await controller.restore();
  return controller;
}

Future<bool?> _openDialog(
  WidgetTester tester,
  MobileConnectionController controller,
) async {
  bool? result;
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () async {
              result = await showCashAccountDialog(context, controller);
            },
            child: const Text('öffnen'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('öffnen'));
  await tester.pumpAndSettle();
  expect(find.text('Konto für Bargeld anlegen'), findsOneWidget);
  return result;
}

void main() {
  testWidgets('a cash account is created with name and balance', (
    tester,
  ) async {
    final transport = ScriptedTransport((request) {
      if (request.method == 'POST' && request.uri.path == '/api/v1/accounts') {
        return jsonResponse(201, {
          'account': {'id': 9, 'name': 'Geldbeutel'},
        });
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    expect(controller.canCreateAccounts, isTrue);

    await _openDialog(tester, controller);
    await tester.enterText(find.byType(TextField).first, 'Geldbeutel');
    await tester.enterText(find.byType(TextField).last, '12,50');
    await tester.tap(find.text('Anlegen'));
    await tester.pumpAndSettle();

    final post = transport.requests.lastWhere(
      (request) =>
          request.method == 'POST' && request.uri.path == '/api/v1/accounts',
    );
    expect(jsonDecode(post.body!), {
      'name': 'Geldbeutel',
      'balance_cents': 1250,
    });
    expect(find.text('Konto für Bargeld anlegen'), findsNothing);
  });

  testWidgets('wrong input and a refusal of the server are shown', (
    tester,
  ) async {
    final transport = ScriptedTransport((request) {
      if (request.method == 'POST' && request.uri.path == '/api/v1/accounts') {
        return jsonResponse(409, {
          'error': {
            'code': 'duplicate',
            'message': 'Ein Konto mit diesem Namen gibt es schon.',
          },
        });
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);

    await _openDialog(tester, controller);
    await tester.enterText(find.byType(TextField).last, 'viel');
    await tester.tap(find.text('Anlegen'));
    await tester.pumpAndSettle();
    expect(find.text('Der Bestand ist kein gültiger Betrag.'), findsOneWidget);
    expect(transport.requests.where((r) => r.method == 'POST'), isEmpty);

    await tester.enterText(find.byType(TextField).last, '');
    await tester.tap(find.text('Anlegen'));
    await tester.pumpAndSettle();
    final post = transport.requests.lastWhere((r) => r.method == 'POST');
    expect(jsonDecode(post.body!), {'name': 'Bargeld'});
    expect(
      find.text('Ein Konto mit diesem Namen gibt es schon.'),
      findsOneWidget,
    );
  });
}
