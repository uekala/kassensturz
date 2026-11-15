import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/budget/triage_page.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'triage', 'budgets.suggest'];

Map<String, dynamic> _transaction(int id, String who, int cents) => {
  'id': id,
  'account_id': 2,
  'booking_date': '2026-11-0$id',
  'amount_cents': cents,
  'manual': false,
  'counterparty': who,
  'purpose': 'Test',
  'account_name': 'Girokonto',
  'category': {'id': 99, 'name': 'Sonstiges'},
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

Future<void> _pump(WidgetTester tester, Widget page) async {
  await tester.pumpWidget(MaterialApp(theme: AppTheme.light(), home: page));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('cards are sorted one by one and similar ones follow', (
    tester,
  ) async {
    final open = [
      _transaction(1, 'Erfundene Firma XY', -45000),
      _transaction(2, 'Erfundener Kiosk', -1200),
      _transaction(3, 'Erfundene Firma XY', -30000),
    ];
    final transport = ScriptedTransport((request) {
      final path = request.uri.path;
      if (path == '/api/v1/triage') {
        return jsonResponse(200, {
          'items': open,
          'total': open.length,
          'expense_cents': 76200,
        });
      }
      if (request.method == 'PATCH' && path == '/api/v1/transactions/1') {
        // The server moved the similar entry along.
        open.removeWhere((item) => item['id'] == 1 || item['id'] == 3);
        return jsonResponse(200, {
          'transaction': _transaction(1, 'Erfundene Firma XY', -45000),
          'also_changed': 1,
          'learned': true,
        });
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    expect(controller.triageTotal, 3);
    expect(controller.triageExpenseCents, 76200);

    await _pump(tester, TriagePage(controller: controller));
    expect(find.text('Noch 3 Buchungen'), findsOneWidget);
    expect(find.text('Erfundene Firma XY'), findsOneWidget);

    final category = controller.categories.firstWhere(
      (item) => item.kind == 'expense',
    );
    await tester.tap(find.widgetWithText(ActionChip, category.name));
    await tester.pumpAndSettle();

    final patch = transport.requests.lastWhere((r) => r.method == 'PATCH');
    expect(jsonDecode(patch.body!), {'category_id': category.id});
    expect(find.text('Noch eine Buchung'), findsOneWidget);
    expect(find.text('Erfundener Kiosk'), findsOneWidget);
    expect(
      find.text('${category.name} gemerkt, eine ähnliche Buchung gleich mit.'),
      findsOneWidget,
    );

    await tester.ensureVisible(find.text('Überspringen'));
    await tester.tap(find.text('Überspringen'));
    await tester.pumpAndSettle();
    expect(
      find.text('Bis auf die übersprungenen ist alles zugeordnet.'),
      findsOneWidget,
    );
    expect(
      find.text('2 Buchungen haben jetzt eine Kategorie.'),
      findsOneWidget,
    );
  });

  testWidgets('budget suggestions are accepted one by one or all at once', (
    tester,
  ) async {
    final puts = <String, dynamic>{};
    final transport = ScriptedTransport((request) {
      final path = request.uri.path;
      if (path == '/api/v1/budgets/suggestions') {
        return jsonResponse(200, {
          'months': 3,
          'items': [
            {
              'category_id': 5,
              'name': 'Lebensmittel',
              'average_cents': 37666,
              'suggested_cents': 38000,
              'current_cents': 5000,
            },
            {
              'category_id': 6,
              'name': 'Freizeit',
              'average_cents': 8100,
              'suggested_cents': 9000,
              'current_cents': null,
            },
          ],
        });
      }
      if (request.method == 'PUT' && path.startsWith('/api/v1/budgets/')) {
        puts[path.split('/').last] = jsonDecode(request.body!);
        return jsonResponse(200, {'ok': true});
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);

    await _pump(tester, BudgetSuggestionsPage(controller: controller));
    expect(find.textContaining('der letzten 3 vollen Monate'), findsOneWidget);
    expect(find.text('Im Schnitt 376,66 €, bisher 50,00 €'), findsOneWidget);
    expect(find.text('Im Schnitt 81,00 €, bisher kein Budget'), findsOneWidget);

    await tester.tap(find.text('90,00 €'));
    await tester.pumpAndSettle();
    expect(puts, {
      '6': {'limit_cents': 9000},
    });
    expect(find.text('Freizeit'), findsNothing);

    await tester.tap(find.text('Alle übernehmen'));
    await tester.pumpAndSettle();
    expect(puts['5'], {'limit_cents': 38000});
    expect(
      find.text('Übernommen. Deine Budgets passen jetzt zu deinen Ausgaben.'),
      findsOneWidget,
    );
  });
}
