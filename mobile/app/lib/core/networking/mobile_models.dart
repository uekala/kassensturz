import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

/// Typisierte Sichten auf die Serverantworten, die Formulare und Auswahllisten nutzen. Jede
/// Factory prüft die Felder, die sie braucht, und wirft eine [FormatException],
/// statt stillschweigend auf null zurückzufallen.

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

  /// True für Konten ohne Bankanbindung; nur diese nehmen manuelle Einträge an.
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

  /// Monatsbudget in Cent, null, wenn die Kategorie keines hat.
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

  /// Veränderung der letzten Zahlung gegenüber dem üblichen Preis; negativ heißt, der
  /// Vertrag wurde teurer. Null, wenn es nichts zu zeigen gibt.
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
    this.suggestedCategoryId,
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
      suggestedCategoryId:
          json['suggestion'] is Map && (json['suggestion'] as Map)['id'] is int
          ? (json['suggestion'] as Map)['id'] as int
          : null,
      receiptCount: json['receipt_count'] is int
          ? json['receipt_count'] as int
          : 0,
    );
  }

  static List<ServerTransaction> listFrom(Map<String, dynamic> response) =>
      _items(response, ServerTransaction.fromJson);

  final int id;
  final int accountId;
  final String bookingDate;
  final int amountCents;

  /// True für von Hand angelegte Einträge; nur diese lassen sich ganz ändern oder
  /// löschen. Bankumsätze nehmen nur eine neue Kategorie und Notiz an.
  final bool manual;
  final String? counterparty;
  final String? purpose;
  final String? note;
  final String? accountName;
  final int? categoryId;
  final String? categoryName;

  /// Schlüssel aus [taxKindLabels], wenn der Eintrag für die Steuererklärung markiert ist.
  final String? taxKind;
  final int receiptCount;

  /// ISO-Datum, an dem die Garantie dieses Kaufs endet, falls eines gesetzt ist.
  final String? warrantyUntil;

  /// Kategorie, die der Server beim Sortieren vorschlägt; null ohne klaren Hinweis.
  final int? suggestedCategoryId;
}

/// Neue Umsätze, seit dieses Gerät sie zuletzt als gelesen markiert hat.
class ServerNews {
  const ServerNews({
    required this.count,
    required this.incomeCents,
    required this.expenseCents,
    required this.largest,
  });

  factory ServerNews.fromJson(Map<String, dynamic> json) {
    final largest = <({String label, int amountCents})>[];
    final raw = json['largest'];
    if (raw is List) {
      for (final entry in raw.whereType<Map>()) {
        final label = entry['label'];
        final amount = entry['amount_cents'];
        if (label is String && amount is int) {
          largest.add((label: label, amountCents: amount));
        }
      }
    }
    int number(String key) => json[key] is int ? json[key] as int : 0;
    return ServerNews(
      count: number('count'),
      incomeCents: number('income_cents'),
      expenseCents: number('expense_cents'),
      largest: largest,
    );
  }

  final int count;
  final int incomeCents;
  final int expenseCents;
  final List<({String label, int amountCents})> largest;
}

/// Eine Art der Steuerübersicht mit ihrer Summe für das Jahr.
class TaxGroup {
  const TaxGroup({
    required this.label,
    required this.count,
    required this.totalCents,
    required this.missingReceipts,
  });

  factory TaxGroup.fromJson(Map<String, dynamic> json) => TaxGroup(
    label: _requiredString(json, 'label'),
    count: _requiredInt(json, 'count'),
    totalCents: _requiredInt(json, 'total_cents'),
    missingReceipts: json['missing_receipts'] is int
        ? json['missing_receipts'] as int
        : 0,
  );

  final String label;
  final int count;
  final int totalCents;
  final int missingReceipts;
}

/// Ein Kauf, dessen Garantie läuft oder vor Kurzem geendet hat.
class ServerWarranty {
  const ServerWarranty({
    required this.label,
    required this.amountCents,
    required this.until,
    required this.daysLeft,
    required this.hasReceipt,
  });

  factory ServerWarranty.fromJson(Map<String, dynamic> json) => ServerWarranty(
    label: _requiredString(json, 'label'),
    amountCents: _requiredInt(json, 'amount_cents'),
    until: _requiredString(json, 'warranty_until'),
    daysLeft: _requiredInt(json, 'days_left'),
    hasReceipt:
        json['receipt_count'] is int && json['receipt_count'] as int > 0,
  );

  final String label;
  final int amountCents;
  final String until;
  final int daysLeft;
  final bool hasReceipt;
}

/// Steuerübersicht eines Jahres und die Garantien, wie der Server sie meldet.
class PapersOverview {
  const PapersOverview({
    required this.year,
    required this.years,
    required this.totalCents,
    required this.missingReceipts,
    required this.groups,
    required this.running,
    required this.expired,
  });

