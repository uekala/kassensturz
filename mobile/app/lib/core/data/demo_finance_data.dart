import 'package:flutter/material.dart';

class DemoCategory {
  const DemoCategory({
    required this.id,
    required this.name,
    required this.icon,
    required this.color,
  });

  final String id;
  final String name;
  final IconData icon;
  final Color color;
}

class DemoTransaction {
  const DemoTransaction({
    required this.id,
    required this.title,
    required this.date,
    required this.categoryId,
    required this.amount,
    required this.icon,
  });

  final String id;
  final String title;
  final DateTime date;
  final String categoryId;

  /// Expenses are negative; income is positive.
  final double amount;
  final IconData icon;

  bool get isExpense => amount < 0;
}

class DemoFinanceData {
  DemoFinanceData._();

  static const categories = <DemoCategory>[
    DemoCategory(
      id: 'food',
      name: 'Lebensmittel',
      icon: Icons.shopping_basket_outlined,
      color: Color(0xFF20836F),
    ),
    DemoCategory(
      id: 'mobility',
      name: 'Mobilität',
      icon: Icons.directions_car_outlined,
      color: Color(0xFF526A9B),
    ),
    DemoCategory(
      id: 'leisure',
      name: 'Freizeit',
      icon: Icons.sports_esports_outlined,
      color: Color(0xFF9A6A35),
    ),
    DemoCategory(
      id: 'household',
      name: 'Haushalt',
      icon: Icons.chair_outlined,
      color: Color(0xFF8065A5),
    ),
    DemoCategory(
      id: 'other',
      name: 'Sonstiges',
      icon: Icons.more_horiz_rounded,
      color: Color(0xFF64736F),
    ),
    DemoCategory(
      id: 'health',
      name: 'Gesundheit',
      icon: Icons.local_pharmacy_outlined,
      color: Color(0xFFB15D67),
    ),
    DemoCategory(
      id: 'housing',
      name: 'Wohnen',
      icon: Icons.home_outlined,
      color: Color(0xFF7B8580),
    ),
    DemoCategory(
      id: 'income',
      name: 'Einkommen',
      icon: Icons.payments_outlined,
      color: Color(0xFF20836F),
    ),
  ];

  static const defaultBudgetLimits = <String, double>{
    'food': 350,
    'mobility': 200,
    'leisure': 150,
    'household': 100,
    'other': 200,
  };

  static const transactions = <DemoTransaction>[
    DemoTransaction(
      id: 'tx-001',
      title: 'REWE',
      date: DateTime(2026, 11, 3),
      categoryId: 'food',
      amount: -48.26,
      icon: Icons.shopping_basket_outlined,
    ),
    DemoTransaction(
      id: 'tx-002',
      title: 'Shell',
      date: DateTime(2026, 11, 2),
      categoryId: 'mobility',
      amount: -65,
      icon: Icons.local_gas_station_outlined,
    ),
    DemoTransaction(
      id: 'tx-003',
      title: 'Miete',
      date: DateTime(2026, 11, 2),
      categoryId: 'housing',
      amount: -980,
      icon: Icons.home_outlined,
    ),
    DemoTransaction(
      id: 'tx-004',
      title: 'Gehalt',
      date: DateTime(2026, 11, 1),
      categoryId: 'income',
      amount: 2750,
      icon: Icons.payments_outlined,
    ),
    DemoTransaction(
      id: 'tx-005',
      title: 'LIDL',
      date: DateTime(2026, 10, 31),
      categoryId: 'food',
      amount: -32.14,
      icon: Icons.shopping_cart_outlined,
    ),
    DemoTransaction(
      id: 'tx-006',
      title: 'Stadtwerke',
      date: DateTime(2026, 10, 30),
      categoryId: 'household',
      amount: -86,
      icon: Icons.bolt_outlined,
    ),
    DemoTransaction(
      id: 'tx-007',
      title: 'Fitnessstudio',
      date: DateTime(2026, 10, 28),
      categoryId: 'leisure',
      amount: -29.90,
      icon: Icons.fitness_center_outlined,
    ),
    DemoTransaction(
      id: 'tx-008',
      title: 'Apotheke',
      date: DateTime(2026, 10, 27),
      categoryId: 'health',
      amount: -18.70,
      icon: Icons.local_pharmacy_outlined,
    ),
    DemoTransaction(
      id: 'tx-009',
      title: 'Café',
      date: DateTime(2026, 10, 25),
      categoryId: 'leisure',
      amount: -12.50,
      icon: Icons.local_cafe_outlined,
    ),
    DemoTransaction(
      id: 'tx-010',
      title: 'Edeka',
      date: DateTime(2026, 10, 24),
      categoryId: 'food',
      amount: -41.60,
      icon: Icons.shopping_basket_outlined,
    ),
  ];

  static DemoCategory category(String id) {
    return categories.firstWhere((category) => category.id == id);
  }

  static double spentForCategory(String categoryId, DateTime month) {
    return transactions
        .where(
          (transaction) =>
              transaction.isExpense &&
              transaction.categoryId == categoryId &&
              transaction.date.year == month.year &&
              transaction.date.month == month.month,
        )
        .fold<double>(
          0,
          (total, transaction) => total + transaction.amount.abs(),
        );
  }

  static double totalBudget(Map<String, double> limits) {
    return limits.values.fold<double>(0, (total, limit) => total + limit);
  }

  static double spentForBudgets(
    DateTime month,
    Map<String, double> limits,
  ) {
    return limits.keys.fold<double>(
      0,
      (total, categoryId) => total + spentForCategory(categoryId, month),
    );
  }

  static double remainingBudget(DateTime month, Map<String, double> limits) {
    return totalBudget(limits) - spentForBudgets(month, limits);
  }
}

String formatEuro(double value) {
  final parts = value.abs().toStringAsFixed(2).split('.');
  final whole = parts[0].replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => '.',
  );
  return '$whole,${parts[1]} €';
}

String formatSignedEuro(double value) {
  final sign = value < 0 ? '−' : '+';
  return '$sign${formatEuro(value.abs())}';
}

String formatDemoDate(DateTime date) {
  final day = date.day.toString().padLeft(2, '0');
  final month = date.month.toString().padLeft(2, '0');
  return '$day.$month.${date.year}';
}
