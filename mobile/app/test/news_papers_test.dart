import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/dashboard/news_card.dart';
import 'package:kassensturz_mobile/features/more/papers_page.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'news', 'papers'];

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

void main() {
  testWidgets('news stay until they are marked as read', (tester) async {
    var seen = 0;
    final transport = ScriptedTransport((request) {
      final path = request.uri.path;
      if (path == '/api/v1/news/seen') {
        seen += 1;
        return jsonResponse(200, {'ok': true});
      }
      if (path == '/api/v1/news') {
        return jsonResponse(200, {
          'count': 5,
          'income_cents': 280000,
          'expense_cents': 66150,
          'largest': [
            {'label': 'Erfundene Firma GmbH', 'amount_cents': 280000},
            {'label': 'Erfundener Vermieter', 'amount_cents': -64000},
            {'label': 'Erfundene Bäckerei', 'amount_cents': -1250},
          ],
        });
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: AnimatedBuilder(
            animation: controller,
            builder: (_, _) => NewsCard(controller: controller),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('5 neue Buchungen'), findsOneWidget);
    expect(find.text('+2.800,00 € und −661,50 €'), findsOneWidget);
    expect(find.text('Erfundener Vermieter'), findsOneWidget);
    expect(find.text('und 2 weitere'), findsOneWidget);

    await tester.tap(find.text('Gelesen'));
    await tester.pumpAndSettle();
    expect(seen, 1);
    expect(find.text('Seit deinem letzten Besuch'), findsNothing);
  });

  testWidgets('tax overview and warranties are shown per year', (tester) async {
    final asked = <String?>[];
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/papers') {
        final year = request.uri.queryParameters['year'];
        asked.add(year);
        return jsonResponse(200, {
          'tax': {
            'year': year == '2025' ? 2025 : 2026,
            'years': [2026, 2025],
            'count': 2,
            'total_cents': year == '2025' ? 9900 : 53000,
            'missing_receipts': 1,
            'groups': [
              {
                'kind': 'handwerker',
                'label': 'Handwerkerleistung',
                'count': 1,
                'total_cents': year == '2025' ? 9900 : 48000,
                'missing_receipts': 0,
              },
              if (year != '2025')
                {
                  'kind': 'spende',
                  'label': 'Spende',
                  'count': 1,
                  'total_cents': 5000,
                  'missing_receipts': 1,
                },
            ],
          },
          'warranties': {
            'running': [
              {
                'id': 3,
                'label': 'Erfundene Waschmaschine',
                'amount_cents': -59900,
                'booking_date': '2025-01-15',
                'warranty_until': '2026-12-05',
                'days_left': 20,
                'receipt_count': 0,
              },
            ],
            'expired': [],
          },
        });
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    expect(controller.canShowPapers, isTrue);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: PapersPage(controller: controller),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Handwerkerleistung'), findsOneWidget);
    expect(find.text('480,00 €'), findsOneWidget);
    expect(find.text('1 Buchung, 1 ohne Beleg'), findsOneWidget);
    expect(find.textContaining('Zusammen 530,00 € in 2026'), findsOneWidget);
    expect(find.text('Erfundene Waschmaschine'), findsOneWidget);
    expect(find.text('599,00 €, noch 20 Tage, ohne Beleg'), findsOneWidget);
    expect(find.text('05.12.2026'), findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, '2025'));
    await tester.pumpAndSettle();
    expect(asked, [null, '2025']);
    expect(find.text('99,00 €'), findsOneWidget);
    expect(find.text('Spende'), findsNothing);
  });
}