  factory PapersOverview.fromJson(Map<String, dynamic> json) {
    final tax = json['tax'] is Map
        ? Map<String, dynamic>.from(json['tax'] as Map)
        : const <String, dynamic>{};
    final warranties = json['warranties'] is Map
        ? Map<String, dynamic>.from(json['warranties'] as Map)
        : const <String, dynamic>{};
    List<T> list<T>(Object? raw, T Function(Map<String, dynamic>) parse) => [
      if (raw is List)
        for (final entry in raw.whereType<Map>())
          parse(Map<String, dynamic>.from(entry)),
    ];
    final years = tax['years'];
    return PapersOverview(
      year: tax['year'] is int ? tax['year'] as int : 0,
      years: years is List ? years.whereType<int>().toList() : const [],
      totalCents: tax['total_cents'] is int ? tax['total_cents'] as int : 0,
      missingReceipts: tax['missing_receipts'] is int
          ? tax['missing_receipts'] as int
          : 0,
      groups: list(tax['groups'], TaxGroup.fromJson),
      running: list(warranties['running'], ServerWarranty.fromJson),
      expired: list(warranties['expired'], ServerWarranty.fromJson),
    );
  }

  final int year;
  final List<int> years;
  final int totalCents;
  final int missingReceipts;
  final List<TaxGroup> groups;
  final List<ServerWarranty> running;
  final List<ServerWarranty> expired;
}

/// Ein Budget, das der Server aus früheren Ausgaben abgeleitet hat.
class BudgetSuggestion {
  const BudgetSuggestion({
    required this.categoryId,
    required this.name,
    required this.averageCents,
    required this.suggestedCents,
    this.currentCents,
  });

  factory BudgetSuggestion.fromJson(Map<String, dynamic> json) =>
      BudgetSuggestion(
        categoryId: _requiredInt(json, 'category_id'),
        name: _requiredString(json, 'name'),
        averageCents: _requiredInt(json, 'average_cents'),
        suggestedCents: _requiredInt(json, 'suggested_cents'),
        currentCents: json['current_cents'] is int
            ? json['current_cents'] as int
            : null,
      );

  static List<BudgetSuggestion> listFrom(Map<String, dynamic> response) =>
      _items(response, BudgetSuggestion.fromJson);

  final int categoryId;
  final String name;
  final int averageCents;
  final int suggestedCents;
  final int? currentCents;
}

/// Was eine Bank während eines Abrufs fragt: eine TAN, welches Verfahren oder Gerät, oder
/// den Zugriff in ihrer eigenen App freizugeben.
class BankQuestion {
  const BankQuestion({
    required this.qid,
    required this.kind,
    required this.bank,
    this.text = '',
    this.title = '',
    this.options = const [],
    this.image,
    this.flicker = const [],
  });

  /// Null für alles, was diese App nicht zeigen kann, damit es nie blind beantwortet wird.
  static BankQuestion? tryParse(dynamic json) {
    if (json is! Map) return null;
    final qid = json['qid'];
    final kind = json['kind'];
    if (qid is! String || qid.isEmpty) return null;
    if (kind != 'tan' && kind != 'decoupled' && kind != 'choice') return null;
    final options = <({String value, String label, String hint})>[];
    final rawOptions = json['options'];
    if (rawOptions is List) {
      for (final entry in rawOptions.whereType<Map>()) {
        final value = entry['value'];
        final label = entry['label'];
        final hint = entry['hint'];
        if (value is String && value.isNotEmpty) {
          options.add((
            value: value,
            label: label is String && label.isNotEmpty ? label : value,
            hint: hint is String ? hint : '',
          ));
        }
      }
    }
    if (kind == 'choice' && options.isEmpty) return null;
    Uint8List? image;
    final rawImage = json['image'];
    if (rawImage is String && rawImage.startsWith('data:image/')) {
      final comma = rawImage.indexOf(',');
      if (comma > 0) {
        try {
          image = base64Decode(rawImage.substring(comma + 1));
        } on FormatException {
          image = null;
        }
      }
    }
    final rawFlicker = json['flicker'];
    final text = json['text'];
    final title = json['title'];
    final bank = json['bank'];
    return BankQuestion(
      qid: qid,
      kind: kind as String,
      bank: bank is String && bank.isNotEmpty ? bank : 'Bank',
      text: text is String ? text : '',
      title: title is String ? title : '',
      options: options,
      image: image,
      flicker: rawFlicker is List
          ? rawFlicker
                .whereType<String>()
                .where((frame) => frame.length == 5)
                .toList()
          : const [],
    );
  }

  /// Benennt genau diese Rückfrage; die Antwort geht mit ihr zurück.
  final String qid;

  /// 'tan', 'decoupled' (in der Banking-App freigeben) oder 'choice'.
  final String kind;
  final String bank;
  final String text;
  final String title;
  final List<({String value, String label, String hint})> options;

  /// Das Bild einer photoTAN, falls die Bank eines geschickt hat.
  final Uint8List? image;

  /// Bilder eines Flickercodes, je fünf Balken, '1' für einen weißen Balken.
  final List<String> flicker;
}

/// Was der Server über den Abruf bei den Banken weiß.
class ServerSyncStatus {
  const ServerSyncStatus({
    required this.running,
    required this.canStart,
    required this.waitMinutes,
    required this.added,
    required this.errors,
    required this.problems,
    required this.sources,
    this.renewals = const [],
    this.question,
    this.lastSync,
    this.nextSync,
  });

