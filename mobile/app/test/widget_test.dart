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

  testWidgets('dashboard budget card opens the budget tab', (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.scrollUntilVisible(
      find.text('Variable Ausgaben'),
      180,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Variable Ausgaben'));
    await tester.pumpAndSettle();

    expect(find.text('Deine Budgets'), findsOneWidget);
    expect(find.text('620,40 €'), findsOneWidget);
  });

  testWidgets('bottom navigation opens accounts, budget and settings',
      (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Konten').last);
    await tester.pumpAndSettle();
    expect(find.text('Gesamtsaldo · Beispieldaten'), findsOneWidget);
    expect(find.text('Girokonto'), findsOneWidget);

    await tester.tap(find.text('Budget').last);
    await tester.pumpAndSettle();
    expect(find.text('1.000,00 €'), findsOneWidget);
    expect(find.text('Lebensmittel'), findsOneWidget);

    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    expect(find.text('Noch nicht verbunden'), findsOneWidget);
    expect(find.text('Pairing noch nicht verfügbar'), findsOneWidget);
  });

  testWidgets('budget month selection updates the shown figures',
      (tester) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Budget').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Oktober 2026'));
    await tester.pumpAndSettle();

    expect(find.text('512,30 €'), findsOneWidget);
    expect(find.text('487,70 €'), findsOneWidget);
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
