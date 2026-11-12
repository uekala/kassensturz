import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/accounts/server_finance_pages.dart';

import 'support/fake_server.dart';

const _transactions = <Map<String, dynamic>>[
  {
    'id': 1,
    'amount_cents': -4217,
    'counterparty': 'Supermarkt',
    'purpose': '',
    'booking_date': '2026-11-09',
    'category': {'id': 6, 'name': 'Lebensmittel'},
    'account_name': 'Girokonto',
    'manual': false,
  },
  {
    'id': 2,
    'amount_cents': -1190,
    'counterparty': 'Bäckerei',
    'purpose': '',
    'booking_date': '2026-11-09',
    'category': {'id': 6, 'name': 'Lebensmittel'},
    'account_name': 'Bargeld',
    'manual': true,
  },
  {
    'id': 3,
    'amount_cents': 12000,
    'counterparty': 'Erstattung',
    'purpose': '',
    'booking_date': '2026-11-08',
    'category': null,
    'account_name': 'Girokonto',
    'manual': false,
  },
];

MobileHttpResponse _answer(RecordedRequest request) {
  if (request.uri.path == '/api/v1/overview') {
    return jsonResponse(200, {
      'as_of': '2026-11-10T12:00:00+00:00',
      'accounts': [
        {
          'name': 'Girokonto',
          'type': 'giro',
          'balance_cents': 242450,
          'balance_known': true,
          'balance_date': '2026-11-10',
        },
        {
          'name': 'Kreditkarte mit einem sehr langen Namen',
          'type': 'card',
          'balance_cents': -6732,
          'balance_known': false,
        },
        {
          'name': 'Testdepot',
          'type': 'depot',
          'balance_cents': 1234567,
          'balance_known': true,
          'balance_date': '2026-11-10',
          'in_forecast': false,
          'previous_value_cents': 1200000,
          'previous_value_date': '2026-10-01',
        },
      ],
      'budgets': [
        {
          'category_id': 6,
          'name': 'Lebensmittel',
          'limit_cents': 45000,
          'spent_cents': 31200,
          'remaining_cents': 13800,
          'state': 'ok',
        },
        {
          'name': 'Freizeit',
          'limit_cents': 12000,
          'spent_cents': 14100,
          'remaining_cents': -2100,
          'state': 'over',
        },
      ],
      'alerts': [
        {
          'level': 'warning',
          'title': 'Budget überschritten',
          'message': 'Freizeit liegt über dem Limit.',
        },
      ],
      'forecast': {
        'free_cents': 128450,
        'balance_cents': 391218,
        'month_end_cents': 243100,
      },
      'month': {'income_cents': 324000, 'expense_cents': -207800},
    });
  }
  return serverAnswer(request, transactions: _transactions);
}

Future<ScriptedTransport> _pumpConnectedApp(WidgetTester tester) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final transport = ScriptedTransport(_answer);
  final controller = MobileConnectionController(
    apiClient: MobileApiClient(
      sessionStore: await pairedStore(),
      transport: transport,
      refreshRetryDelay: Duration.zero,
    ),
    readRetryDelay: Duration.zero,
  );
  await tester.pumpWidget(
    KassensturzApp(mobileConnectionController: controller),
  );
  await tester.pumpAndSettle();
  return transport;
}

