import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';

void main() {
  testWidgets('shows prototype dashboard and demo status by default',
      (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    expect(find.text('Beispieldaten – noch nicht mit deinem Server verbunden'),
        findsOneWidget);
    expect(find.text('Dein Überblick'), findsOneWidget);
    expect(find.text('2.486,30 €'), findsOneWidget);
    expect(find.text('DEMO'), findsOneWidget);
  });

  testWidgets('dashboard action opens the transaction tab', (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.scrollUntilVisible(
      find.text('Alle Buchungen anzeigen'),
      180,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Alle Buchungen anzeigen'));
    await tester.pumpAndSettle();

    expect(find.text('Buchungen'), findsWidgets);
    expect(find.text('5 Buchungen · Beispieldaten'), findsOneWidget);
  });

  testWidgets('bottom navigation opens accounts and settings', (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Konten').last);
    await tester.pumpAndSettle();
    expect(find.text('Gesamtsaldo · Beispieldaten'), findsOneWidget);
    expect(find.text('Girokonto'), findsOneWidget);

    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    expect(find.text('Noch nicht verbunden'), findsOneWidget);
    expect(find.text('Pairing noch nicht verfügbar'), findsOneWidget);
  });

  testWidgets('transaction filters separate expenses and income',
      (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Buchungen').last);
    await tester.pumpAndSettle();
    expect(find.text('5 Buchungen · Beispieldaten'), findsOneWidget);

    await tester.tap(find.text('Einnahmen'));
    await tester.pumpAndSettle();
    expect(find.text('1 Buchung · Beispieldaten'), findsOneWidget);
    expect(find.text('Gehalt'), findsOneWidget);
    expect(find.text('REWE'), findsNothing);

    await tester.tap(find.text('Ausgaben'));
    await tester.pumpAndSettle();
    expect(find.text('4 Buchungen · Beispieldaten'), findsOneWidget);
    expect(find.text('Gehalt'), findsNothing);
    expect(find.text('REWE'), findsOneWidget);
  });
}
