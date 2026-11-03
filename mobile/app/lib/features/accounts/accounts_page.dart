import 'package:flutter/material.dart';

class AccountsPage extends StatelessWidget {
  const AccountsPage({super.key});

  static const _accounts = [
    _Account('Girokonto', 'Musterbank · •• 4821', '2.486,30 €', Icons.account_balance_rounded),
    _Account('Tagesgeld', 'Musterbank · •• 1093', '8.250,00 €', Icons.savings_outlined),
    _Account('Kreditkarte', 'Beispiel Visa · •• 7712', '−324,80 €', Icons.credit_card_rounded),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(
          'Deine Konten',
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 6),
        Text(
          'Beispielhafte Kontenübersicht',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        ..._accounts.map(
          (account) => Card(
            elevation: 0,
            color: Colors.white,
            margin: const EdgeInsets.only(bottom: 10),
            child: ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: CircleAvatar(
                backgroundColor: colors.primaryContainer,
                foregroundColor: colors.onPrimaryContainer,
                child: Icon(account.icon),
              ),
              title: Text(account.name, style: const TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(account.details),
              trailing: Text(account.balance, style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
          ),
        ),
      ],
    );
  }
}

class _Account {
  const _Account(this.name, this.details, this.balance, this.icon);

  final String name;
  final String details;
  final String balance;
  final IconData icon;
}