void main() {
  testWidgets('connected app shows server data on every tab', (tester) async {
    final transport = await _pumpConnectedApp(tester);

    expect(find.text('NICHT VERBUNDEN'), findsNothing);
    expect(find.text('Frei verfügbar'), findsOneWidget);
    expect(find.text('1.284,50 €'), findsOneWidget);
    expect(find.text('Budget überschritten'), findsOneWidget);

    await tester.tap(find.text('Auswertung'));
    await tester.pumpAndSettle();
    expect(find.text('Nach Kategorie'), findsOneWidget);
    expect(find.text('Freizeit'), findsOneWidget);
    expect(find.textContaining('75 %'), findsOneWidget);
    expect(find.text('Letzte 12 Monate'), findsOneWidget);
    await tester.tap(find.byTooltip('Vorheriger Monat'));
    await tester.pumpAndSettle();
    final now = DateTime.now();
    final previous = DateTime(now.year, now.month - 1);
    expect(
      transport.requests.last.uri.queryParameters['month'],
      '${previous.year}-${previous.month.toString().padLeft(2, '0')}',
    );
    expect(find.text('Freizeit'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('Tiefster erwarteter Stand'),
      300,
    );
    await tester.pageBack();
    await tester.pumpAndSettle();

    await tester.tap(find.text('Umsätze').last);
    await tester.pumpAndSettle();
    expect(find.text('3 Buchungen'), findsOneWidget);
    expect(find.text('von Hand'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'kiosk');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(transport.requests.last.uri.queryParameters['q'], 'kiosk');
    await tester.tap(find.text('Ausgaben'));
    await tester.pumpAndSettle();
    expect(transport.requests.last.uri.queryParameters['kind'], 'out');
    expect(transport.requests.last.uri.queryParameters['q'], 'kiosk');
    await tester.tap(find.byTooltip('Suche leeren'));
    await tester.pumpAndSettle();
    expect(
      transport.requests.last.uri.queryParameters.containsKey('q'),
      isFalse,
    );

    await tester.tap(find.text('Planung').last);
    await tester.pumpAndSettle();
    expect(find.text('Noch verfügbar'), findsOneWidget);
    await tester.tap(find.text('Verträge'));
    await tester.pumpAndSettle();
    expect(find.text('Fixkosten pro Monat'), findsOneWidget);
    expect(find.text('Strom'), findsOneWidget);

    await tester.tap(find.text('Konten').last);
    await tester.pumpAndSettle();
    expect(find.text('Vermögen'), findsOneWidget);
    expect(find.textContaining('Depots 12.345,67'), findsOneWidget);
    expect(find.textContaining('Saldo nicht bestätigt'), findsOneWidget);
    expect(find.textContaining('Depot · Stand 10.11.2026'), findsOneWidget);

    await tester.tap(find.byTooltip('Einstellungen'));
    await tester.pumpAndSettle();
    expect(find.text('Mit Kassensturz verbunden'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Umsatz anlegen'));
    await tester.pumpAndSettle();
    expect(find.text('Neuer Umsatz'), findsOneWidget);
  });

  testWidgets('the app follows the dark setting of the phone', (tester) async {
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
    await _pumpConnectedApp(tester);

    final context = tester.element(find.text('Frei verfügbar'));
    expect(Theme.of(context).brightness, Brightness.dark);
    expect(KlarColors.of(context).surface, KlarColors.dark.surface);
    expect(Theme.of(context).scaffoldBackgroundColor, KlarColors.dark.surface);

    await tester.tap(find.text('Auswertung'));
    await tester.pumpAndSettle();
    expect(find.text('Nach Kategorie'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    for (final tab in ['Umsätze', 'Planung', 'Konten']) {
      await tester.tap(find.text(tab).last);
      await tester.pumpAndSettle();
    }
    await tester.tap(find.byTooltip('Umsatz anlegen'));
    await tester.pumpAndSettle();
    expect(find.text('Betrag in Euro'), findsOneWidget);
  });

  testWidgets('budgets can be changed, removed and created in the app', (
    tester,
  ) async {
    final transport = await _pumpConnectedApp(tester);
    await tester.tap(find.text('Planung').last);
    await tester.pumpAndSettle();

    await tester.tap(_inBudgets('Lebensmittel'));
    await tester.pumpAndSettle();
    expect(find.text('Budget Lebensmittel'), findsOneWidget);
    expect(find.text('450'), findsOneWidget);
    await tester.enterText(find.byType(TextFormField), '500,50');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    var put = transport.requests.lastWhere((r) => r.method == 'PUT');
    expect(put.uri.path, '/api/v1/budgets/6');
    expect(jsonDecode(put.body!), {'limit_cents': 50050});
    expect(find.text('Budget gespeichert'), findsOneWidget);

    await tester.tap(_inBudgets('Lebensmittel'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Budget entfernen'));
    await tester.pumpAndSettle();
    put = transport.requests.lastWhere((r) => r.method == 'PUT');
    expect(jsonDecode(put.body!), {'limit_cents': null});

    await tester.tap(find.text('Budget anlegen'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    expect(find.text('Bitte eine Kategorie wählen.'), findsOneWidget);
    expect(find.text('Gehalt'), findsNothing);
    await tester.tap(find.byType(DropdownButtonFormField<int>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Wohnen').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).last, '900');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    put = transport.requests.lastWhere((r) => r.method == 'PUT');
    expect(put.uri.path, '/api/v1/budgets/5');
    expect(jsonDecode(put.body!), {'limit_cents': 90000});
  });
}

Finder _inBudgets(String text) => find.descendant(
  of: find.byType(ServerBudgetPage),
  matching: find.text(text),
);
