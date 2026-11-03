import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';

enum AccountType { checking, savings, creditCard, cash, investment, other }

extension AccountTypeDetails on AccountType {
  String get label => switch (this) {
    AccountType.checking => 'Girokonto',
    AccountType.savings => 'Tagesgeld',
    AccountType.creditCard => 'Kreditkarte',
    AccountType.cash => 'Bargeld',
    AccountType.investment => 'Depot',
    AccountType.other => 'Sonstiges',
  };

  IconData get icon => switch (this) {
    AccountType.checking => Icons.account_balance_rounded,
    AccountType.savings => Icons.savings_outlined,
    AccountType.creditCard => Icons.credit_card_rounded,
    AccountType.cash => Icons.payments_outlined,
    AccountType.investment => Icons.trending_up_rounded,
    AccountType.other => Icons.wallet_outlined,
  };
}

class Account {
  const Account({
    required this.id,
    required this.name,
    required this.institution,
    required this.accountSuffix,
    required this.type,
    required this.balanceCents,
  });

  final String id;
  final String name;
  final String institution;

  /// Only the final four digits are stored, never a full account/card number.
  final String accountSuffix;
  final AccountType type;

  /// Signed integer cents. Negative balances can represent credit-card debt.
  final int balanceCents;

  String get details {
    final parts = <String>[
      if (institution.isNotEmpty) institution,
      if (accountSuffix.isNotEmpty) '•• $accountSuffix',
    ];
    return parts.isEmpty ? 'Manuell erfasst' : parts.join(' · ');
  }

  void validate() {
    if (id.trim().isEmpty || id.length > 80) {
      throw ArgumentError.value(id, 'id', 'Account ID is required.');
    }
    if (name.trim().isEmpty || name.trim().length > 60) {
      throw ArgumentError.value(
        name,
        'name',
        'Account name must contain 1 to 60 characters.',
      );
    }
    if (institution.trim().length > 60) {
      throw ArgumentError.value(
        institution,
        'institution',
        'Institution must not exceed 60 characters.',
      );
    }
    if (accountSuffix.isNotEmpty &&
        !RegExp(r'^\d{4}$').hasMatch(accountSuffix)) {
      throw ArgumentError.value(
        accountSuffix,
        'accountSuffix',
        'Only the final four digits may be stored.',
      );
    }
  }

  Map<String, Object?> toDatabaseMap() => {
    'id': id,
    'name': name.trim(),
    'institution': institution.trim(),
    'account_suffix': accountSuffix,
    'type': type.name,
    'balance_cents': balanceCents,
    'currency': 'EUR',
  };

  factory Account.fromDatabaseMap(Map<String, Object?> map) {
    final typeName = map['type'];
    final type = AccountType.values.where((value) => value.name == typeName);
    final account = Account(
      id: map['id'] as String,
      name: map['name'] as String,
      institution: map['institution'] as String? ?? '',
      accountSuffix: map['account_suffix'] as String? ?? '',
      type: type.isEmpty ? AccountType.other : type.first,
      balanceCents: map['balance_cents'] as int,
    );
    account.validate();
    if (map['currency'] != 'EUR') {
      throw const FormatException('Unsupported account currency.');
    }
    return account;
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Account &&
          other.id == id &&
          other.name == name &&
          other.institution == institution &&
          other.accountSuffix == accountSuffix &&
          other.type == type &&
          other.balanceCents == balanceCents;

  @override
  int get hashCode => Object.hash(
    id,
    name,
    institution,
    accountSuffix,
    type,
    balanceCents,
  );

  Account copyWith({
    String? name,
    String? institution,
    String? accountSuffix,
    AccountType? type,
    int? balanceCents,
  }) {
    return Account(
      id: id,
      name: name ?? this.name,
      institution: institution ?? this.institution,
      accountSuffix: accountSuffix ?? this.accountSuffix,
      type: type ?? this.type,
      balanceCents: balanceCents ?? this.balanceCents,
    );
  }

  static String createId() {
    final random = Random.secure();
    final bytes = List<int>.generate(18, (_) => random.nextInt(256));
    return 'acc-${base64UrlEncode(bytes).replaceAll('=', '')}';
  }
}

const sampleAccounts = <Account>[
  Account(
    id: 'sample-checking',
    name: 'Girokonto',
    institution: 'Musterbank',
    accountSuffix: '4821',
    type: AccountType.checking,
    balanceCents: 248630,
  ),
  Account(
    id: 'sample-savings',
    name: 'Tagesgeld',
    institution: 'Musterbank',
    accountSuffix: '1093',
    type: AccountType.savings,
    balanceCents: 825000,
  ),
  Account(
    id: 'sample-card',
    name: 'Kreditkarte',
    institution: 'Beispiel Visa',
    accountSuffix: '7712',
    type: AccountType.creditCard,
    balanceCents: -32480,
  ),
];
