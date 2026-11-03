import 'package:flutter/material.dart';

class TransactionsPage extends StatelessWidget {
  const TransactionsPage({super.key});

  static const _transactions = [
    _Transaction('REWE', 'Lebensmittel · 03.11.2026', '−48,26 €',
        Icons.shopping_basket_outlined, true),
    _Transaction(
        'Miete', 'Wohnen · 02.11.2026', '−980,00 €', Icons.home_outlined, true),
    _Transaction('Gehalt', 'Einkommen · 01.11.2026', '+2.750,00 €',
        Icons.payments_outlined, false),
    _Transaction('LIDL', 'Lebensmittel · 31.10.2026', '−32,14 €',
        Icons.shopping_cart_outlined, true),
    _Transaction('Stadtwerke', 'Versorger · 30.10.2026', '−86,00 €',
        Icons.bolt_outlined, true),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(
          'Buchungen',
          style: Theme.of(context)
              .textTheme
              .headlineSmall
              ?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 6),
        Text(
          'Deine letzten Buchungen im Überblick.',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 14),
        ..._transactions.map(
          (transaction) => ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 2),
            leading: CircleAvatar(
              backgroundColor: colors.secondaryContainer,
              foregroundColor: colors.onSecondaryContainer,
              child: Icon(transaction.icon, size: 20),
            ),
            title: Text(transaction.title,
                style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(transaction.subtitle),
            trailing: Text(
              transaction.amount,
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color:
                    transaction.isExpense ? colors.onSurface : colors.primary,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _Transaction {
  const _Transaction(
      this.title, this.subtitle, this.amount, this.icon, this.isExpense);

  final String title;
  final String subtitle;
  final String amount;
  final IconData icon;
  final bool isExpense;
}
