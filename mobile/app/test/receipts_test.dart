import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/core/networking/mobile_models.dart';
import 'package:kassensturz_mobile/features/transactions/receipts_section.dart';
import 'package:kassensturz_mobile/features/transactions/transaction_editor_page.dart';

import 'support/fake_server.dart';

const _capabilities = [...fullCapabilities, 'tax', 'receipts', 'warranty'];
final _photo = Uint8List.fromList([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3]);

/// A server that keeps receipts of transaction 4 in memory.
class _ReceiptServer {
  final receipts = <Map<String, dynamic>>[
    {'id': 11, 'filename': 'rechnung.jpg', 'mime': 'image/jpeg', 'size': 2048},
  ];

  late final transport = ScriptedTransport(_json, binaryHandler: _binary);

  MobileHttpResponse _json(RecordedRequest request) {
    final path = request.uri.path;
    if (path == '/api/v1/transactions/4/receipts') {
      return jsonResponse(200, {'items': receipts, 'max': 10});
    }
    if (request.method == 'DELETE' && path.startsWith('/api/v1/receipts/')) {
      final id = int.parse(path.split('/').last);
      receipts.removeWhere((receipt) => receipt['id'] == id);
      return jsonResponse(200, {'ok': true});
    }
    return serverAnswer(request, capabilities: _capabilities);
  }

  MobileBinaryResponse _binary(RecordedBinaryRequest request) {
    if (request.method == 'POST') {
      final receipt = {
        'id': 12,
        'filename': request.uri.queryParameters['filename'],
        'mime': 'image/jpeg',
        'size': request.body!.length,
      };
      receipts.add(receipt);
      return binaryJson(201, {'receipt': receipt});
    }
    return MobileBinaryResponse(statusCode: 200, bytes: _photo);
  }
}

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

const _bankTransaction = ServerTransaction(
  id: 4,
  accountId: 2,
  bookingDate: '2026-11-09',
  amountCents: -48000,
  manual: false,
  counterparty: 'Erfundener Malerbetrieb',
  accountName: 'Girokonto',
  categoryId: 5,
  categoryName: 'Wohnen',
);

/// Scrolls until [target] is built and then fully into view, so a tap hits it.
Future<void> _reveal(
  WidgetTester tester,
  Finder target,
  Finder list,
  double step,
) async {
  await tester.dragUntilVisible(target, list, Offset(0, step));
  await tester.ensureVisible(target);
  await tester.pumpAndSettle();
}

