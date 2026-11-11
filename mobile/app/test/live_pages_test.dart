import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';

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
      ],
      'budgets': [
        {
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

void main() {
  testWidgets('connected app shows server data on every tab', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = MobileConnectionController(
      apiClient: MobileApiClient(
        sessionStore: await pairedStore(),
        transport: ScriptedTransport(_answer),
        refreshRetryDelay: Duration.zero,
      ),
      readRetryDelay: Duration.zero,
    );
    await tester.pumpWidget(
      KassensturzApp(mobileConnectionController: controller),
    );
    await tester.pumpAndSettle();

    expect(find.text('NICHT VERBUNDEN'), findsNothing);
    expect(find.text('Frei verfügbar'), findsOneWidget);
    expect(find.text('1.284,50 €'), findsOneWidget);
    expect(find.text('Budget überschritten'), findsOneWidget);

    await tester.tap(find.text('Umsätze').last);
    await tester.pumpAndSettle();
    expect(find.text('3 Buchungen'), findsOneWidget);
    expect(find.text('von Hand'), findsOneWidget);

    await tester.tap(find.text('Planung').last);
    await tester.pumpAndSettle();
    expect(find.text('Noch verfügbar'), findsOneWidget);
    await tester.tap(find.text('Verträge'));
    await tester.pumpAndSettle();
    expect(find.text('Fixkosten pro Monat'), findsOneWidget);
    expect(find.text('Strom'), findsOneWidget);

    await tester.tap(find.text('Konten').last);
    await tester.pumpAndSettle();
    expect(find.text('Gesamtsaldo'), findsOneWidget);
    expect(find.textContaining('Saldo nicht bestätigt'), findsOneWidget);

    await tester.tap(find.byTooltip('Einstellungen'));
    await tester.pumpAndSettle();
    expect(find.text('Mit Kassensturz verbunden'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Umsatz anlegen'));
    await tester.pumpAndSettle();
    expect(find.text('Neuer Umsatz'), findsOneWidget);
  });
}
