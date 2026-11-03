import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'demo_finance_data.dart';

abstract interface class BudgetRepository {
  Future<Map<String, double>> loadLimits();

  Future<void> saveLimits(Map<String, double> limits);
}

abstract interface class StringKeyValueStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);
}

class SharedPreferencesStringKeyValueStore implements StringKeyValueStore {
  SharedPreferencesStringKeyValueStore({SharedPreferencesAsync? preferences})
      : _preferences = preferences ?? SharedPreferencesAsync();

  final SharedPreferencesAsync _preferences;

  @override
  Future<String?> read(String key) => _preferences.getString(key);

  @override
  Future<void> write(String key, String value) =>
      _preferences.setString(key, value);
}

/// Stores only budget limits. Never use this lightweight store for credentials
/// or authoritative banking data.
class LocalBudgetRepository implements BudgetRepository {
  LocalBudgetRepository({required StringKeyValueStore store}) : _store = store;

  static const _storageKey = 'kassensturz.mobile.budget-limits.v1';
  static const _schemaVersion = 1;

  final StringKeyValueStore _store;

  static final Set<String> _allowedCategoryIds = DemoFinanceData.categories
      .where((category) => category.id != 'housing' && category.id != 'income')
      .map((category) => category.id)
      .toSet();

  @override
  Future<Map<String, double>> loadLimits() async {
    final raw = await _store.read(_storageKey);
    if (raw == null) {
      return Map<String, double>.from(DemoFinanceData.defaultBudgetLimits);
    }

    final decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic> ||
        decoded['version'] != _schemaVersion ||
        decoded['limits'] is! Map<String, dynamic>) {
      throw const FormatException('Unsupported budget storage format.');
    }

    final rawLimits = decoded['limits'] as Map<String, dynamic>;
    final limits = <String, double>{};
    for (final entry in rawLimits.entries) {
      final value = entry.value;
      if (value is! num || !value.isFinite || value <= 0) {
        throw const FormatException('Invalid budget limit in local storage.');
      }
      _validateCategory(entry.key);
      limits[entry.key] = value.toDouble();
    }
    return limits;
  }

  @override
  Future<void> saveLimits(Map<String, double> limits) async {
    for (final entry in limits.entries) {
      _validateCategory(entry.key);
      if (!entry.value.isFinite || entry.value <= 0) {
        throw ArgumentError.value(
          entry.value,
          entry.key,
          'Budget limits must be finite and greater than zero.',
        );
      }
    }

    final payload = jsonEncode({
      'version': _schemaVersion,
      'limits': limits,
    });
    await _store.write(_storageKey, payload);
  }

  static void _validateCategory(String categoryId) {
    if (!_allowedCategoryIds.contains(categoryId)) {
      throw ArgumentError.value(
        categoryId,
        'categoryId',
        'Category cannot have a variable spending budget.',
      );
    }
  }
}

/// In-memory repository for widget previews and tests. Production uses the
/// SharedPreferences-backed repository passed from main.dart.
class InMemoryBudgetRepository implements BudgetRepository {
  InMemoryBudgetRepository({
    Map<String, double>? initialLimits,
  }) : _limits = Map<String, double>.from(
          initialLimits ?? DemoFinanceData.defaultBudgetLimits,
        );

  Map<String, double> _limits;

  @override
  Future<Map<String, double>> loadLimits() async =>
      Map<String, double>.from(_limits);

  @override
  Future<void> saveLimits(Map<String, double> limits) async {
    _limits = Map<String, double>.from(limits);
  }
}
