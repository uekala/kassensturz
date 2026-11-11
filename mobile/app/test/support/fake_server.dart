import 'dart:convert';

import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_session.dart';
import 'package:kassensturz_mobile/core/networking/mobile_session_store.dart';

String token(String char) => List<String>.filled(43, char).join();

typedef RecordedRequest = ({
  String method,
  Uri uri,
  Map<String, String> headers,
  String? body,
});

/// A transport whose answers are computed per request. The handler may
/// throw a [MobileNetworkException] to simulate a broken connection.
class ScriptedTransport implements MobileTransport {
  ScriptedTransport(this.handler);

  final MobileHttpResponse Function(RecordedRequest request) handler;
  final requests = <RecordedRequest>[];

  @override
  Future<MobileHttpResponse> send({
    required String method,
    required Uri uri,
    required Map<String, String> headers,
    String? body,
  }) async {
    final request = (
      method: method,
      uri: uri,
      headers: Map<String, String>.from(headers),
      body: body,
    );
    requests.add(request);
    return handler(request);
  }

  int count(String method, String path) {
    var total = 0;
    for (final request in requests) {
      if (request.method == method && request.uri.path == path) total++;
    }
    return total;
  }

  @override
  void close() {}
}

MobileHttpResponse jsonResponse(int status, Map<String, dynamic> body) =>
    MobileHttpResponse(statusCode: status, body: jsonEncode(body));

MobileHttpResponse errorResponse(int status, String code, String message) =>
    jsonResponse(status, {
      'error': {'code': code, 'message': message},
    });

Map<String, dynamic> tokenResponse({String? access, String? refresh}) => {
  'access_token': access ?? token('a'),
  'access_expires_in': 600,
  'refresh_token': refresh ?? token('r'),
  'refresh_expires_in': 2592000,
  'token_type': 'Bearer',
};

MobileSession testSession() => MobileSession.fromPairResponse(
  serverUrl: 'https://kassensturz.example.ts.net',
  now: DateTime.now().toUtc(),
  response: {
    'device': {'id': 'device-1', 'name': 'Testgerät'},
    ...tokenResponse(),
  },
);

Future<InMemoryMobileSessionStore> pairedStore() async {
  final store = InMemoryMobileSessionStore();
  await store.write(testSession());
  return store;
}

const fullCapabilities = [
  'overview',
  'transactions',
  'accounts',
  'categories',
  'contracts',
  'transactions.write',
  'transactions.search',
  'stats',
];

/// Answers like a Kassensturz server 0.3.0 with one cash account and one
/// bank account. [capabilities] can be reduced to imitate an older server.
MobileHttpResponse serverAnswer(
  RecordedRequest request, {
  List<String> capabilities = fullCapabilities,
  List<Map<String, dynamic>> transactions = const [],
}) {
  final path = request.uri.path;
  if (path == '/api/v1/me') {
    return jsonResponse(200, {
      'device': {'id': 'device-1', 'name': 'Testgerät'},
      'server': {'name': 'Kassensturz', 'version': '0.3.0'},
      'capabilities': capabilities,
    });
  }
  if (path == '/api/v1/overview') {
    return jsonResponse(200, {
      'as_of': '2026-11-10T12:00:00+00:00',
      'accounts': <Object>[],
      'budgets': <Object>[],
      'alerts': <Object>[],
      'forecast': <String, Object>{},
      'month': <String, Object>{},
    });
  }
  if (path == '/api/v1/accounts') {
    return jsonResponse(200, {
      'items': [
        {
          'id': 1,
          'name': 'Bargeld',
          'type': 'cash',
          'balance_cents': 5000,
          'balance_known': true,
          'manual_entries': true,
        },
        {
          'id': 2,
          'name': 'Girokonto',
          'type': 'giro',
          'balance_cents': 120000,
          'balance_known': true,
          'manual_entries': false,
        },
      ],
    });
  }
  if (path == '/api/v1/categories') {
    return jsonResponse(200, {
      'items': [
        {'id': 5, 'name': 'Wohnen', 'kind': 'expense', 'parent_id': null},
        {'id': 6, 'name': 'Lebensmittel', 'kind': 'expense', 'parent_id': 5},
      ],
    });
  }
  if (path == '/api/v1/stats') {
    final now = DateTime.now();
    final month =
        request.uri.queryParameters['month'] ??
        '${now.year}-${now.month.toString().padLeft(2, '0')}';
    return jsonResponse(200, {
      'month': {
        'month': month,
        'income_cents': 324000,
        'expense_cents': 207800,
        'balance_cents': 116200,
      },
      'categories': [
        {
          'category_id': 6,
          'name': 'Lebensmittel',
          'cents': 155850,
          'share': 0.75,
        },
        {'category_id': 9, 'name': 'Freizeit', 'cents': 51950, 'share': 0.25},
      ],
      'history': [
        for (var index = 1; index <= 12; index++)
          {
            'month': '2026-${index.toString().padLeft(2, '0')}',
            'income_cents': 300000 + index * 1000,
            'expense_cents': 200000 + index * 500,
          },
      ],
      'balance_curve': {
        'today': '2026-11-10',
        'low_point': {'date': '2026-11-28', 'cents': -4500},
        'points': [
          for (var day = 1; day <= 10; day++)
            {
              'date': '2026-11-${day.toString().padLeft(2, '0')}',
              'cents': 400000 - day * 9000,
              'forecast': false,
            },
          for (var day = 11; day <= 30; day++)
            {
              'date': '2026-11-$day',
              'cents': 310000 - (day - 10) * 16000,
              'forecast': true,
            },
        ],
      },
    });
  }
  if (path == '/api/v1/contracts') {
    return jsonResponse(200, {
      'items': [
        {
          'key': 'manual:strom',
          'name': 'Strom',
          'kind': 'expense',
          'interval': 'monatlich',
          'amount_cents': -6500,
          'monthly_cents': -6500,
          'next_due': '2026-12-01',
          'status': 'confirmed',
          'running': true,
          'category_name': 'Wohnen',
          'account_name': 'Girokonto',
          'cancellation_deadline': null,
        },
      ],
    });
  }
  if (path == '/api/v1/transactions' && request.method == 'GET') {
    return jsonResponse(200, {
      'items': transactions,
      'total': transactions.length,
      'limit': 50,
      'offset': 0,
    });
  }
  if (path == '/api/v1/transactions' && request.method == 'POST') {
    return jsonResponse(201, {
      'created': true,
      'transaction': {'id': 9},
    });
  }
  if (path.startsWith('/api/v1/transactions/')) {
    if (request.method == 'DELETE') return jsonResponse(200, {'ok': true});
    return jsonResponse(200, {
      'transaction': {'id': 9},
    });
  }
  return errorResponse(404, 'not_found', 'Unbekannt.');
}

Map<String, dynamic> jsonDecodeMap(String body) =>
    Map<String, dynamic>.from(jsonDecode(body) as Map);

/// A store that already holds [testSession].
class InMemoryStoreHandle {
  InMemoryStoreHandle._(this.store);

  final InMemoryMobileSessionStore store;

  static Future<InMemoryStoreHandle> paired() async =>
      InMemoryStoreHandle._(await pairedStore());
}
