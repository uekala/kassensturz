import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';

import 'support/fake_server.dart';

const _refreshPath = '/api/v1/auth/refresh';

MobileHttpResponse _unauthorized() =>
    errorResponse(401, 'unauthorized', 'Anmeldung erforderlich.');

MobileApiClient _client(
  InMemoryStoreHandle handle,
  ScriptedTransport transport,
) => MobileApiClient(
  sessionStore: handle.store,
  transport: transport,
  refreshRetryDelay: Duration.zero,
);

void main() {
  test('lost refresh answer is repeated once with the same token', () async {
    final handle = await InMemoryStoreHandle.paired();
    var refreshCalls = 0;
    final transport = ScriptedTransport((request) {
      if (request.uri.path == _refreshPath) {
        refreshCalls++;
        if (refreshCalls == 1) {
          throw const MobileNetworkException(
            MobileNetworkFailure.interrupted,
            requestSent: true,
          );
        }
        return jsonResponse(
          200,
          tokenResponse(access: token('b'), refresh: token('s')),
        );
      }
      final authorization = request.headers['Authorization'];
      return authorization == 'Bearer ${token('b')}'
          ? serverAnswer(request)
          : _unauthorized();
    });
    final client = _client(handle, transport);

    final identity = await client.me();

    expect(identity['server'], isA<Map>());
    expect(transport.count('POST', _refreshPath), 2);
    final bodies = transport.requests
        .where((request) => request.uri.path == _refreshPath)
        .map((request) => jsonDecode(request.body!) as Map)
        .toList();
    expect(bodies[0]['refresh_token'], token('r'));
    expect(bodies[1]['refresh_token'], token('r'));
    final saved = await handle.store.read();
    expect(saved?.refreshToken, token('s'));
    expect(saved?.accessToken, token('b'));
    client.close();
  });

  test('refresh is not repeated when nothing reached the server', () async {
    final handle = await InMemoryStoreHandle.paired();
    final transport = ScriptedTransport((request) {
      if (request.uri.path == _refreshPath) {
        throw const MobileNetworkException(
          MobileNetworkFailure.unreachable,
          requestSent: false,
        );
      }
      return _unauthorized();
    });
    final client = _client(handle, transport);

    await expectLater(client.me(), throwsA(isA<MobileNetworkException>()));

    expect(transport.count('POST', _refreshPath), 1);
    final saved = await handle.store.read();
    expect(saved?.refreshToken, token('r'), reason: 'session must be kept');
    client.close();
  });

  test('refresh is sent at most twice per attempt', () async {
    final handle = await InMemoryStoreHandle.paired();
    final transport = ScriptedTransport((request) {
      if (request.uri.path == _refreshPath) {
        throw const MobileNetworkException(
          MobileNetworkFailure.timeout,
          requestSent: true,
        );
      }
      return _unauthorized();
    });
    final client = _client(handle, transport);

    await expectLater(client.me(), throwsA(isA<MobileNetworkException>()));

    expect(transport.count('POST', _refreshPath), 2);
    expect(await handle.store.read(), isNotNull);
    client.close();
  });

  test('rejected repetition ends the session and asks for pairing', () async {
    final handle = await InMemoryStoreHandle.paired();
    var refreshCalls = 0;
    final transport = ScriptedTransport((request) {
      if (request.uri.path == _refreshPath) {
        refreshCalls++;
        if (refreshCalls == 1) {
          throw const MobileNetworkException(
            MobileNetworkFailure.interrupted,
            requestSent: true,
          );
        }
      }
      return _unauthorized();
    });
    final client = _client(handle, transport);

    await expectLater(
      client.me(),
      throwsA(isA<MobileSessionExpiredException>()),
    );

    expect(await handle.store.read(), isNull);
    client.close();
  });

  test('parallel calls share one refresh and never send it twice', () async {
    final handle = await InMemoryStoreHandle.paired();
    final transport = ScriptedTransport((request) {
      if (request.uri.path == _refreshPath) {
        return jsonResponse(
          200,
          tokenResponse(access: token('b'), refresh: token('s')),
        );
      }
      final authorization = request.headers['Authorization'];
      return authorization == 'Bearer ${token('b')}'
          ? serverAnswer(request)
          : _unauthorized();
    });
    final client = _client(handle, transport);

    final results = await Future.wait([
      client.me(),
      client.overview(),
      client.accounts(),
      client.categories(),
    ]);

    expect(results, hasLength(4));
    expect(transport.count('POST', _refreshPath), 1);
    client.close();
  });

  test('a rotated token is never sent again after success', () async {
    final handle = await InMemoryStoreHandle.paired();
    final sent = <String>[];
    var accepted = token('a');
    var generation = 0;
    final transport = ScriptedTransport((request) {
      if (request.uri.path == _refreshPath) {
        sent.add((jsonDecode(request.body!) as Map)['refresh_token'] as String);
        generation++;
        accepted = token('bcd'[generation - 1]);
        return jsonResponse(
          200,
          tokenResponse(
            access: accepted,
            refresh: token('xyz'[generation - 1]),
          ),
        );
      }
      return request.headers['Authorization'] == 'Bearer $accepted'
          ? serverAnswer(request)
          : _unauthorized();
    });
    final client = _client(handle, transport);

    accepted = 'expired';
    await client.me();
    accepted = 'expired';
    await client.me();

    expect(sent, [token('r'), token('x')]);
    expect(sent.toSet(), hasLength(2));
    client.close();
  });

  test('write calls carry a JSON body and the bearer token', () async {
    final handle = await InMemoryStoreHandle.paired();
    final transport = ScriptedTransport(serverAnswer);
    final client = _client(handle, transport);

    await client.createTransaction({
      'client_request_id': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'account_id': 1,
      'booking_date': '2026-11-09',
      'amount_cents': -450,
      'counterparty': 'Bäckerei',
    });
    await client.updateTransaction(9, {'note': 'x'});
    await client.deleteTransaction(9);

    final create = transport.requests[0];
    expect(create.method, 'POST');
    expect(create.uri.path, '/api/v1/transactions');
    expect(create.uri.query, isEmpty);
    expect(create.headers['Authorization'], 'Bearer ${token('a')}');
    expect((jsonDecode(create.body!) as Map)['amount_cents'], -450);
    expect(transport.requests[1].method, 'PATCH');
    expect(transport.requests[1].uri.path, '/api/v1/transactions/9');
    expect(transport.requests[2].method, 'DELETE');
    expect(transport.requests[2].body, isNull);
    client.close();
  });

  test('creating without a request id is refused before sending', () async {
    final handle = await InMemoryStoreHandle.paired();
    final transport = ScriptedTransport(serverAnswer);
    final client = _client(handle, transport);

    expect(
      () => client.createTransaction({'account_id': 1}),
      throwsFormatException,
    );
    expect(() => client.updateTransaction(9, {}), throwsFormatException);
    expect(transport.requests, isEmpty);
    client.close();
  });

  test('a failed write is not repeated automatically', () async {
    final handle = await InMemoryStoreHandle.paired();
    final transport = ScriptedTransport((request) {
      if (request.method == 'POST') {
        throw const MobileNetworkException(
          MobileNetworkFailure.interrupted,
          requestSent: true,
        );
      }
      return serverAnswer(request);
    });
    final client = _client(handle, transport);

    await expectLater(
      client.createTransaction({
        'client_request_id': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'account_id': 1,
      }),
      throwsA(isA<MobileNetworkException>()),
    );

    expect(transport.count('POST', '/api/v1/transactions'), 1);
    client.close();
  });
}
