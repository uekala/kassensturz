import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';

void main() {
  testWidgets('shows prototype notice and dashboard by default',
      (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    expect(find.text('Prototyp mit Beispieldaten – noch nicht verbunden'),
        findsOneWidget);
    expect(find.text('Dein Überblick'), findsOneWidget);
    expect(find.text('2.486,30 €'), findsOneWidget);
  });

  testWidgets('navigates to accounts and transactions', (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Konten'));
    await tester.pumpAndSettle();
    expect(find.text('Beispielhafte Kontenübersicht'), findsOneWidget);
    expect(find.text('Girokonto'), findsOneWidget);

    await tester.tap(find.text('Buchungen'));
    await tester.pumpAndSettle();
    expect(find.text('Deine letzten Buchungen im Überblick.'), findsOneWidget);
    expect(find.text('REWE'), findsOneWidget);
  });

  testWidgets('shows that server pairing is not available yet', (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Mehr'));
    await tester.pumpAndSettle();
    expect(find.text('Noch nicht verbunden'), findsOneWidget);
    expect(find.text('Pairing noch nicht verfügbar'), findsOneWidget);
  });
}