void main() {
  test('transactions carry tax kind and receipt count', () {
    final transaction = ServerTransaction.fromJson({
      'id': 7,
      'account_id': 1,
      'booking_date': '2026-11-09',
      'amount_cents': -450,
      'manual': false,
      'tax_kind': 'spende',
      'receipt_count': 2,
    });
    expect(transaction.taxKind, 'spende');
    expect(transaction.receiptCount, 2);

    final older = ServerTransaction.fromJson({
      'id': 7,
      'account_id': 1,
      'booking_date': '2026-11-09',
      'amount_cents': -450,
    });
    expect(older.taxKind, isNull);
    expect(older.receiptCount, 0);
  });

  test('warranty end is parsed and years are added by calendar', () {
    final transaction = ServerTransaction.fromJson({
      'id': 7,
      'account_id': 1,
      'booking_date': '2026-11-09',
      'amount_cents': -450,
      'warranty_until': '2028-11-09',
    });
    expect(transaction.warrantyUntil, '2028-11-09');
    expect(addYears(DateTime(2026, 11, 9), 2), DateTime(2028, 11, 9));
    expect(addYears(DateTime(2024, 2, 29), 2), DateTime(2026, 2, 28));
    expect(addYears(DateTime(2024, 2, 29), 4), DateTime(2028, 2, 29));
  });

  test('receipts describe their kind and size', () {
    final items = ServerReceipt.listFrom({
      'items': [
        {'id': 1, 'filename': 'a.jpg', 'mime': 'image/jpeg', 'size': 2048},
        {
          'id': 2,
          'filename': 'b.pdf',
          'mime': 'application/pdf',
          'size': 3 * 1024 * 1024 + 512 * 1024,
        },
      ],
    });
    expect(items.first.isImage, isTrue);
    expect(items.first.sizeLabel, '2 KB');
    expect(items.last.isImage, isFalse);
    expect(items.last.sizeLabel, '3,5 MB');
  });

  test(
    'upload sends the raw file with the session and reads it back',
    () async {
      final server = _ReceiptServer();
      final client = MobileApiClient(
        sessionStore: await pairedStore(),
        transport: server.transport,
        refreshRetryDelay: Duration.zero,
      );

      final answer = await client.uploadReceipt(4, 'beleg.jpg', _photo);
      final sent = server.transport.binaryRequests.single;
      expect(sent.method, 'POST');
      expect(sent.uri.path, '/api/v1/transactions/4/receipts');
      expect(sent.uri.queryParameters, {'filename': 'beleg.jpg'});
      expect(sent.headers['Authorization'], 'Bearer ${token('a')}');
      expect(sent.body, _photo);
      expect((answer['receipt'] as Map)['id'], 12);

      expect(await client.receiptBytes(12), _photo);
      expect(
        () => client.uploadReceipt(4, 'leer.jpg', Uint8List(0)),
        throwsFormatException,
      );
    },
  );

  test('a refused upload reports the message of the server', () async {
    final transport = ScriptedTransport(
      serverAnswer,
      binaryHandler: (_) => binaryJson(400, {
        'error': {
          'code': 'invalid_request',
          'message': 'Als Beleg gehen Fotos und PDF.',
        },
      }),
    );
    final controller = await _controller(transport);
    expect(
      await controller.addReceipt(4, 'a.txt', _photo),
      'Als Beleg gehen Fotos und PDF.',
    );
    controller.dispose();
  });

  testWidgets('a bank transaction gets a tax kind and receipts', (
    tester,
  ) async {
    final server = _ReceiptServer();
    final controller = (await tester.runAsync(
      () => _controller(server.transport),
    ))!;
    addTearDown(controller.dispose);
    expect(controller.canTagTax, isTrue);
    expect(controller.canUseReceipts, isTrue);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: TransactionEditorPage(
          controller: controller,
          existing: _bankTransaction,
          receiptPicker: ({required bool camera}) async =>
              PickedReceipt(name: 'foto.jpg', bytes: _photo),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final list = find.byType(ListView).first;

    await _reveal(tester, find.text('rechnung.jpg'), list, -200);
    expect(find.text('2 KB'), findsOneWidget);

    await _reveal(tester, find.text('Foto aufnehmen'), list, -200);
    await tester.tap(find.text('Foto aufnehmen'));
    await tester.pumpAndSettle();
    expect(find.text('foto.jpg'), findsOneWidget);
    expect(server.transport.binaryRequests.single.body, _photo);

    await _reveal(tester, find.byTooltip('Beleg entfernen').first, list, 100);
    await tester.tap(find.byTooltip('Beleg entfernen').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Entfernen'));
    await tester.pumpAndSettle();
    expect(find.text('rechnung.jpg'), findsNothing);
    expect(find.text('foto.jpg'), findsOneWidget);

    await _reveal(tester, find.text('Nicht relevant'), list, 100);
    await tester.tap(find.text('Nicht relevant'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Spende'));
    await tester.pumpAndSettle();
    expect(find.text('Spende'), findsOneWidget);

    await _reveal(tester, find.text('Keine Garantie'), list, 100);
    await tester.tap(find.text('Keine Garantie'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('2 Jahre ab Kauf'));
    await tester.pumpAndSettle();
    expect(find.text('09.11.2028'), findsOneWidget);

    await _reveal(tester, find.text('Auf dem Server speichern'), list, -200);
    await tester.tap(find.text('Auf dem Server speichern'));
    await tester.pumpAndSettle();
    final patch = server.transport.requests.lastWhere(
      (request) => request.method == 'PATCH',
    );
    expect(patch.uri.path, '/api/v1/transactions/4');
    expect(jsonDecode(patch.body!), {
      'tax_kind': 'spende',
      'warranty_until': '2028-11-09',
    });
  });

  testWidgets('an older server shows neither tax kind nor receipts', (
    tester,
  ) async {
    final transport = ScriptedTransport(serverAnswer);
    final controller = (await tester.runAsync(() => _controller(transport)))!;
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: TransactionEditorPage(
          controller: controller,
          existing: _bankTransaction,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Für die Steuererklärung'), findsNothing);
    expect(find.text('Garantie bis'), findsNothing);
    expect(find.text('Belege'), findsNothing);
    expect(transport.binaryRequests, isEmpty);
  });
}
