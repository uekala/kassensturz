import 'package:flutter/foundation.dart';

import 'budget_repository.dart';
import 'demo_finance_data.dart';

class BudgetController extends ChangeNotifier {
  BudgetController({required BudgetRepository repository})
    : _repository = repository,
      _limits = Map<String, double>.from(DemoFinanceData.defaultBudgetLimits);

  final BudgetRepository _repository;
  Map<String, double> _limits;
  bool _isLoading = true;
  bool _isSaving = false;
  Object? _loadError;
  Object? _saveError;

  Map<String, double> get limits => Map<String, double>.unmodifiable(_limits);
  bool get isLoading => _isLoading;
  bool get isSaving => _isSaving;
  Object? get loadError => _loadError;
  Object? get saveError => _saveError;

  Future<void> load() async {
    _isLoading = true;
    _loadError = null;
    notifyListeners();

    try {
      final savedLimits = await _repository.loadLimits();
      _limits = Map<String, double>.from(savedLimits);
    } catch (error) {
      _loadError = error;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> saveLimits(Map<String, double> nextLimits) async {
    if (_isSaving) return false;

    final previousLimits = _limits;
    _limits = Map<String, double>.from(nextLimits);
    _isSaving = true;
    _saveError = null;
    notifyListeners();

    try {
      await _repository.saveLimits(_limits);
      return true;
    } catch (error) {
      _limits = previousLimits;
      _saveError = error;
      return false;
    } finally {
      _isSaving = false;
      notifyListeners();
    }
  }
}
