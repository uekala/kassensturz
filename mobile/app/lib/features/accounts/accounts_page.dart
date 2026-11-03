import 'package:flutter/material.dart';

class AccountsPage extends StatelessWidget {
  const AccountsPage({super.key});

  static const _accounts = [
    _Account(
      'Girokonto',
      'Musterbank · •• 4821',
      '2.486,30 €',
      Icons.account_balance_rounded,
      'Giro',
    ),
    _Account(
      'Tagesgeld',
      'Musterbank · •• 1093',
      '8.250,00 €',
      Icons.savings_outlined,
      'Sparen',
    ),
    _Account(
      'Kreditkarte',
      'Beispiel Visa · •• 7712',
      '−324,80 €',
      Icons.credit_card_rounded,
      'Kredit',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(
          'Deine Konten',
          style: textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          'Alle Kontostände an einem Ort.',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: const Color(0xFF104E46),
            borderRadius: BorderRadius.circular(18),
          ),
          child: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Gesamtsaldo · Beispieldaten',
                style: TextStyle(color: Colors.white70, fontSize: 12),
              ),
              SizedBox(height: 7),
              Text(
                '10.411,50 €',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 27,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.8,
                ),
              ),
              SizedBox(height: 3),
              Text(
                '3 Beispielkonten',
                style: TextStyle(color: Colors.white70, fontSize: 11),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Text(
          'DEINE KONTEN',
          style: textTheme.labelSmall?.copyWith(
            color: colors.onSurfaceVariant,
            fontWeight: FontWeight.w800,
            letterSpacing: 1,
          ),
        ),
        const SizedBox(height: 9),
        ..._accounts.map((account) => _AccountCard(account)),
      ],
    );
  }
}

class _AccountCard extends StatelessWidget {
  const _AccountCard(this.account);

  final _Account account;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Container(
      margin: const EdgeInsets.only(bottom: 9),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(
          color: colors.outlineVariant.withValues(alpha: 0.35),
        ),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        leading: CircleAvatar(
          backgroundColor: colors.primaryContainer,
          foregroundColor: colors.onPrimaryContainer,
          child: Icon(account.icon, size: 20),
        ),
        title: Text(
          account.name,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
        ),
        subtitle: Text(account.details, style: const TextStyle(fontSize: 11)),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              account.balance,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12),
            ),
            const SizedBox(height: 3),
            Text(
              account.type,
              style: TextStyle(color: colors.onSurfaceVariant, fontSize: 10),
            ),
          ],
        ),
      ),
    );
  }
}

class _Account {
  const _Account(this.name, this.details, this.balance, this.icon, this.type);

  final String name;
  final String details;
  final String balance;
  final IconData icon;
  final String type;
}
