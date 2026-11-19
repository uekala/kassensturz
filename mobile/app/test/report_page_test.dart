import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/features/reports/report_page.dart';

void main() {
  test('report titles name the month or the year', () {
    expect(reportTitle('month', '2026-10'), 'Monatsbericht Oktober 2026');
    expect(reportTitle('month', '2026-03'), 'Monatsbericht März 2026');
    expect(reportTitle('year', '2025'), 'Jahresrückblick 2025');
    expect(reportTitle('month', 'kaputt'), 'Monatsbericht');
    expect(reportTitle('month', '2026-13'), 'Monatsbericht');
  });
}
