import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/core/widgets/part_filter.dart';
import 'package:kassensturz_mobile/features/accounts/server_finance_pages.dart';
import 'package:kassensturz_mobile/features/more/household_page.dart';

import 'support/fake_server.dart';

const _adult = [
  ...fullCapabilities,
  'household',
  'household.sharing',
  'parts',
  'accounts.value',
];

Map<String, dynamic> _overview({bool child = false, bool split = true}) => {
  'as_of': '2026-11-10T12:00:00+00:00',
  'accounts': [
    {
      'id': 3,
      'name': 'Erfundenes Depot',
      'type': 'depot',
      'balance_cents': 1500000,
      'balance_known': true,
      'group': 'depots',
      'ownership': 'mine',
      'value_editable': true,
    },
    {
      'id': 2,
      'name': 'Erfundenes Giro',
      'type': 'giro',
      'balance_cents': 120000,
      'balance_known': true,
      'group': 'alltag',
      'ownership': 'shared',
      'value_editable': false,
    },
  ],
  'budgets': <Object>[],
  'alerts': <Object>[],
  'forecast': <String, Object>{},
  'month': <String, Object>{},
  'household': {
    'person': {'id': 1, 'name': 'Anna'},
    'private_accounts': split,
    'read_only': child,
  },
};

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

ScriptedTransport _server({
  List<String> capabilities = _adult,
  bool child = false,
  bool split = true,
  void Function(RecordedRequest request)? onRequest,
}) => ScriptedTransport((request) {
  onRequest?.call(request);
  final path = request.uri.path;
  if (path == '/api/v1/overview') {
    return jsonResponse(200, _overview(child: child, split: split));
  }
  if (path == '/api/v1/me' && child) {
    // Der Server teilt dem Handy eines Kindes in seiner Identität mit, dass es nur liest.
    return jsonResponse(200, {
      'device': {'id': 'device-1', 'name': 'Testgerät'},
      'server': {'name': 'Kassensturz', 'version': '0.3.57'},
      'capabilities': ['overview', 'transactions', 'accounts', 'household'],
      'household': {
        'person': {'id': 1, 'name': 'Anna'},
        'read_only': true,
      },
    });
  }
  if (request.method == 'PUT' && path == '/api/v1/accounts/3/value') {
    return jsonResponse(200, {'account': <String, Object>{}});
  }
  if (path == '/api/v1/household/sharing') {
    return jsonResponse(200, {
      'open': [
        {'person': 'Ben', 'cents': -1500},
      ],
      'items': <Object>[],
      'settlements': <Object>[],
      'persons': [
        {'id': 1, 'name': 'Anna'},
        {'id': 2, 'name': 'Ben'},
      ],
    });
  }
  return serverAnswer(request, capabilities: capabilities);
});

Future<void> _pump(WidgetTester tester, Widget Function() page) async {
  tester.view.physicalSize = const Size(900, 3200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(body: page()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test('the split into own and shared needs a household of adults', () async {
    final yes = await _controller(_server());
    expect(yes.canFilterParts, isTrue);
    final oldServer = await _controller(
      _server(capabilities: [...fullCapabilities, 'household']),
    );
    expect(oldServer.canFilterParts, isFalse);
    final noPrivate = await _controller(_server(split: false));
    expect(noPrivate.canFilterParts, isFalse);
    final child = await _controller(_server(child: true));
    expect(child.isReadOnly, isTrue);
    expect(child.canFilterParts, isFalse);
    expect(child.canEditAccountValues, isFalse);
    for (final controller in [yes, oldServer, noPrivate, child]) {
      controller.dispose();
    }
  });

  testWidgets('choosing "Ich" asks the server for the own part only', (
    tester,
  ) async {
    final parts = <String?>[];
    final transport = _server(
      onRequest: (request) {
        if (request.uri.path == '/api/v1/transactions' &&
            request.method == 'GET') {
          parts.add(request.uri.queryParameters['part']);
        }
      },
    );
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    await _pump(
      tester,
      () => AnimatedBuilder(
        animation: controller,
        builder: (_, _) => PartFilter(controller: controller),
      ),
    );
    parts.clear();

    await tester.tap(find.text('Ich'));
    await tester.pumpAndSettle();
    expect(controller.viewPart, 'own');
    expect(parts, ['own']);

    await tester.tap(find.text('Gemeinsam'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Alle'));
    await tester.pumpAndSettle();
    expect(controller.viewPart, isNull);
    expect(parts, ['own', 'shared', null]);
  });

  testWidgets('accounts say whose they are and take a new value', (
    tester,
  ) async {
    Map<String, dynamic>? sent;
    final transport = _server(
      onRequest: (request) {
        if (request.method == 'PUT') {
          sent = jsonDecode(request.body!) as Map<String, dynamic>;
        }
      },
    );
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    await _pump(
      tester,
      () => AnimatedBuilder(
        animation: controller,
        builder: (_, _) => ServerAccountsPage(controller: controller),
      ),
    );

    expect(find.text('Vermögen'), findsOneWidget);
    expect(find.textContaining('nur für dich'), findsOneWidget);
    expect(find.textContaining('gemeinsam'), findsWidgets);

    // Ein Konto mit Bankanbindung hat nichts zu öffnen.
    await tester.tap(find.text('Erfundenes Giro'));
    await tester.pumpAndSettle();
    expect(find.text('Wert eintragen'), findsNothing);

    await tester.tap(find.text('Erfundenes Depot'));
    await tester.pumpAndSettle();
    expect(find.text('Wert eintragen'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'viel');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    expect(sent, isNull);
    expect(find.textContaining('Bitte gib einen Betrag ein'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '20.000,50');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    expect(sent, {'value_cents': 2000050});
    expect(find.text('Wert eintragen'), findsNothing);
    expect(find.text('Wert eingetragen.'), findsOneWidget);
  });

  testWidgets('a child sees its money without wealth and cannot edit', (
    tester,
  ) async {
    final controller = (await tester.runAsync(
      () => _controller(_server(child: true)),
    ))!;
    addTearDown(controller.dispose);
    await _pump(
      tester,
      () => AnimatedBuilder(
        animation: controller,
        builder: (_, _) => ServerAccountsPage(controller: controller),
      ),
    );

    expect(find.text('Dein Geld'), findsOneWidget);
    expect(find.text('Vermögen'), findsNothing);
    expect(find.textContaining('Alltag'), findsNothing);
    expect(find.text('Wer hat was geändert?'), findsNothing);

    await tester.tap(find.text('Erfundenes Depot'));
    await tester.pumpAndSettle();
    expect(find.text('Wert eintragen'), findsNothing);
  });

  testWidgets('the household page names who owes whom', (tester) async {
    final controller = (await tester.runAsync(() => _controller(_server())))!;
    addTearDown(controller.dispose);
    await tester.runAsync(() async {
      await _pump(tester, () => HouseholdPage(controller: controller));
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    await tester.pumpAndSettle();

    expect(find.text('Du schuldest Ben'), findsOneWidget);
  });
}
