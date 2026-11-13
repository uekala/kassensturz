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
    this.budgetCents,
  });

  factory ServerCategory.fromJson(Map<String, dynamic> json) => ServerCategory(
    id: _requiredInt(json, 'id'),
    name: _requiredString(json, 'name'),
    kind: _optionalString(json, 'kind') ?? 'expense',
    parentId: json['parent_id'] is int ? json['parent_id'] as int : null,
    budgetCents: json['budget_cents'] is int
        ? json['budget_cents'] as int
        : null,
  );

  static List<ServerCategory> listFrom(Map<String, dynamic> response) =>
      _items(response, ServerCategory.fromJson);

  final int id;
  final String name;
  final String kind;
  final int? parentId;

  /// Monthly budget in cents, null when the category has none.
  final int? budgetCents;
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
    this.priceChangeCents,
    this.manual = false,
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
    priceChangeCents: json['price_change_cents'] is int
        ? json['price_change_cents'] as int
        : null,
    manual: json['manual'] == true,
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

  /// Change of the last payment against the usual price; negative means the
  /// contract became more expensive. Null when there is nothing to show.
  final int? priceChangeCents;
  final bool manual;
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
    this.taxKind,
    this.receiptCount = 0,
    this.warrantyUntil,
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
      taxKind: _optionalString(json, 'tax_kind'),
      warrantyUntil: _optionalString(json, 'warranty_until'),
      receiptCount: json['receipt_count'] is int
          ? json['receipt_count'] as int
          : 0,
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

  /// Key from [taxKindLabels] when the entry is marked for the tax return.
  final String? taxKind;
  final int receiptCount;

  /// ISO date on which the warranty of this purchase ends, if one is set.
  final String? warrantyUntil;
}

/// The same calendar day [years] later; 29 February becomes the 28th.
DateTime addYears(DateTime day, int years) {
  final moved = DateTime(day.year + years, day.month, day.day);
  return moved.month == day.month
      ? moved
      : DateTime(day.year + years, day.month + 1, 0);
}

/// Kinds a transaction can be marked with for the tax return. The keys are
/// the ones the server stores.
const taxKindLabels = <String, String>{
  'handwerker': 'Handwerkerleistung',
  'haushaltsnah': 'Haushaltsnahe Dienstleistung',
  'arbeitsmittel': 'Arbeitsmittel und Werbungskosten',
  'spende': 'Spende',
  'versicherung': 'Versicherung und Vorsorge',
  'gesundheit': 'Krankheitskosten',
  'kinder': 'Kinderbetreuung',
  'sonstiges': 'Sonstiges',
};

class ServerReceipt {
  const ServerReceipt({
    required this.id,
    required this.filename,
    required this.mime,
    required this.size,
  });

  factory ServerReceipt.fromJson(Map<String, dynamic> json) => ServerReceipt(
    id: _requiredInt(json, 'id'),
    filename: _requiredString(json, 'filename'),
    mime: _optionalString(json, 'mime') ?? '',
    size: json['size'] is int ? json['size'] as int : 0,
  );

  static List<ServerReceipt> listFrom(Map<String, dynamic> response) =>
      _items(response, ServerReceipt.fromJson);

  final int id;
  final String filename;
  final String mime;
  final int size;

  bool get isImage => mime.startsWith('image/');

  String get sizeLabel => size >= 1024 * 1024
      ? '${(size / (1024 * 1024)).toStringAsFixed(1).replaceAll('.', ',')} MB'
      : '${(size / 1024).ceil()} KB';
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
