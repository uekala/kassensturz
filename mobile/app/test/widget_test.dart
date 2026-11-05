import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';
import 'package:kassensturz_mobile/core/data/account_repository.dart';
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
    expect(find.text('+1.656,74 €'), findsOneWidget);
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
    expect(find.text('10 Buchungen'), findsOneWidget);
  });

  testWidgets('dashboard budget card uses calculated transaction totals', (
    tester,
  ) async {
    await tester.pumpWidget(const KassensturzApp());
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Variable Ausgaben'),
      180,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('886,74 € noch verfügbar'), findsOneWidget);
    expect(find.text('11 %'), findsOneWidget);
    expect(find.text('113,26 € ausgegeben'), findsOneWidget);
  });

  testWidgets(
    'dashboard hides fallback budget totals when local storage fails',
    (tester) async {
      await tester.pumpWidget(
        KassensturzApp(budgetRepository: _FailingBudgetRepository()),
      );
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Variable Ausgaben'),
        180,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Nicht verfügbar'), findsOneWidget);
      expect(find.text('886,74 € noch verfügbar'), findsNothing);
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
    expect(find.text('Gesamtsaldo · manuell erfasst'), findsOneWidget);
    expect(find.text('Girokonto'), findsWidgets);

    await tester.tap(find.text('Budget').last);
    await tester.pumpAndSettle();
    expect(find.text('1.000,00 €'), findsOneWidget);
    expect(find.text('Lebensmittel'), findsOneWidget);
    expect(find.text('113,26 €'), findsOneWidget);

    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    expect(find.text('Noch nicht verbunden'), findsOneWidget);
    expect(find.text('Einmaliger Pairing-Code'), findsOneWidget);
    expect(find.text('Gerät sicher koppeln'), findsOneWidget);
    expect(find.text('https://dein-server.ts.net'), findsOneWidget);
    expect(find.text('Server prüfen'), findsOneWidget);
  });

  testWidgets(
    'accounts can be created, edited, persisted and deleted locally',
    (tester) async {
      _useTallViewport(tester);
      final repository = InMemoryAccountRepository(initialAccounts: const []);

      await tester.pumpWidget(KassensturzApp(accountRepository: repository));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Konten').last);
      await tester.pumpAndSettle();

      expect(find.text('Noch keine Konten angelegt'), findsOneWidget);
      await tester.tap(find.text('Erstes Konto anlegen'));
      await tester.pumpAndSettle();

      var fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'Reisekonto');
      await tester.enterText(fields.at(1), 'Hausbank');
      await tester.enterText(fields.at(2), '1234');
      await tester.enterText(fields.at(3), '1234,56');
      await tester.tap(find.text('Speichern').last);
      await tester.pumpAndSettle();

      expect(find.text('Reisekonto'), findsOneWidget);
      expect(find.text('1.234,56 €'), findsWidgets);
      expect(find.text('Hausbank · •• 1234'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(KassensturzApp(accountRepository: repository));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Konten').last);
      await tester.pumpAndSettle();

      expect(find.text('Reisekonto'), findsOneWidget);
      expect(find.text('1.234,56 €'), findsWidgets);

      await tester.tap(find.byTooltip('Aktionen für Reisekonto'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Bearbeiten'));
      await tester.pumpAndSettle();

      fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'Urlaubskonto');
      await tester.enterText(fields.at(3), '900,00');
      await tester.tap(find.text('Speichern').last);
      await tester.pumpAndSettle();

      expect(find.text('Urlaubskonto'), findsOneWidget);
      expect(find.text('900,00 €'), findsWidgets);
      expect(find.text('Reisekonto'), findsNothing);

      await tester.tap(find.byTooltip('Aktionen für Urlaubskonto'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Löschen').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Löschen').last);
      await tester.pumpAndSettle();

      expect(find.text('Noch keine Konten angelegt'), findsOneWidget);
      expect(find.text('Urlaubskonto'), findsNothing);
    },
  );

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
    expect(find.text('10 Buchungen'), findsOneWidget);

    await tester.tap(find.text('Einnahmen'));
    await tester.pumpAndSettle();
    expect(find.text('1 Buchung'), findsOneWidget);
    expect(find.text('Gehalt'), findsOneWidget);
    expect(find.text('REWE'), findsNothing);

    await tester.tap(find.text('Ausgaben'));
    await tester.pumpAndSettle();
    expect(find.text('9 Buchungen'), findsOneWidget);
    expect(find.text('Gehalt'), findsNothing);
    expect(find.text('REWE'), findsOneWidget);
  });

  testWidgets('pairing form requires HTTPS server URL and a one-time code', (
    tester,
  ) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());
    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Gerät sicher koppeln'));
    await tester.pumpAndSettle();

    expect(
      find.text('Bitte eine gültige HTTPS-Adresse eingeben.'),
      findsOneWidget,
    );
    expect(find.text('Der Pairing-Code ist ungültig.'), findsOneWidget);
    expect(find.text('OFFLINE'), findsOneWidget);
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
