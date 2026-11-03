import 'package:flutter/foundation.dart';

import 'account.dart';
import 'account_repository.dart';

class AccountController extends ChangeNotifier {
  AccountController({required AccountRepository repository})
    : _repository = repository;

  final AccountRepository _repository;
  List<Account> _accounts = const [];
  bool _isLoading = true;
  bool _isSaving = false;
  Object? _loadError;
  Object? _operationError;

  List<Account> get accounts => List<Account>.unmodifiable(_accounts);
  bool get isLoading => _isLoading;
  bool get isSaving => _isSaving;
  Object? get loadError => _loadError;
  Object? get operationError => _operationError;

  int get totalBalanceCents =>
      _accounts.fold(0, (total, account) => total + account.balanceCents);

  Future<void> load() async {
    _isLoading = true;
    _loadError = null;
    notifyListeners();

    try {
      _accounts = await _repository.loadAccounts();
    } catch (error) {
      _loadError = error;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> save(Account account) async {
    if (_isSaving) return false;

    _isSaving = true;
    _operationError = null;
    notifyListeners();
    try {
      await _repository.saveAccount(account);
      final index = _accounts.indexWhere((saved) => saved.id == account.id);
      if (index == -1) {
        _accounts = [..._accounts, account];
      } else {
        _accounts = [
          for (var i = 0; i < _accounts.length; i++)
            if (i == index) account else _accounts[i],
        ];
      }
      return true;
    } catch (error) {
      _operationError = error;
      return false;
    } finally {
      _isSaving = false;
      notifyListeners();
    }
  }

  Future<bool> delete(String accountId) async {
    if (_isSaving) return false;

    _isSaving = true;
    _operationError = null;
    notifyListeners();
    try {
      await _repository.deleteAccount(accountId);
      _accounts = _accounts
          .where((account) => account.id != accountId)
          .toList(growable: false);
      return true;
    } catch (error) {
      _operationError = error;
      return false;
    } finally {
      _isSaving = false;
      notifyListeners();
    }
  }
}
