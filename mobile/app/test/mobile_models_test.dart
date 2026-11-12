import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/networking/mobile_models.dart';

import 'support/fake_server.dart';

RecordedRequest _get(String path) => (
  method: 'GET',
  uri: Uri.parse('https://kassensturz.example.ts.net$path'),
  headers: const <String, String>{},
  body: null,
);

Map<String, dynamic> _body(String path) {
  final response = serverAnswer(_get(path));
  expect(response.statusCode, 200);
  return Map<String, dynamic>.from(jsonDecodeMap(response.body));
}

void main() {
  test('accounts are parsed with their manual-entry flag', () {
    final accounts = ServerAccount.listFrom(_body('/api/v1/accounts'));

    expect(accounts, hasLength(2));
    expect(accounts[0].name, 'Bargeld');
    expect(accounts[0].balanceCents, 5000);
    expect(accounts[0].manualEntries, isTrue);
    expect(accounts[1].manualEntries, isFalse);
  });

  test('categories and contracts are parsed from server lists', () {
    final categories = ServerCategory.listFrom(_body('/api/v1/categories'));
    final contracts = ServerContract.listFrom(_body('/api/v1/contracts'));

    expect(categories.map((category) => category.id), [5, 6, 7]);
    expect(categories[1].parentId, 5);
    expect(contracts.single.name, 'Strom');
    expect(contracts.single.monthlyCents, -6500);
    expect(contracts.single.running, isTrue);
    expect(contracts.single.cancellationDeadline, isNull);
  });

  test('a response without a list is rejected instead of shown as empty', () {
    expect(
      () => ServerAccount.listFrom({'items': 'nope'}),
      throwsFormatException,
    );
    expect(
      () => ServerAccount.listFrom({
        'items': [
          {'id': 1, 'name': 'Bargeld'},
        ],
      }),
      throwsFormatException,
    );
  });

  test('transaction keeps the manual flag, note and category', () {
    final transaction = ServerTransaction.fromJson({
      'id': 7,
      'account_id': 1,
      'booking_date': '2026-11-09',
      'amount_cents': -450,
      'counterparty': 'Bäckerei',
      'purpose': null,
      'note': 'Frühstück',
      'account_name': 'Bargeld',
      'manual': true,
      'category': {'id': 6, 'name': 'Lebensmittel'},
    });

    expect(transaction.manual, isTrue);
    expect(transaction.amountCents, -450);
    expect(transaction.purpose, isNull);
    expect(transaction.note, 'Frühstück');
    expect(transaction.categoryId, 6);
    expect(transaction.categoryName, 'Lebensmittel');
  });

  test('transaction from an older server without account id is rejected', () {
    expect(
      () => ServerTransaction.fromJson({
        'id': 7,
        'booking_date': '2026-11-09',
        'amount_cents': -450,
      }),
      throwsFormatException,
    );
  });

  test('amounts are converted to integer cents without rounding errors', () {
    expect(parseAmountToCents('12,50'), 1250);
    expect(parseAmountToCents('12,5'), 1250);
    expect(parseAmountToCents('12'), 1200);
    expect(parseAmountToCents('1.234,56'), 123456);
    expect(parseAmountToCents('0,29 €'), 29);
    expect(parseAmountToCents('19.99'), 1999);
    expect(parseAmountToCents('0,07'), 7);
  });

  test('invalid, zero and negative amounts are rejected', () {
    for (final input in ['', '0', '0,00', '-5', 'abc', '1,234', '1,2,3']) {
      expect(parseAmountToCents(input), isNull, reason: input);
    }
  });

  test('dates use the ISO format the server expects', () {
    expect(formatIsoDate(DateTime(2026, 1, 5)), '2026-01-05');
    expect(formatIsoDate(DateTime(2026, 11, 30)), '2026-11-30');
  });

  test('request ids are long enough, hex only and differ per call', () {
    final first = newClientRequestId();
    final second = newClientRequestId();

    expect(first, hasLength(32));
    expect(RegExp(r'^[0-9a-f]{32}$').hasMatch(first), isTrue);
    expect(first, isNot(second));
    expect(newClientRequestId(random: Random(1)), hasLength(32));
  });
}
