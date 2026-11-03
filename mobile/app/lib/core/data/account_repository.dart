import 'dart:convert';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_sqlcipher/sqflite.dart';

import 'account.dart';

abstract interface class AccountRepository {
  Future<List<Account>> loadAccounts();

  Future<void> saveAccount(Account account);

  Future<void> deleteAccount(String accountId);
}

abstract interface class SecureValueStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);
}

class FlutterSecureValueStore implements SecureValueStore {
  FlutterSecureValueStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
}

/// Creates one random SQLCipher key and keeps it in platform secure storage.
class SecureAccountEncryptionKeyStore {
  SecureAccountEncryptionKeyStore({required SecureValueStore store})
    : _store = store;

  static const _keyName = 'kassensturz.mobile.accounts.sqlcipher-key.v1';

  final SecureValueStore _store;

  Future<String> getOrCreateKey() async {
    final existing = await _store.read(_keyName);
    if (existing != null) {
      try {
        final decoded = base64Url.decode(base64Url.normalize(existing));
        if (decoded.length != 32) {
          throw const FormatException('Invalid account database key length.');
        }
      } on FormatException {
        throw const FormatException(
          'The stored account database key is invalid. Data was not changed.',
        );
      }
      return existing;
    }

    final random = Random.secure();
    final bytes = List<int>.generate(32, (_) => random.nextInt(256));
    final key = base64UrlEncode(bytes).replaceAll('=', '');
    await _store.write(_keyName, key);
    return key;
  }
}

/// Encrypted local account storage. The database key is never stored alongside
/// the database file and must remain recoverable from platform secure storage.
class SqlCipherAccountRepository implements AccountRepository {
  SqlCipherAccountRepository({
    required SecureAccountEncryptionKeyStore keyStore,
  }) : _keyStore = keyStore;

  final SecureAccountEncryptionKeyStore _keyStore;
  Future<Database>? _databaseFuture;

  Future<Database> _database() async {
    final pending = _databaseFuture ??= _openDatabase();
    try {
      return await pending;
    } catch (_) {
      _databaseFuture = null;
      rethrow;
    }
  }

  Future<Database> _openDatabase() async {
    final key = await _keyStore.getOrCreateKey();
    final databaseDirectory = await getDatabasesPath();
    final databasePath = p.join(databaseDirectory, 'kassensturz_accounts.db');

    return openDatabase(
      databasePath,
      password: key,
      version: 1,
      onConfigure: (database) async {
        await database.execute('PRAGMA secure_delete = ON');
      },
      onCreate: (database, version) async {
        await database.execute('''
          CREATE TABLE accounts (
            id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            institution TEXT NOT NULL DEFAULT '',
            account_suffix TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL,
            balance_cents INTEGER NOT NULL,
            currency TEXT NOT NULL CHECK (currency = 'EUR')
          )
        ''');
      },
    );
  }

  @override
  Future<List<Account>> loadAccounts() async {
    final database = await _database();
    final rows = await database.query(
      'accounts',
      orderBy: 'name COLLATE NOCASE ASC',
    );
    return rows.map(Account.fromDatabaseMap).toList(growable: false);
  }

  @override
  Future<void> saveAccount(Account account) async {
    account.validate();
    final database = await _database();
    await database.insert(
      'accounts',
      account.toDatabaseMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  @override
  Future<void> deleteAccount(String accountId) async {
    final database = await _database();
    await database.delete(
      'accounts',
      where: 'id = ?',
      whereArgs: [accountId],
    );
  }

  Future<void> close() async {
    final pending = _databaseFuture;
    _databaseFuture = null;
    if (pending == null) return;
    try {
      await (await pending).close();
    } catch (_) {
      // An unopened or failed database has nothing to close.
    }
  }
}

/// In-memory repository used by widget tests and the prototype preview.
/// Production startup injects [SqlCipherAccountRepository].
class InMemoryAccountRepository implements AccountRepository {
  InMemoryAccountRepository({List<Account>? initialAccounts})
    : _accounts = List<Account>.from(initialAccounts ?? sampleAccounts);

  List<Account> _accounts;

  @override
  Future<List<Account>> loadAccounts() async =>
      List<Account>.unmodifiable(_accounts);

  @override
  Future<void> saveAccount(Account account) async {
    account.validate();
    final index = _accounts.indexWhere((saved) => saved.id == account.id);
    if (index == -1) {
      _accounts = [..._accounts, account];
    } else {
      _accounts = [
        for (var i = 0; i < _accounts.length; i++)
          if (i == index) account else _accounts[i],
      ];
    }
  }

  @override
  Future<void> deleteAccount(String accountId) async {
    _accounts = _accounts.where((account) => account.id != accountId).toList();
  }
}
