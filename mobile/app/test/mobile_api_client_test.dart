import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_session.dart';
import 'package:kassensturz_mobile/core/networking/mobile_session_store.dart';

String token(String char) => List<String>.filled(43, char).join();

class FakeTransport implements MobileTransport {
  FakeTransport(this.responses);

  final List<MobileHttpResponse> responses;
  final requests =
      <({String method, Uri uri, Map<String, String> headers, String? body})>[];

  @override
  Future<MobileHttpResponse> send({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    String? body,
  }) async {
    requests.add((
      method: method,
      uri: uri,
      headers: Map<String, String>.from(headers),
      body: body,
    ));
    return responses.removeAt(0);
  }

  @override
  void close() {}
}

MobileHttpResponse jsonResponse(int status, Map<String, dynamic> body) =>
    MobileHttpResponse(statusCode: status, body: jsonEncode(body));

Map<String, dynamic> tokenResponse({String? access, String? refresh}) => {
  'access_token': access ?? token('a'),
  'access_expires_in': 600,
  'refresh_token': refresh ?? token('r'),
  'refresh_expires_in': 2592000,
  'token_type': 'Bearer',
};

MobileSession session() => MobileSession.fromPairResponse(
  serverUrl: 'https://kassensturz.example.ts.net',
  now: DateTime.utc(2026, 11, 3, 12),
  response: {
    'device': {'id': 'device-1', 'name': 'Testgerät'},
    ...tokenResponse(),
  },
);