  factory ServerSyncStatus.fromJson(Map<String, dynamic> json) {
    final run = json['run'];
    final runMap = run is Map ? Map<String, dynamic>.from(run) : const {};
    final errors = <String>[];
    final rawErrors = runMap['errors'];
    if (rawErrors is List) {
      for (final entry in rawErrors.whereType<Map>()) {
        final name = entry['name'];
        final message = entry['message'];
        if (message is String) {
          errors.add(name is String ? '$name: $message' : message);
        }
      }
    }
    final problems = <String>[];
    final renewals = <({int id, String name})>[];
    var count = 0;
    final sources = json['sources'];
    if (sources is List) {
      for (final entry in sources.whereType<Map>()) {
        count += 1;
        final name = entry['name'] is String ? entry['name'] as String : 'Bank';
        final days = entry['days_left'];
        final renew = entry['renew'];
        if (renew is int) renewals.add((id: renew, name: name));
        switch (entry['state']) {
          case 'expired':
            problems.add('$name: Freigabe abgelaufen');
          case 'no_accounts':
            problems.add('$name: keine Konten verknüpft');
          case 'needs_pin':
            problems.add('$name: nur von Hand in Home Assistant');
          case 'error':
            problems.add('$name: letzter Abruf fehlgeschlagen');
          default:
            if (days is int && days <= 14) {
              problems.add(
                days <= 0
                    ? '$name: Freigabe läuft heute ab'
                    : '$name: Freigabe läuft in $days Tagen ab',
              );
            }
        }
      }
    }
    final added = runMap['added'];
    final wait = json['wait_minutes'];
    return ServerSyncStatus(
      running: runMap['state'] == 'running',
      canStart: json['can_start'] == true,
      waitMinutes: wait is int ? wait : 0,
      added: added is int ? added : 0,
      errors: errors,
      problems: problems,
      renewals: renewals,
      question: BankQuestion.tryParse(json['question']),
      sources: count,
      lastSync: DateTime.tryParse(_optionalString(json, 'last_sync') ?? ''),
      nextSync: DateTime.tryParse(_optionalString(json, 'next_sync') ?? ''),
    );
  }

  final bool running;
  final bool canStart;
  final int waitMinutes;

  /// Neue Umsätze des aus der App gestarteten Abrufs.
  final int added;
  final List<String> errors;

  /// Banken, die Aufmerksamkeit brauchen, fertig zum Anzeigen.
  final List<String> problems;

  /// Bank-Einwilligungen, die bald enden oder geendet haben und sich vom
  /// Handy aus verlängern lassen.
  final List<({int id, String name})> renewals;

  /// Was eine Bank gerade fragt, falls ein Abruf auf eine Antwort wartet.
  final BankQuestion? question;
  final int sources;

  /// Ältester Stand aller Banken; null, bis jede Bank einmal abgerufen wurde.
  final DateTime? lastSync;
  final DateTime? nextSync;
}

/// "heute, 06:30 Uhr", "gestern, …", "morgen, …" oder das Datum.
String formatMoment(DateTime moment, DateTime now) {
  final day = DateTime(moment.year, moment.month, moment.day);
  final today = DateTime(now.year, now.month, now.day);
  final offset = day.difference(today).inHours / 24;
  final time =
      '${moment.hour.toString().padLeft(2, '0')}:'
      '${moment.minute.toString().padLeft(2, '0')} Uhr';
  final label = switch (offset.round()) {
    0 => 'heute',
    -1 => 'gestern',
    1 => 'morgen',
    _ =>
      '${day.day.toString().padLeft(2, '0')}.'
          '${day.month.toString().padLeft(2, '0')}.${day.year}',
  };
  return '$label, $time';
}

/// Derselbe Kalendertag [years] später; der 29. Februar wird zum 28.
DateTime addYears(DateTime day, int years) {
  final moved = DateTime(day.year + years, day.month, day.day);
  return moved.month == day.month
      ? moved
      : DateTime(day.year + years, day.month + 1, 0);
}

/// Arten, mit denen sich ein Umsatz für die Steuererklärung markieren lässt. Die Schlüssel
/// sind die, die der Server speichert.
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

/// Wandelt einen deutschen oder einfachen Betrag wie `12,50`, `1.234,56` oder `12.5`
/// in Cent um. Gibt null für alles zurück, was kein positiver Betrag ist.
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

/// Formatiert ein Datum als `YYYY-MM-DD`-String, wie der Server ihn erwartet.
String formatIsoDate(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}

/// Erzeugt die ID, die das Anlegen eines Umsatzes wiederholbar macht: Der Server
/// speichert sie und beantwortet eine wiederholte Anfrage mit dem vorhandenen Eintrag.
String newClientRequestId({Random? random}) {
  final source = random ?? Random.secure();
  final buffer = StringBuffer();
  for (var index = 0; index < 16; index++) {
    buffer.write(source.nextInt(256).toRadixString(16).padLeft(2, '0'));
  }
  return buffer.toString();
}
