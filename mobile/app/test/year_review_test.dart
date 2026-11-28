import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/analysis/year_review_page.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'year'];

Map<String, dynamic> _year(int year) => {
  'year': year,
  'running': year == 2026,
  'until': year == 2026 ? '2026-06-20' : '$year-12-31',
  'has_data': true,
  'years': [2025, 2026],
  'income_cents': 1500000,
  'expense_cents': 750000,
  'saved_cents': 750000,
  'savings_rate': 0.5,
  'fixed_cents': 300000,
  'count': 13,
  'previous': year == 2026
      ? {'income_cents': 1200000, 'expense_cents': 600000, 'saved_cents': 0}
      : null,
  'months': [
    {'month': '$year-01', 'income_cents': 250000, 'expense_cents': 100000},
    {'month': '$year-02', 'income_cents': 250000, 'expense_cents': 250000},
  ],
  'best_month': {'month': '$year-01', 'label': 'Januar', 'saldo_cents': 150000},
  'worst_month': {'month': '$year-02', 'label': 'Februar', 'saldo_cents': 0},
  'categories': [
    {
      'name': 'Testurlaub',
      'cents': 150000,
      'share': 0.2,
      'previous_cents': year == 2026 ? 0 : null,
    },
    {
      'name': 'Erfundener Laden',
      'cents': 600000,
      'share': 0.8,
      'previous_cents': year == 2026 ? 600000 : null,
    },
  ],
  'biggest': [
    {
      'name': 'Erfundenes Reisebuero',
      'amount_cents': -150000,
      'date': '$year-05-10',
    },
  ],
};

void main() {
  test('the sentences name savings, the year before and the months', () {
    final text = yearReviewText(_year(2026));
    expect(text, contains('Gespart 7.500,00 €, Sparquote 50 %.'));
    expect(
      text,
      contains('Ausgaben 1.500,00 € höher als im Vorjahr bis zum selben Tag.'),
    );
    expect(text, contains('40 % der Ausgaben waren feste Zahlungen'));
    expect(text, contains('Bester Monat: Januar (1.500,00 €)'));
    expect(yearReviewText(_year(2025)), isNot(contains('Vorjahr')));
  });

  testWidgets('the year in review shows the server figures and switches', (
    tester,
  ) async {
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/year') {
        final year = int.parse(request.uri.queryParameters['year']!);
        return jsonResponse(200, _year(year));
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
    expect(controller.canShowYear, isTrue);
    tester.view.physicalSize = const Size(800, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: YearReviewPage(controller: controller, year: 2026),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Jahresrückblick 2026'), findsOneWidget);
    expect(find.text('7.500,00 €'), findsOneWidget);
    expect(find.textContaining('neu'), findsOneWidget);
    expect(find.textContaining('wie im Vorjahr'), findsOneWidget);

    await tester.tap(find.text('2025'));
    await tester.pumpAndSettle();
    expect(transport.requests.last.uri.queryParameters['year'], '2025');
    expect(find.text('Jahresrückblick 2025'), findsOneWidget);
    expect(find.textContaining('Vorjahr:'), findsNothing);
  });
}