void main() {
  test('session server URL requires HTTPS and rejects path or credentials', () {
    expect(
      MobileSession.normalizeServerUrl('https://example.ts.net/'),
      'https://example.ts.net',
    );
    expect(
      () => MobileSession.normalizeServerUrl('http://example.ts.net'),
      throwsFormatException,
    );
    expect(
      () => MobileSession.normalizeServerUrl(
        'https://user:secret@example.ts.net',
      ),
      throwsFormatException,
    );
    expect(
      () => MobileSession.normalizeServerUrl('https://example.ts.net/api'),
      throwsFormatException,
    );
  });

  test('secure session serialization round trips', () {
    final original = session();
    final restored = MobileSession.fromStoredJson(original.toStoredJson());
    expect(restored.serverUrl, original.serverUrl);
    expect(restored.deviceId, original.deviceId);
    expect(restored.accessToken, original.accessToken);
    expect(restored.refreshToken, original.refreshToken);
    expect(restored.accessExpiresAt, original.accessExpiresAt);
  });

  test('pair sends one-time secret in HTTPS body, not URL', () async {
    final store = InMemoryMobileSessionStore();
    final transport = FakeTransport([
      jsonResponse(201, {
        'device': {'id': 'phone-1', 'name': 'iPhone'},
        ...tokenResponse(),
      }),
    ]);
    final client = MobileApiClient(sessionStore: store, transport: transport);

    final paired = await client.pair(
      serverUrl: 'https://kassensturz.example.ts.net/',
      pairingSecret: token('p'),
      deviceName: 'iPhone',
    );

    expect(paired.deviceId, 'phone-1');
    final request = transport.requests.single;
    expect(request.method, 'POST');
    expect(request.uri.scheme, 'https');
    expect(request.uri.path, '/api/v1/pair');
    expect(request.uri.query, isEmpty);
    expect(request.body, contains(token('p')));
    expect(request.headers.containsKey('Authorization'), isFalse);
    expect((await store.read())?.refreshToken, paired.refreshToken);
    client.close();
  });

  test('health check uses HTTPS without requiring a session', () async {
    final transport = FakeTransport([
      jsonResponse(200, {
        'status': 'ok',
        'api_version': 1,
        'server': {'name': 'Kassensturz', 'version': '0.2.0'},
      }),
    ]);
    final client = MobileApiClient(
      sessionStore: InMemoryMobileSessionStore(),
      transport: transport,
    );

    final health = await client.health(
      serverUrl: 'https://kassensturz.example.ts.net',
    );

    expect(health['status'], 'ok');
    final request = transport.requests.single;
    expect(request.method, 'GET');
    expect(request.uri.scheme, 'https');
    expect(request.uri.path, '/api/v1/health');
    expect(request.headers.containsKey('Authorization'), isFalse);
    expect(request.body, isNull);
    client.close();
  });

  test('health check rejects incompatible API version', () async {
    final transport = FakeTransport([
      jsonResponse(200, {
        'status': 'ok',
        'api_version': 2,
        'server': {'name': 'Kassensturz'},
      }),
    ]);
    final client = MobileApiClient(
      sessionStore: InMemoryMobileSessionStore(),
      transport: transport,
    );

    await expectLater(
      client.health(serverUrl: 'https://kassensturz.example.ts.net'),
      throwsFormatException,
    );
    client.close();
  });

  test('pair rejects HTTP without sending a request', () async {
    final transport = FakeTransport([]);
    final client = MobileApiClient(
      sessionStore: InMemoryMobileSessionStore(),
      transport: transport,
    );

    await expectLater(
      client.pair(
        serverUrl: 'http://kassensturz.local',
        pairingSecret: token('p'),
        deviceName: 'iPhone',
      ),
      throwsFormatException,
    );
    expect(transport.requests, isEmpty);
    client.close();
  });

  test('401 rotates refresh token and retries with new access token', () async {
    final store = InMemoryMobileSessionStore();
    await store.write(session());
    final transport = FakeTransport([
      jsonResponse(401, {
        'error': {'code': 'unauthorized', 'message': 'Unauthorized'},
      }),
      jsonResponse(200, tokenResponse(access: token('b'), refresh: token('s'))),
      jsonResponse(200, {
        'device': {'id': 'device-1', 'name': 'Testgerät'},
        'server': {'name': 'Kassensturz', 'version': '0.2.0'},
      }),
    ]);
    final client = MobileApiClient(sessionStore: store, transport: transport);

    final identity = await client.me();

    expect(identity['server']['name'], 'Kassensturz');
    expect(transport.requests, hasLength(3));
    expect(
      transport.requests[0].headers['Authorization'],
      'Bearer ${token('a')}',
    );
    expect(transport.requests[1].uri.path, '/api/v1/auth/refresh');
    expect(transport.requests[1].body, contains(token('r')));
    expect(transport.requests[1].uri.query, isEmpty);
    expect(
      transport.requests[2].headers['Authorization'],
      'Bearer ${token('b')}',
    );
    final saved = await store.read();
    expect(saved?.accessToken, token('b'));
    expect(saved?.refreshToken, token('s'));
    client.close();
  });

  test('refresh rejection clears local credentials', () async {
    final store = InMemoryMobileSessionStore();
    await store.write(session());
    final response = jsonResponse(401, {
      'error': {'code': 'unauthorized', 'message': 'Unauthorized'},
    });
    final transport = FakeTransport([response, response]);
    final client = MobileApiClient(sessionStore: store, transport: transport);

    await expectLater(
      client.me(),
      throwsA(isA<MobileSessionExpiredException>()),
    );
    expect(await store.read(), isNull);
    client.close();
  });

  test(
    'transaction filters are query parameters, credentials stay in header',
    () async {
      final store = InMemoryMobileSessionStore();
      await store.write(session());
      final transport = FakeTransport([
        jsonResponse(200, {'items': [], 'total': 0, 'limit': 25, 'offset': 50}),
      ]);
      final client = MobileApiClient(sessionStore: store, transport: transport);

      await client.transactions(
        limit: 25,
        offset: 50,
        month: '2026-11',
        accountId: 7,
        categoryId: 3,
      );

      final request = transport.requests.single;
      expect(request.uri.path, '/api/v1/transactions');
      expect(request.uri.queryParameters['month'], '2026-11');
      expect(request.uri.queryParameters['account_id'], '7');
      expect(request.headers['Authorization'], 'Bearer ${token('a')}');
      expect(request.uri.query, isNot(contains(token('a'))));
      client.close();
    },
  );

  test('logout always removes the local session', () async {
    final store = InMemoryMobileSessionStore();
    await store.write(session());
    final transport = FakeTransport([
      jsonResponse(200, {'ok': true}),
    ]);
    final client = MobileApiClient(sessionStore: store, transport: transport);

    await client.logout();

    expect(await store.read(), isNull);
    expect(transport.requests.single.uri.path, '/api/v1/auth/logout');
    client.close();
  });
}
