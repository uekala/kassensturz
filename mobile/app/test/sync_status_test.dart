import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/core/networking/mobile_models.dart';
import 'package:kassensturz_mobile/features/dashboard/sync_status_card.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'sync'];
final _now = DateTime(2026, 11, 15, 9, 0);

Map<String, dynamic> _status({
  String run = 'idle',
  int added = 0,
  bool canStart = true,
  int wait = 0,
  String state = 'ok',
  int? daysLeft = 99,
  List<Map<String, dynamic>> errors = const [],
}) => {
  'sources': [
    {
      'name': 'Erfundene Bank',
      'last_sync': '2026-11-15T06:30:05',
      'state': state,
      'days_left': daysLeft,
      'accounts': 1,
    },
  ],
  'last_sync': '2026-11-15T06:30:05',
  'newest_sync': '2026-11-15T06:30:05',
  'next_sync': '2026-11-16T06:30:00',
  'run': {'state': run, 'added': added, 'errors': errors},
  'can_start': canStart,
  'wait_minutes': wait,
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
    syncPollInterval: Duration.zero,
    clock: () => _now,
  );
  await controller.restore();
  return controller;
}

Future<void> _pump(
  WidgetTester tester,
  MobileConnectionController controller,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (_, _) => SyncStatusCard(controller: controller),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test('status is read and problems are put into words', () {
    final fine = ServerSyncStatus.fromJson(_status());
    expect(fine.lastSync, DateTime(2026, 11, 15, 6, 30, 5));
    expect(fine.canStart, isTrue);
    expect(fine.problems, isEmpty);
    expect(fine.sources, 1);

    expect(ServerSyncStatus.fromJson(_status(state: 'expired')).problems, [
      'Erfundene Bank: Freigabe abgelaufen',
    ]);
    expect(ServerSyncStatus.fromJson(_status(state: 'no_accounts')).problems, [
      'Erfundene Bank: keine Konten verknüpft',
    ]);
    expect(ServerSyncStatus.fromJson(_status(daysLeft: 9)).problems, [
      'Erfundene Bank: Freigabe läuft in 9 Tagen ab',
    ]);
    final failed = ServerSyncStatus.fromJson(
      _status(
        run: 'error',
        errors: [
          {'name': 'Erfundene Bank', 'message': 'Nicht erreichbar.'},
        ],
      ),
    );
    expect(failed.errors, ['Erfundene Bank: Nicht erreichbar.']);
  });

  test('moments are named relative to today', () {
    expect(
      formatMoment(DateTime(2026, 11, 15, 6, 30), _now),
      'heute, 06:30 Uhr',
    );
    expect(
      formatMoment(DateTime(2026, 11, 14, 23, 5), _now),
      'gestern, 23:05 Uhr',
    );
    expect(
      formatMoment(DateTime(2026, 11, 16, 6, 30), _now),
      'morgen, 06:30 Uhr',
    );
    expect(
      formatMoment(DateTime(2026, 11, 2, 6, 30), _now),
      '02.11.2026, 06:30 Uhr',
    );
  });

  testWidgets('the card shows the state and fetches until the server is done', (
    tester,
  ) async {
    var polls = 0;
    var started = 0;
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/sync') {
        if (request.method == 'POST') {
          started += 1;
          return jsonResponse(202, _status(run: 'running', canStart: false));
        }
        if (started == 0) return jsonResponse(200, _status());
        polls += 1;
        return jsonResponse(
          200,
          polls < 2
              ? _status(run: 'running', canStart: false)
              : _status(run: 'done', added: 3, canStart: false, wait: 30),
        );
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);

    await _pump(tester, controller);
    expect(find.text('Stand: heute, 06:30 Uhr'), findsOneWidget);
    expect(find.text('Nächster von selbst: morgen, 06:30 Uhr'), findsOneWidget);

    await tester.tap(find.text('Jetzt abrufen'));
    await tester.pumpAndSettle();

    expect(started, 1);
    expect(find.text('Abgerufen: 3 neue Buchungen.'), findsOneWidget);
    expect(find.text('Jetzt abrufen'), findsNothing);
    expect(find.textContaining('geht in 30 Minuten'), findsOneWidget);
  });

  testWidgets('a refusal of the server is shown as it is', (tester) async {
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/sync') {
        if (request.method == 'POST') {
          return jsonResponse(409, {
            'error': {
              'code': 'too_soon',
              'message': 'In 12 Minuten geht es wieder.',
            },
          });
        }
        return jsonResponse(200, _status());
      }
      return serverAnswer(request, capabilities: _capabilities);
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);

    await _pump(tester, controller);
    await tester.tap(find.text('Jetzt abrufen'));
    await tester.pumpAndSettle();
    expect(find.text('In 12 Minuten geht es wieder.'), findsOneWidget);
  });

  testWidgets('older servers show no card', (tester) async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    await _pump(tester, controller);
    expect(find.text('Bankabruf'), findsNothing);
    expect(
      transport.requests.where((r) => r.uri.path == '/api/v1/sync'),
      isEmpty,
    );
  });
}
