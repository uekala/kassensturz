import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/features/accounts/loan_sheet.dart';

Map<String, dynamic> _plan(Map<String, dynamic> booked) => {
  'payment_cents': 35000,
  'today_cents': 1354441,
  'booked': booked,
};

void main() {
  test('nothing to compare right after entering the debt', () {
    expect(bookedRatesText(_plan({'expected': 0, 'count': 0})), isNull);
    expect(bookedRatesText({'payment_cents': 35000}), isNull);
  });

  test('all rates booked', () {
    final (text, missing) = bookedRatesText(
      _plan({
        'expected': 3,
        'count': 3,
        'counterparty': 'Erfundene Kreditbank',
        'missing': <String>[],
        'other': <Object>[],
      }),
    )!;
    expect(missing, isFalse);
    expect(
      text,
      '✓ Alle 3 Raten seit dem Eintrag sind gebucht an Erfundene Kreditbank.',
    );
  });

  test('a missing rate names the month and the booked debt', () {
    final (text, missing) = bookedRatesText(
      _plan({
        'expected': 5,
        'count': 4,
        'counterparty': 'Erfundene Kreditbank',
        'missing': ['2026-10'],
        'rest_cents': 1389584,
        'other': [
          {'date': '2026-09-20', 'cents': 100000},
        ],
      }),
    )!;
    expect(missing, isTrue);
    expect(text, contains('Für 10/2026 ist keine Abbuchung über 350,00 €'));
    expect(text, contains('wären es heute 13.895,84 €.'));
    expect(
      text,
      contains('Weitere Zahlungen an Erfundene Kreditbank: 1.000,00 €'),
    );
  });

  test('no booked rate at all', () {
    final (text, missing) = bookedRatesText(
      _plan({
        'expected': 2,
        'count': 0,
        'missing': ['2026-10', '2026-11'],
      }),
    )!;
    expect(missing, isFalse);
    expect(text, startsWith('Keine Abbuchung über genau 350,00 €'));
  });
}
