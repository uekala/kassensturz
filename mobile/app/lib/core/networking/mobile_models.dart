import 'dart:math';

/// Typed views of the server responses used by forms and pickers. Every
/// factory validates the fields it needs and throws a [FormatException]
/// instead of silently falling back to zero.

String _requiredString(Map<String, dynamic> source, String key) {
  final value = source[key];
  if (value is! String || value.isEmpty) {
    throw FormatException('Feld "$key" fehlt in der Serverantwort.');
  }
  return value;
}

int _requiredInt(Map<String, dynamic> source, String key) {
  final value = source[key];
  if (value is! int) {
    throw FormatException('Feld "$key" fehlt in der Serverantwort.');
  }
  return value;
}

String? _optionalString(Map<String, dynamic> source, String key) {
  final value = source[key];
  return value is String && value.isNotEmpty ? value : null;
}

List<T> _items<T>(
  Map<String, dynamic> response,
  T Function(Map<String, dynamic>) parse,
) {
  final items = response['items'];
  if (items is! List) {
    throw const FormatException('Die Serverantwort enthält keine Liste.');
  }
  return List<T>.unmodifiable(
    items.whereType<Map>().map(
      (item) => parse(Map<String, dynamic>.from(item)),
    ),
  );
}

class ServerAccount {
  const ServerAccount({
    required this.id,
    required this.name,
    required this.type,
    required this.balanceCents,
    required this.balanceKnown,
    required this.manualEntries,
  });

  factory ServerAccount.fromJson(Map<String, dynamic> json) => ServerAccount(
    id: _requiredInt(json, 'id'),
    name: _requiredString(json, 'name'),
    type: _optionalString(json, 'type') ?? 'Konto',
    balanceCents: _requiredInt(json, 'balance_cents'),
    balanceKnown: json['balance_known'] == true,
    manualEntries: json['manual_entries'] == true,
  );

  static List<ServerAccount> listFrom(Map<String, dynamic> response) =>
      _items(response, ServerAccount.fromJson);

  final int id;
  final String name;
  final String type;
  final int balanceCents;
  final bool balanceKnown;

  /// True for accounts without a bank feed; only these accept manual entries.
  final bool manualEntries;
}

class ServerCategory {
  const ServerCategory({
    required this.id,
    required this.name,
    required this.kind,
    this.parentId,
  });

  factory ServerCategory.fromJson(Map<String, dynamic> json) => ServerCategory(
    id: _requiredInt(json, 'id'),
    name: _requiredString(json, 'name'),
    kind: _optionalString(json, 'kind') ?? 'expense',
    parentId: json['parent_id'] is int ? json['parent_id'] as int : null,
  );

  static List<ServerCategory> listFrom(Map<String, dynamic> response) =>
      _items(response, ServerCategory.fromJson);

  final int id;
  final String name;
  final String kind;
  final int? parentId;
}

class ServerContract {
  const ServerContract({
    required this.key,
    required this.name,
    required this.kind,
    required this.amountCents,
    required this.monthlyCents,
    required this.running,
    this.interval,
    this.nextDue,
    this.status,
    this.categoryName,
    this.accountName,
    this.cancellationDeadline,
  });

  factory ServerContract.fromJson(Map<String, dynamic> json) => ServerContract(
    key: _requiredString(json, 'key'),
    name: _optionalString(json, 'name') ?? 'Vertrag',
    kind: _optionalString(json, 'kind') ?? 'expense',
    amountCents: _requiredInt(json, 'amount_cents'),
    monthlyCents: _requiredInt(json, 'monthly_cents'),
    running: json['running'] == true,
    interval: _optionalString(json, 'interval'),
    nextDue: _optionalString(json, 'next_due'),
    status: _optionalString(json, 'status'),
    categoryName: _optionalString(json, 'category_name'),
    accountName: _optionalString(json, 'account_name'),
    cancellationDeadline: _optionalString(json, 'cancellation_deadline'),
  );

  static List<ServerContract> listFrom(Map<String, dynamic> response) =>
      _items(response, ServerContract.fromJson);

  final String key;
  final String name;
  final String kind;
  final int amountCents;
  final int monthlyCents;
  final bool running;
  final String? interval;
  final String? nextDue;
  final String? status;
  final String? categoryName;
  final String? accountName;
  final String? cancellationDeadline;
}

class ServerTransaction {
  const ServerTransaction({
    required this.id,
    required this.accountId,
    required this.bookingDate,
    required this.amountCents,
    required this.manual,
    this.counterparty,
    this.purpose,
    this.note,
    this.accountName,
    this.categoryId,
    this.categoryName,
  });

  factory ServerTransaction.fromJson(Map<String, dynamic> json) {
    final category = json['category'];
    final categoryMap = category is Map
        ? Map<String, dynamic>.from(category)
        : const <String, dynamic>{};
    return ServerTransaction(
      id: _requiredInt(json, 'id'),
      accountId: _requiredInt(json, 'account_id'),
      bookingDate: _requiredString(json, 'booking_date'),
      amountCents: _requiredInt(json, 'amount_cents'),
      manual: json['manual'] == true,
      counterparty: _optionalString(json, 'counterparty'),
      purpose: _optionalString(json, 'purpose'),
      note: _optionalString(json, 'note'),
      accountName: _optionalString(json, 'account_name'),
      categoryId: categoryMap['id'] is int ? categoryMap['id'] as int : null,
      categoryName: _optionalString(categoryMap, 'name'),
    );
  }

  final int id;
  final int accountId;
  final String bookingDate;
  final int amountCents;

  /// True for entries created by hand; only these can be fully edited or
  /// deleted. Bank transactions accept a new category and note only.
  final bool manual;
  final String? counterparty;
  final String? purpose;
  final String? note;
  final String? accountName;
  final int? categoryId;
  final String? categoryName;
}

/// Parses a German or plain amount such as `12,50`, `1.234,56` or `12.5`
/// into cents. Returns null for anything that is not a positive amount.
int? parseAmountToCents(String input) {
  var text = input.trim().replaceAll('€', '').replaceAll(' ', '');
  if (text.isEmpty) return null;
  if (text.contains(',')) {
    text = text.replaceAll('.', '').replaceAll(',', '.');
  }
  if (!RegExp(r'^\d{1,9}(\.\d{1,2})?$').hasMatch(text)) return null;
  final parts = text.split('.');
  final euros = int.parse(parts[0]);
  final fraction = parts.length == 2 ? parts[1].padRight(2, '0') : '00';
  final cents = euros * 100 + int.parse(fraction);
  return cents > 0 ? cents : null;
}

/// Formats a date as the `YYYY-MM-DD` string the server expects.
String formatIsoDate(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}

/// Creates the id that makes creating a transaction repeatable: the server
/// stores it and answers a repeated request with the existing entry.
String newClientRequestId({Random? random}) {
  final source = random ?? Random.secure();
  final buffer = StringBuffer();
  for (var index = 0; index < 16; index++) {
    buffer.write(source.nextInt(256).toRadixString(16).padLeft(2, '0'));
  }
  return buffer.toString();
}
