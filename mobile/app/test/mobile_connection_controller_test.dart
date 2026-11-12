import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/core/networking/mobile_session.dart';
import 'package:kassensturz_mobile/core/networking/mobile_session_store.dart';

import 'support/fake_server.dart';

const _transactionsPath = '/api/v1/transactions';

MobileConnectionController _controller(
  MobileSessionStore store,
  ScriptedTransport transport, {
  DateTime Function()? clock,
}) => MobileConnectionController(
  apiClient: MobileApiClient(
    sessionStore: store,
    transport: transport,
    refreshRetryDelay: Duration.zero,
  ),
  readRetryDelay: Duration.zero,
  clock: clock,
);

Map<String, dynamic> _createFields() => {
  'client_request_id': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'account_id': 1,
  'booking_date': '2026-11-09',
  'amount_cents': -450,
  'counterparty': 'KS-MOBILTEST Bäckerei',
};

class _UnreadableStore implements MobileSessionStore {
  bool cleared = false;

  @override
  Future<MobileSession?> read() async {
    if (cleared) return null;
    throw const FormatException('Gespeicherte Sitzung ist ungültig.');
  }

  @override
  Future<void> write(MobileSession session) async {}

  @override
  Future<void> clear() async {
    cleared = true;
  }
}

void main() {
  test('restore loads all server data and records the sync', () async {
    final transport = ScriptedTransport(serverAnswer);
    final now = DateTime(2026, 11, 10, 12, 30);
    final controller = _controller(
      await pairedStore(),
      transport,
      clock: () => now,
    );

    await controller.restore();

    expect(controller.linkState, ServerLinkState.connected);
    expect(controller.lastSyncAt, now);
    expect(controller.serverVersion, '0.3.0');
    expect(controller.canWriteTransactions, isTrue);
    expect(controller.serverNeedsUpdate, isFalse);
    expect(controller.accounts, hasLength(2));
    expect(controller.manualAccounts.single.name, 'Bargeld');
    expect(controller.categories, hasLength(3));
    expect(controller.overviewData, isNotNull);
    expect(controller.financeError, isNull);
    controller.dispose();
  });

  test('without a stored session nothing is requested', () async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = _controller(InMemoryMobileSessionStore(), transport);

    await controller.restore();

    expect(controller.linkState, ServerLinkState.notPaired);
    expect(controller.lastSyncAt, isNull);
    expect(transport.requests, isEmpty);
    controller.dispose();
  });

  test('an older server is shown as connected but read-only', () async {
    final transport = ScriptedTransport(
      (request) => serverAnswer(
        request,
        capabilities: const ['overview', 'transactions'],
      ),
    );
    final controller = _controller(await pairedStore(), transport);

    await controller.restore();
    final failure = await controller.createTransaction(_createFields());

    expect(controller.linkState, ServerLinkState.connected);
    expect(controller.canWriteTransactions, isFalse);
    expect(controller.serverNeedsUpdate, isTrue);
    expect(failure, contains('aktualisiere'));
    expect(transport.count('GET', '/api/v1/accounts'), 0);
    expect(transport.count('POST', _transactionsPath), 0);
    controller.dispose();
  });

  test('unreachable server keeps the session and the last data', () async {
    var offline = false;
    final transport = ScriptedTransport((request) {
      if (offline) {
        throw const MobileNetworkException(
          MobileNetworkFailure.unreachable,
          requestSent: false,
        );
      }
      return serverAnswer(request);
    });
    final store = await pairedStore();
    final controller = _controller(store, transport);
    await controller.restore();
    final firstSync = controller.lastSyncAt;

    offline = true;
    await controller.loadFinancialData();

    expect(controller.linkState, ServerLinkState.unreachable);
    expect(controller.isConnected, isTrue);
    expect(controller.financeError, contains('Tailscale'));
    expect(controller.overviewData, isNotNull);
    expect(controller.lastSyncAt, firstSync);
    expect(await store.read(), isNotNull);

    offline = false;
    await controller.loadFinancialData();

    expect(controller.linkState, ServerLinkState.connected);
    expect(controller.financeError, isNull);
    controller.dispose();
  });

  test('a read is repeated once after a transport failure', () async {
    var failures = 1;
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/overview' && failures > 0) {
        failures--;
        throw const MobileNetworkException(
          MobileNetworkFailure.interrupted,
          requestSent: true,
        );
      }
      return serverAnswer(request);
    });
    final controller = _controller(await pairedStore(), transport);

    await controller.restore();

    expect(transport.count('GET', '/api/v1/overview'), 2);
    expect(controller.linkState, ServerLinkState.connected);
    expect(controller.financeError, isNull);
    controller.dispose();
  });

  test('creating a transaction sends it once and reloads the data', () async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();
    final overviewLoads = transport.count('GET', '/api/v1/overview');

    final failure = await controller.createTransaction(_createFields());

    expect(failure, isNull);
    expect(transport.count('POST', _transactionsPath), 1);
    expect(transport.count('GET', '/api/v1/overview'), overviewLoads + 1);
    controller.dispose();
  });

  test('a repeated save reuses the same request id', () async {
    var breakConnection = true;
    final transport = ScriptedTransport((request) {
      if (request.method == 'POST' && breakConnection) {
        throw const MobileNetworkException(
          MobileNetworkFailure.interrupted,
          requestSent: true,
        );
      }
      return serverAnswer(request);
    });
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();
    final fields = _createFields();

    final first = await controller.createTransaction(fields);
    breakConnection = false;
    final second = await controller.createTransaction(fields);

    expect(first, contains('unterbrochen'));
    expect(second, isNull);
    final ids = <Object?>[];
    for (final request in transport.requests) {
      if (request.method != 'POST') continue;
      ids.add((jsonDecode(request.body!) as Map)['client_request_id']);
    }
    expect(ids, hasLength(2));
    expect(ids.toSet(), hasLength(1));
    controller.dispose();
  });

  test('server refusal is passed on and nothing is reloaded', () async {
    final transport = ScriptedTransport((request) {
      if (request.method == 'DELETE') {
        return errorResponse(
          409,
          'not_deletable',
          'Bankumsätze können nicht gelöscht werden.',
        );
      }
      return serverAnswer(request);
    });
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();
    final loads = transport.count('GET', '/api/v1/overview');

    final failure = await controller.deleteTransaction(3);

    expect(failure, 'Bankumsätze können nicht gelöscht werden.');
    expect(transport.count('GET', '/api/v1/overview'), loads);
    expect(controller.linkState, ServerLinkState.connected);
    controller.dispose();
  });

  test('filters are sent to the server and can be cleared', () async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();

    await controller.setTransactionFilter(accountId: 1, categoryId: 6);

    final filtered = transport.requests.last.uri.queryParameters;
    expect(filtered['account_id'], '1');
    expect(filtered['category_id'], '6');
    expect(controller.hasTransactionFilter, isTrue);

    await controller.setTransactionFilter();

    final cleared = transport.requests.last.uri.queryParameters;
    expect(cleared.containsKey('account_id'), isFalse);
    expect(controller.hasTransactionFilter, isFalse);
    controller.dispose();
  });

  test('search and kind are sent to the server and can be cleared', () async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();
    expect(controller.canSearchTransactions, isTrue);

    await controller.setTransactionSearch('  Bäckerei ');
    await controller.setTransactionKind('out');

    final filtered = transport.requests.last.uri.queryParameters;
    expect(filtered['q'], 'Bäckerei');
    expect(filtered['kind'], 'out');
    expect(controller.hasTransactionFilter, isTrue);

    final before = transport.count('GET', _transactionsPath);
    await controller.setTransactionSearch('Bäckerei');
    expect(transport.count('GET', _transactionsPath), before);

    await controller.setTransactionSearch('');
    await controller.setTransactionKind(null);

    final cleared = transport.requests.last.uri.queryParameters;
    expect(cleared.containsKey('q'), isFalse);
    expect(cleared.containsKey('kind'), isFalse);
    expect(controller.hasTransactionFilter, isFalse);
    controller.dispose();
  });

  test('a server without search is never sent search parameters', () async {
    final transport = ScriptedTransport(
      (request) => serverAnswer(
        request,
        capabilities: const ['overview', 'transactions', 'transactions.write'],
      ),
    );
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();
    expect(controller.canSearchTransactions, isFalse);

    await controller.setTransactionSearch('Bäckerei');
    await controller.setTransactionKind('in');

    final sent = transport.requests.last.uri.queryParameters;
    expect(sent.containsKey('q'), isFalse);
    expect(sent.containsKey('kind'), isFalse);
    controller.dispose();
  });

  test('the analysis is loaded on demand, also for another month', () async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();
    expect(controller.canShowStats, isTrue);
    expect(transport.count('GET', '/api/v1/stats'), 0);

    await controller.loadStats();
    expect(controller.stats?['categories'], hasLength(2));
    expect(transport.requests.last.uri.queryParameters, isEmpty);

    await controller.loadStats(month: '2026-10');
    expect(controller.stats?['month']?['month'], '2026-10');
    expect(transport.requests.last.uri.queryParameters['month'], '2026-10');
    expect(controller.statsError, isNull);
    controller.dispose();
  });

  test('a server without analysis is not asked for it', () async {
    final transport = ScriptedTransport(
      (request) => serverAnswer(
        request,
        capabilities: const ['overview', 'transactions', 'transactions.write'],
      ),
    );
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();

    await controller.loadStats();

    expect(controller.canShowStats, isFalse);
    expect(transport.count('GET', '/api/v1/stats'), 0);
    controller.dispose();
  });

  test('contracts are loaded on demand', () async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = _controller(await pairedStore(), transport);
    await controller.restore();

    expect(transport.count('GET', '/api/v1/contracts'), 0);
    await controller.loadContracts();

    expect(controller.contracts.single.name, 'Strom');
    expect(controller.contractsError, isNull);
    controller.dispose();
  });

  test('a revoked device loses its session and all server data', () async {
    var revoked = false;
    final transport = ScriptedTransport((request) {
      if (revoked) {
        return errorResponse(401, 'unauthorized', 'Anmeldung erforderlich.');
      }
      return serverAnswer(request);
    });
    final store = await pairedStore();
    final controller = _controller(store, transport);
    await controller.restore();

    revoked = true;
    await controller.loadFinancialData();

    expect(controller.linkState, ServerLinkState.notPaired);
    expect(controller.overviewData, isNull);
    expect(controller.accounts, isEmpty);
    expect(controller.canWriteTransactions, isFalse);
    expect(controller.statusMessage, contains('kopple'));
    expect(await store.read(), isNull);
    controller.dispose();
  });

  test('an unreadable stored session is removed', () async {
    final store = _UnreadableStore();
    final controller = _controller(store, ScriptedTransport(serverAnswer));

    await controller.restore();

    expect(store.cleared, isTrue);
    expect(controller.linkState, ServerLinkState.notPaired);
    expect(controller.errorMessage, contains('erneut ein'));
    controller.dispose();
  });

  test('returning to the app reloads only when the data is old', () async {
    var now = DateTime(2026, 11, 10, 12);
    final transport = ScriptedTransport(serverAnswer);
    final controller = _controller(
      await pairedStore(),
      transport,
      clock: () => now,
    );
    await controller.restore();
    final loads = transport.count('GET', '/api/v1/overview');

    now = now.add(const Duration(seconds: 20));
    await controller.refreshIfStale();
    expect(transport.count('GET', '/api/v1/overview'), loads);

    now = now.add(const Duration(minutes: 2));
    await controller.refreshIfStale();
    expect(transport.count('GET', '/api/v1/overview'), loads + 1);
    expect(controller.lastSyncAt, now);
    controller.dispose();
  });

  test('disconnecting signs out on the server and forgets the data', () async {
    final transport = ScriptedTransport((request) {
      if (request.uri.path == '/api/v1/auth/logout') {
        return jsonResponse(200, {'ok': true});
      }
      return serverAnswer(request);
    });
    final store = await pairedStore();
    final controller = _controller(store, transport);
    await controller.restore();

    await controller.logout();

    expect(transport.count('POST', '/api/v1/auth/logout'), 1);
    expect(controller.linkState, ServerLinkState.notPaired);
    expect(controller.overviewData, isNull);
    expect(controller.lastSyncAt, isNull);
    expect(await store.read(), isNull);
    controller.dispose();
  });
}
