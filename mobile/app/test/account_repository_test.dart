import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/data/account.dart';
import 'package:kassensturz_mobile/core/data/account_repository.dart';

void main() {
  group('Account model', () {
    test('round-trips its database representation without floating point', () {
      const account = Account(
        id: 'acc-test',
        name: 'Girokonto',
        institution: 'Musterbank',
        accountSuffix: '4821',
        type: AccountType.checking,
        balanceCents: -32480,
      );

      expect(Account.fromDatabaseMap(account.toDatabaseMap()), account);
      expect(account.balanceCents, -32480);
    });

    test('rejects full account numbers instead of storing them', () {
      const account = Account(
        id: 'acc-test',
        name: 'Girokonto',
        institution: '',
        accountSuffix: '123456789',
        type: AccountType.checking,
        balanceCents: 0,
      );

      expect(account.validate, throwsArgumentError);
    });

    test('rejects blank account names', () {
      const account = Account(
        id: 'acc-test',
        name: ' ',
        institution: '',
        accountSuffix: '',
        type: AccountType.checking,
        balanceCents: 0,
      );

      expect(account.validate, throwsArgumentError);
    });
  });

  group('SecureAccountKeyStore', () {
    test('creates a random 256-bit key and reuses it', () async {
      final store = FakeSecureValueStore();
      final keyStore = SecureAccountKeyStore(store: store);

      final first = await keyStore.getOrCreateKey();
      final second = await keyStore.getOrCreateKey();

      expect(base64Url.decode(base64Url.normalize(first)), hasLength(32));
      expect(second, first);
      expect(store.values, hasLength(1));
    });

    test('does not replace an invalid existing key', () async {
      final store = FakeSecureValueStore()
        ..values['kassensturz.mobile.accounts.database-key.v1'] = 'invalid';
      final keyStore = SecureAccountKeyStore(store: store);

      await expectLater(keyStore.getOrCreateKey(), throwsFormatException);
      expect(
        store.values['kassensturz.mobile.accounts.database-key.v1'],
        'invalid',
      );
    });
  });

  group('InMemoryAccountRepository', () {
    test('adds, updates and deletes accounts', () async {
      final repository = InMemoryAccountRepository(initialAccounts: const []);
      const account = Account(
        id: 'acc-custom',
        name: 'Reisekonto',
        institution: 'Musterbank',
        accountSuffix: '1234',
        type: AccountType.savings,
        balanceCents: 125050,
      );

      await repository.saveAccount(account);
      expect(await repository.loadAccounts(), [account]);

      await repository.saveAccount(
        account.copyWith(name: 'Urlaubskonto', balanceCents: 90000),
      );
      final updated = (await repository.loadAccounts()).single;
      expect(updated.name, 'Urlaubskonto');
      expect(updated.balanceCents, 90000);

      await repository.deleteAccount(account.id);
      expect(await repository.loadAccounts(), isEmpty);
    });

    test('returns an immutable account list', () async {
      final repository = InMemoryAccountRepository();

      final accounts = await repository.loadAccounts();

      expect(() => accounts.clear(), throwsUnsupportedError);
    });
  });
}

class FakeSecureValueStore implements SecureValueStore {
  final Map<String, String> values = {};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }
}
