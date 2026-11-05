import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/data/budget_repository.dart';
import 'package:kassensturz_mobile/core/data/demo_finance_data.dart';

void main() {
  group('LocalBudgetRepository', () {
    test('returns the documented defaults when no local data exists', () async {
      final repository = LocalBudgetRepository(
        store: FakeStringKeyValueStore(),
      );

      final limits = await repository.loadLimits();

      expect(limits, equals(DemoFinanceData.defaultBudgetLimits));
    });

    test('round-trips limits across repository instances', () async {
      final store = FakeStringKeyValueStore();
      final firstRepository = LocalBudgetRepository(store: store);
      final updatedLimits = <String, double>{
        'food': 425,
        'mobility': 180,
        'health': 75.50,
      };

      await firstRepository.saveLimits(updatedLimits);
      final secondRepository = LocalBudgetRepository(store: store);

      expect(await secondRepository.loadLimits(), updatedLimits);
    });

    test('rejects categories that cannot have variable budgets', () async {
      final repository = LocalBudgetRepository(
        store: FakeStringKeyValueStore(),
      );

      await expectLater(
        repository.saveLimits({'income': 1000}),
        throwsArgumentError,
      );
    });

    test('rejects invalid or non-positive limits', () async {
      final repository = LocalBudgetRepository(
        store: FakeStringKeyValueStore(),
      );

      await expectLater(
        repository.saveLimits({'food': 0}),
        throwsArgumentError,
      );
      await expectLater(
        repository.saveLimits({'food': double.infinity}),
        throwsArgumentError,
      );
    });

    test('does not silently replace corrupted stored data', () async {
      final store = FakeStringKeyValueStore()
        ..values['kassensturz.mobile.budget-limits.v1'] = '{broken';
      final repository = LocalBudgetRepository(store: store);

      await expectLater(repository.loadLimits(), throwsFormatException);
    });
  });
}

class FakeStringKeyValueStore implements StringKeyValueStore {
  final Map<String, String> values = {};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }
}
