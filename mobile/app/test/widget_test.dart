import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';
import 'package:kassensturz_mobile/core/data/budget_repository.dart';

void _useTallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 1800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  testWidgets('shows prototype dashboard and demo status by default', (
    tester,
  ) async {
    await tester.pumpWidget(const KassensturzApp());

    expect(
      find.text('Beispieldaten – noch nicht mit deinem Server verbunden'),
      findsOneWidget,
    );
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
    expect(find.text('10 Buchungen · Beispieldaten'), findsOneWidget);
  });

  testWidgets('dashboard budget card uses calculated transaction totals', (
    tester,
  ) async {
    await tester.pumpWidget(const KassensturzApp());
    await tester.pumpAndSettle();

    expect(find.text('886,74 €'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Variable Ausgaben'),
      180,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('11 % genutzt'), findsOneWidget);
    expect(find.text('113,26 € ausgegeben'), findsOneWidget);
  });

  testWidgets(
    'dashboard hides fallback budget totals when local storage fails',
    (tester) async {
      await tester.pumpWidget(
        KassensturzApp(budgetRepository: _FailingBudgetRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('Nicht verfügbar'), findsWidgets);
      expect(find.text('886,74 €'), findsNothing);

      await tester.scrollUntilVisible(
        find.text('Variable Ausgaben'),
        180,
        scrollable: find.byType(Scrollable).first,
      );
      expect(
        find.text('Budgetinformationen können derzeit nicht angezeigt werden.'),
        findsOneWidget,
      );
      expect(find.text('113,26 € ausgegeben'), findsNothing);
    },
  );

  testWidgets('bottom navigation opens accounts, budget and settings', (
    tester,
  ) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Konten').last);
    await tester.pumpAndSettle();
    expect(find.text('Gesamtsaldo · Beispieldaten'), findsOneWidget);
    expect(find.text('Girokonto'), findsOneWidget);

    await tester.tap(find.text('Budget').last);
    await tester.pumpAndSettle();
    expect(find.text('1.000,00 €'), findsOneWidget);
    expect(find.text('Lebensmittel'), findsOneWidget);
    expect(find.text('113,26 €'), findsOneWidget);

    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    expect(find.text('Noch nicht verbunden'), findsOneWidget);
    expect(find.text('Pairing noch nicht verfügbar'), findsOneWidget);
  });

  testWidgets(
    'budget month selection recalculates spending from transactions',
    (tester) async {
      await tester.pumpWidget(const KassensturzApp());

      await tester.tap(find.text('Budget').last);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Oktober 2026'));
      await tester.pumpAndSettle();

      expect(find.text('202,14 €'), findsOneWidget);
      expect(find.text('797,86 €'), findsOneWidget);
    },
  );

  testWidgets('can add a budget for a previously unbudgeted category', (
    tester,
  ) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Budget').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Oktober 2026'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Hinzufügen'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField), '100');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();

    expect(find.text('Gesundheit'), findsOneWidget);
    expect(find.text('1.100,00 €'), findsOneWidget);
    expect(find.text('18,70 €'), findsOneWidget);
  });

  testWidgets('can edit an existing budget limit', (tester) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Budget').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Budget bearbeiten: Lebensmittel'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField), '400');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();

    expect(find.text('1.050,00 €'), findsOneWidget);
  });

  testWidgets('can delete a budget category', (tester) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Budget').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Budget löschen: Lebensmittel'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Löschen'));
    await tester.pumpAndSettle();

    expect(find.text('Lebensmittel'), findsNothing);
    expect(find.text('650,00 €'), findsOneWidget);
  });

  testWidgets(
    'budget limits survive recreating the app with the same repository',
    (tester) async {
      _useTallViewport(tester);
      final repository = InMemoryBudgetRepository();

      await tester.pumpWidget(KassensturzApp(budgetRepository: repository));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Budget').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Budget bearbeiten: Lebensmittel'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField), '425');
      await tester.tap(find.text('Speichern'));
      await tester.pumpAndSettle();

      expect(find.text('1.075,00 €'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(KassensturzApp(budgetRepository: repository));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Budget').last);
      await tester.pumpAndSettle();
      expect(find.text('1.075,00 €'), findsOneWidget);
      expect(find.text('von 425,00 €'), findsOneWidget);
    },
  );

  testWidgets('transaction filters use shared demo transaction data', (
    tester,
  ) async {
    await tester.pumpWidget(const KassensturzApp());

    await tester.tap(find.text('Buchungen').last);
    await tester.pumpAndSettle();
    expect(find.text('10 Buchungen · Beispieldaten'), findsOneWidget);

    await tester.tap(find.text('Einnahmen'));
    await tester.pumpAndSettle();
    expect(find.text('1 Buchung · Beispieldaten'), findsOneWidget);
    expect(find.text('Gehalt'), findsOneWidget);
    expect(find.text('REWE'), findsNothing);

    await tester.tap(find.text('Ausgaben'));
    await tester.pumpAndSettle();
    expect(find.text('9 Buchungen · Beispieldaten'), findsOneWidget);
    expect(find.text('Gehalt'), findsNothing);
    expect(find.text('REWE'), findsOneWidget);
  });
}

class _FailingBudgetRepository implements BudgetRepository {
  @override
  Future<Map<String, double>> loadLimits() async {
    throw const FormatException('Corrupted local budget data');
  }

  @override
  Future<void> saveLimits(Map<String, double> limits) async {
    throw StateError('Local storage is unavailable');
  }
}
