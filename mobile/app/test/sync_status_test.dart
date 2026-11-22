import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/core/networking/mobile_models.dart';
import 'package:kassensturz_mobile/features/dashboard/bank_renew_sheet.dart';
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
  int? renew,
  Map<String, dynamic>? question,
  List<Map<String, dynamic>> errors = const [],
}) => {
  'sources': [
    {
      'name': 'Erfundene Bank',
      'last_sync': '2026-11-15T06:30:05',
      'state': state,
      'days_left': daysLeft,
      'accounts': 1,
      'renew': renew,
    },
  ],
  'last_sync': '2026-11-15T06:30:05',
  'newest_sync': '2026-11-15T06:30:05',
  'next_sync': '2026-11-16T06:30:00',
  'run': {'state': run, 'added': added, 'errors': errors},
  'can_start': canStart,
  'wait_minutes': wait,
  'question': question,
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

  test('a consent that can be renewed is read from the status', () {
    expect(ServerSyncStatus.fromJson(_status()).renewals, isEmpty);
    final due = ServerSyncStatus.fromJson(_status(daysLeft: 5, renew: 1));
    expect(due.renewals.single, (id: 1, name: 'Erfundene Bank'));
  });

  testWidgets('the card offers renewing only with the capability', (
    tester,
  ) async {
    for (final capabilities in [
      _capabilities,
      [..._capabilities, 'banks.renew'],
    ]) {
      final transport = ScriptedTransport((request) {
        if (request.uri.path == '/api/v1/sync') {
          return jsonResponse(200, _status(daysLeft: 5, renew: 1));
        }
        return serverAnswer(request, capabilities: capabilities);
      });
      final controller = (await tester.runAsync(() => _controller(transport)))!;
      await _pump(tester, controller);
      expect(
        find.text('Freigabe für Erfundene Bank erneuern'),
        capabilities.contains('banks.renew') ? findsOneWidget : findsNothing,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    }
  });

  testWidgets('renewing opens the bank and hands the address back', (
    tester,
  ) async {
    final sent = <String, Map<String, dynamic>>{};
    var renewed = false;
    final transport = ScriptedTransport((request) {
      final path = request.uri.path;
      if (path == '/api/v1/sync') {
        return jsonResponse(
          200,
          renewed ? _status() : _status(daysLeft: 5, renew: 1),
        );
      }
      if (path.startsWith('/api/v1/banks/renew')) {
        sent[path] = jsonDecode(request.body!) as Map<String, dynamic>;
        if (path.endsWith('/complete')) {
          if (sent[path]!['text'] == 'falsch') {
            return jsonResponse(409, {
              'error': {
                'code': 'bank_refused',
                'message': 'In der Adresse fehlt ein eindeutiger Code.',
              },
            });
          }
          renewed = true;
          return jsonResponse(200, {'name': 'Erfundene Bank', 'accounts': 1});
        }
        return jsonResponse(200, {
          'name': 'Erfundene Bank',
          'url': 'https://bank.example.invalid/freigabe',
          'days': 180,
        });
      }
      return serverAnswer(
        request,
        capabilities: [..._capabilities, 'banks.renew'],
      );
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    Uri? opened;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showModalBottomSheet<void>(
                context: context,
                isScrollControlled: true,
                builder: (_) => BankRenewSheet(
                  controller: controller,
                  id: 1,
                  name: 'Erfundene Bank',
                  openUrl: (url) async {
                    opened = url;
                    return true;
                  },
                ),
              ),
              child: const Text('auf'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('auf'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Bank öffnen'));
    await tester.pumpAndSettle();
    expect(sent['/api/v1/banks/renew'], {'id': 1});
    expect(opened, Uri.parse('https://bank.example.invalid/freigabe'));
    expect(find.text('Noch einmal öffnen'), findsOneWidget);

    await tester.tap(find.text('Freigabe abschließen'));
    await tester.pumpAndSettle();
    expect(
      find.text('Füge die Adresse der letzten Seite ein.'),
      findsOneWidget,
    );
    expect(sent.containsKey('/api/v1/banks/renew/complete'), isFalse);

    await tester.enterText(find.byType(TextField), 'falsch');
    await tester.tap(find.text('Freigabe abschließen'));
    await tester.pumpAndSettle();
    expect(
      find.text('In der Adresse fehlt ein eindeutiger Code.'),
      findsOneWidget,
    );

    const address = 'https://enablebanking.com/?code=ks-test&state=ks-state';
    await tester.enterText(find.byType(TextField), address);
    await tester.tap(find.text('Freigabe abschließen'));
    await tester.pumpAndSettle();
    expect(sent['/api/v1/banks/renew/complete'], {'text': address});
    expect(find.text('Freigabe abschließen'), findsNothing);
    expect(find.text('Freigabe für Erfundene Bank erneuert.'), findsOneWidget);
    expect(controller.syncStatus!.renewals, isEmpty);
  });

  test('questions of a bank are read, unknown ones are left alone', () {
    BankQuestion? read(Map<String, dynamic> question) =>
        ServerSyncStatus.fromJson(_status(question: question)).question;

    final tan = read({
      'qid': 'q1',
      'kind': 'tan',
      'bank': 'Erfundene Bank',
      'text': 'Bitte TAN eingeben.',
      'image': 'data:image/png;base64,AAEC',
      'flicker': ['10101', '0101', 7],
    })!;
    expect((tan.qid, tan.kind, tan.text), ('q1', 'tan', 'Bitte TAN eingeben.'));
    expect(tan.image, [0, 1, 2]);
    expect(tan.flicker, ['10101']);

    final choice = read({
      'qid': 'q2',
      'kind': 'choice',
      'bank': 'Erfundene Bank',
      'title': 'Welches Verfahren?',
      'options': [
        {'value': '921', 'label': 'pushTAN', 'hint': 'App-Freigabe'},
        {'value': '', 'label': 'leer'},
      ],
    })!;
    expect(choice.options.single.value, '921');

    expect(read({'qid': 'q3', 'kind': 'neu', 'bank': 'X'}), isNull);
    expect(read({'qid': '', 'kind': 'tan'}), isNull);
    expect(
      read({'qid': 'q4', 'kind': 'choice', 'options': <Object>[]}),
      isNull,
    );
    expect(ServerSyncStatus.fromJson(_status()).question, isNull);
  });

  testWidgets('a TAN asked by the bank is entered in the card', (tester) async {
    const question = {
      'qid': 'ks-frage-1',
      'kind': 'tan',
      'bank': 'Erfundene Bank',
      'text': 'Bitte TAN aus der erfundenen App eingeben.',
    };
    final sent = <Map<String, dynamic>>[];
    Map<String, dynamic>? startBody;
    var answered = false;
    final transport = ScriptedTransport((request) {
      final path = request.uri.path;
      if (path == '/api/v1/sync/answer') {
        final body = jsonDecode(request.body!) as Map<String, dynamic>;
        sent.add(body);
        if (body['value'] == '000000') {
          return jsonResponse(409, {
            'error': {
              'code': 'bank_refused',
              'message': 'Diese Rückfrage ist nicht mehr offen.',
            },
          });
        }
        answered = true;
        return jsonResponse(200, _status(run: 'running', canStart: false));
      }
      if (path == '/api/v1/sync') {
        if (request.method == 'POST') {
          startBody = jsonDecode(request.body!) as Map<String, dynamic>;
        }
        return jsonResponse(
          200,
          answered
              ? _status(run: 'done', added: 1, canStart: false, wait: 30)
              : _status(run: 'running', canStart: false, question: question),
        );
      }
      return serverAnswer(
        request,
        capabilities: [..._capabilities, 'sync.tan'],
      );
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);

    await _pump(tester, controller);
    expect(find.text('Erfundene Bank verlangt eine TAN'), findsOneWidget);
    expect(
      find.text('Bitte TAN aus der erfundenen App eingeben.'),
      findsOneWidget,
    );
    expect(find.text('Jetzt abrufen'), findsNothing);

    await tester.tap(find.text('TAN senden'));
    await tester.pumpAndSettle();
    expect(find.text('Bitte gib die TAN ein.'), findsOneWidget);
    expect(sent, isEmpty);

    await tester.enterText(find.byType(TextField), '000000');
    await tester.tap(find.text('TAN senden'));
    await tester.pumpAndSettle();
    expect(find.text('Diese Rückfrage ist nicht mehr offen.'), findsOneWidget);

    await tester.enterText(find.byType(TextField), ' 123456 ');
    await tester.tap(find.text('TAN senden'));
    await tester.pumpAndSettle();
    expect(sent.last, {'qid': 'ks-frage-1', 'value': '123456'});
    expect(find.text('Erfundene Bank verlangt eine TAN'), findsNothing);
    expect(controller.bankQuestion, isNull);
    expect(controller.syncStatus!.running, isFalse);
    // Von hier wurde nichts gestartet: Der Abruf wartete schon.
    expect(startBody, isNull);
  });

  testWidgets('starting from the app allows the bank to ask back', (
    tester,
  ) async {
    Map<String, dynamic>? startBody;
    final cancelled = <Map<String, dynamic>>[];
    var open = true;
    final transport = ScriptedTransport((request) {
      final path = request.uri.path;
      if (path == '/api/v1/sync/answer') {
        cancelled.add(jsonDecode(request.body!) as Map<String, dynamic>);
        open = false;
        return jsonResponse(200, _status(run: 'done', canStart: false));
      }
      if (path == '/api/v1/sync') {
        if (request.method == 'POST') {
          startBody = jsonDecode(request.body!) as Map<String, dynamic>;
          return jsonResponse(
            202,
            _status(
              run: 'running',
              canStart: false,
              question: {
                'qid': 'ks-frage-2',
                'kind': 'decoupled',
                'bank': 'Erfundene Bank',
                'text': 'Bitte bestätige den Zugriff in deiner Banking-App.',
              },
            ),
          );
        }
        if (startBody == null) return jsonResponse(200, _status());
        return jsonResponse(
          200,
          open
              ? _status(
                  run: 'running',
                  canStart: false,
                  question: {
                    'qid': 'ks-frage-2',
                    'kind': 'decoupled',
                    'bank': 'Erfundene Bank',
                    'text':
                        'Bitte bestätige den Zugriff in deiner Banking-App.',
                  },
                )
              : _status(run: 'done', canStart: false, wait: 30),
        );
      }
      return serverAnswer(
        request,
        capabilities: [..._capabilities, 'sync.tan'],
      );
    });
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);
    await _pump(tester, controller);

    await tester.tap(find.text('Jetzt abrufen'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 10));
    expect(startBody, {'interactive': true});
    expect(
      find.text('Erfundene Bank: Freigabe in der Banking-App'),
      findsOneWidget,
    );
    expect(find.text('Ich habe freigegeben'), findsOneWidget);

    await tester.tap(find.text('Abruf abbrechen'));
    await tester.pumpAndSettle();
    expect(cancelled.single, {'qid': 'ks-frage-2', 'cancel': true});
    expect(find.text('Abruf abbrechen'), findsNothing);
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
