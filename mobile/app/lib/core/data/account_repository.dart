import 'dart:convert';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqlite3/sqlite3.dart';

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

/// Creates one random 256-bit database key and keeps it in platform secure
/// storage (Android Keystore-backed storage / Apple Keychain).
class SecureAccountKeyStore {
  SecureAccountKeyStore({required SecureValueStore store}) : _store = store;

  static const _keyName = 'kassensturz.mobile.accounts.database-key.v1';

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

/// Encrypted SQLite storage using SQLite3MultipleCiphers in SQLCipher
/// compatibility mode. The random database key is kept separately in
/// platform secure storage and is never written beside the database file.
class EncryptedAccountRepository implements AccountRepository {
  EncryptedAccountRepository({
    required SecureAccountKeyStore keyStore,
    Future<String> Function()? databasePathProvider,
  }) : _keyStore = keyStore,
       _databasePathProvider = databasePathProvider;

  final SecureAccountKeyStore _keyStore;
  final Future<String> Function()? _databasePathProvider;
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
    final keyBytes = base64Url.decode(base64Url.normalize(key));
    final keyHex = keyBytes
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    final directoryPath = _databasePathProvider == null
        ? (await getApplicationSupportDirectory()).path
        : await _databasePathProvider!();
    final databasePath = p.join(directoryPath, 'kassensturz_accounts.db');
    final database = sqlite3.open(databasePath);

    try {
      if (database.select('PRAGMA cipher;').isEmpty) {
        throw StateError(
          'Encrypted SQLite support is unavailable. The database was not used.',
        );
      }

      database
        ..execute("PRAGMA cipher = 'sqlcipher';")
        ..execute('PRAGMA legacy = 4;')
        ..execute('PRAGMA key = "x\'$keyHex\'";');

      // Reading the schema forces SQLite to verify the key before any
      // application data can be read or modified.
      database.select('SELECT count(*) FROM sqlite_master;');
      database.execute('PRAGMA secure_delete = ON;');

      if (database.userVersion == 0) {
        database.execute('''
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
        database.userVersion = 1;
      } else if (database.userVersion != 1) {
        throw FormatException(
          'Unsupported account database version: ${database.userVersion}.',
        );
      }

      return database;
    } catch (_) {
      database.dispose();
      rethrow;
    }
  }

  @override
  Future<List<Account>> loadAccounts() async {
    final database = await _database();
    final rows = database.select(
      'SELECT id, name, institution, account_suffix, type, '
      'balance_cents, currency FROM accounts '
      'ORDER BY name COLLATE NOCASE ASC',
    );
    return rows
        .map((row) => Account.fromDatabaseMap(Map<String, Object?>.from(row)))
        .toList(growable: false);
  }

  @override
  Future<void> saveAccount(Account account) async {
    account.validate();
    final database = await _database();
    final values = account.toDatabaseMap();
    database.execute(
      'INSERT OR REPLACE INTO accounts '
      '(id, name, institution, account_suffix, type, balance_cents, currency) '
      'VALUES (?, ?, ?, ?, ?, ?, ?)',
      [
        values['id'],
        values['name'],
        values['institution'],
        values['account_suffix'],
        values['type'],
        values['balance_cents'],
        values['currency'],
      ],
    );
  }

  @override
  Future<void> deleteAccount(String accountId) async {
    final database = await _database();
    database.execute('DELETE FROM accounts WHERE id = ?', [accountId]);
  }

  Future<void> close() async {
    final pending = _databaseFuture;
    _databaseFuture = null;
    if (pending == null) return;
    try {
      (await pending).dispose();
    } catch (_) {
      // An unopened or failed database has no live connection to close.
    }
  }
}

/// In-memory repository used by widget tests and the prototype preview.
/// Production startup injects [EncryptedAccountRepository].
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
