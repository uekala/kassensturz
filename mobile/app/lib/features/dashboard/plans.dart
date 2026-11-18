import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';

/// Account kinds that hold a value instead of bookings; nothing is paid
/// from them.
const _valueKinds = {
  'depot',
  'festgeld',
  'vl',
  'immobilie',
  'kredit',
  'taschengeld',
};

/// Label of an action the server offers on an alert or a plan.
String planActionLabel(String action, {required bool expense}) =>
    switch (action) {
      'ack' => 'Geprüft',
      'paid' => 'Bezahlt',
      'received' => 'Ist angekommen',
      'drop' => expense ? 'Entfällt' : 'Kommt nicht mehr',
      _ => action,
    };

/// What an alert refers to: (`planned` or `expected`, id), or null.
({String kind, int id})? planOfAlert(Map<String, dynamic> alert) {
  final key = alert['key']?.toString() ?? '';
  final match = RegExp(r'^(planned|expected)-due:(\d+):').firstMatch(key);
  if (match == null) return null;
  return (kind: match.group(1)!, id: int.parse(match.group(2)!));
}

/// Runs an action of an alert and tells the person how it went.
Future<void> runAlertAction(
  BuildContext context,
  MobileConnectionController controller,
  Map<String, dynamic> alert,
  String action,
) async {
  final messenger = ScaffoldMessenger.of(context);
  final plan = planOfAlert(alert);
  final String? error;
  if (action == 'ack') {
    error = await controller.acknowledgeAlert(alert['key']?.toString() ?? '');
  } else if (plan != null) {
    error = await controller.settlePlan(plan.kind, plan.id, action);
  } else {
    error = 'Diese Aktion kennt die App nicht.';
  }
  messenger.showSnackBar(SnackBar(content: Text(error ?? 'Erledigt')));
}

/// Open planned expenses and expected incomes, each with its actions.
class PlansSection extends StatelessWidget {
  const PlansSection({
    required this.controller,
    required this.plans,
    super.key,
  });

  final MobileConnectionController controller;
  final Map<String, dynamic> plans;

  static List<Map<String, dynamic>> _items(dynamic value) {
    if (value is! List) return const [];
    return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
  }

  @override
  Widget build(BuildContext context) {
    final planned = _items(plans['planned']);
    final expected = _items(plans['expected']);
    if (planned.isEmpty && expected.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 22),
        const SectionTitle('Geplant und erwartet'),
        const SizedBox(height: 4),
        for (final item in planned)
          _PlanRow(controller: controller, item: item, expense: true),
        for (final item in expected)
          _PlanRow(controller: controller, item: item, expense: false),
      ],
    );
  }
}

class _PlanRow extends StatelessWidget {
  const _PlanRow({
    required this.controller,
    required this.item,
    required this.expense,
  });

  final MobileConnectionController controller;
  final Map<String, dynamic> item;
  final bool expense;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final cents = item['cents'] is int ? item['cents'] as int : 0;
    final label = item['label']?.toString() ?? '';
    final account = item['account']?.toString() ?? '';
    final overdue = item['overdue'] == true;
    final day = expense ? item['due_date'] : item['since'];
    final when = day is String
        ? (expense ? 'am ${formatShortDate(day)}' : 'seit ${formatShortDate(day)}')
        : '';
    return InkWell(
      onTap: controller.canManagePlans
          ? () => _openActions(context, label)
          : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(
                    [
                      expense ? 'Geplante Ausgabe' : 'Geld kommt zurück',
                      when,
                      account,
                      if (overdue) expense ? 'noch offen' : 'steht aus',
                    ].where((part) => part.isNotEmpty).join(', '),
                    style: textTheme.bodySmall?.copyWith(
                      color: overdue ? klar.warn : null,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Text(
              expense
                  ? formatEuro(-cents / 100)
                  : formatSignedEuro(cents / 100),
              style: textTheme.titleMedium,
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openActions(BuildContext context, String label) async {
    final kind = expense ? 'planned' : 'expected';
    final id = item['id'] is int ? item['id'] as int : 0;
    final actions = expense ? const ['paid', 'drop'] : const ['received', 'drop'];
    final chosen = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(title: Text(label)),
            for (final action in actions)
              ListTile(
                leading: Icon(
                  action == 'drop'
                      ? Icons.close_rounded
                      : Icons.check_circle_outline_rounded,
                ),
                title: Text(planActionLabel(action, expense: expense)),
                onTap: () => Navigator.of(context).pop(action),
              ),
          ],
        ),
      ),
    );
    if (chosen == null || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    final error = await controller.settlePlan(kind, id, chosen);
    messenger.showSnackBar(SnackBar(content: Text(error ?? 'Erledigt')));
  }
}

/// Opens the form that plans a one-off expense, optionally with an amount.
Future<void> showPlanExpenseSheet(
  BuildContext context, {
  required MobileConnectionController controller,
  int? cents,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: PlanExpenseSheet(controller: controller, cents: cents),
  ),
);

class PlanExpenseSheet extends StatefulWidget {
  const PlanExpenseSheet({required this.controller, this.cents, super.key});

  final MobileConnectionController controller;
  final int? cents;

  @override
  State<PlanExpenseSheet> createState() => _PlanExpenseSheetState();
}

class _PlanExpenseSheetState extends State<PlanExpenseSheet> {
  final _label = TextEditingController();
  late final TextEditingController _amount;
  late DateTime _day;
  int? _accountId;
  bool _saving = false;
  String? _error;

  List<Map<String, dynamic>> get _accounts {
    final raw = widget.controller.overviewData?['accounts'];
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map(Map<String, dynamic>.from)
        .where((account) => !_valueKinds.contains(account['type']))
        .toList();
  }

  @override
  void initState() {
    super.initState();
    final cents = widget.cents;
    _amount = TextEditingController(
      text: cents == null ? '' : (cents / 100).toStringAsFixed(2).replaceAll('.', ','),
    );
    _day = DateUtils.dateOnly(DateTime.now()).add(const Duration(days: 7));
    final accounts = _accounts;
    final first =
        accounts.where((account) => account['in_forecast'] == true).firstOrNull ??
        accounts.firstOrNull;
    final id = first?['id'];
    _accountId = id is int ? id : null;
  }

  @override
  void dispose() {
    _label.dispose();
    _amount.dispose();
    super.dispose();
  }

  Future<void> _pickDay() async {
    final today = DateUtils.dateOnly(DateTime.now());
    final picked = await showDatePicker(
      context: context,
      initialDate: _day,
      firstDate: today,
      lastDate: today.add(const Duration(days: 3 * 365)),
    );
    if (picked != null) setState(() => _day = picked);
  }

  Future<void> _save() async {
    final cents = parseAmountToCents(_amount.text);
    final accountId = _accountId;
    if (_label.text.trim().isEmpty) {
      setState(() => _error = 'Wofür ist die Ausgabe?');
      return;
    }
    if (cents == null) {
      setState(() => _error = 'Bitte einen Betrag größer als 0 eingeben.');
      return;
    }
    if (accountId == null) {
      setState(() => _error = 'Bitte das Konto wählen.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final day =
        '${_day.year}-${_day.month.toString().padLeft(2, '0')}-'
        '${_day.day.toString().padLeft(2, '0')}';
    final error = await widget.controller.createPlanned(
      label: _label.text,
      cents: cents,
      dueDate: day,
      accountId: accountId,
    );
    if (!mounted) return;
    if (error != null) {
      setState(() {
        _saving = false;
        _error = error;
      });
      return;
    }
    final messenger = ScaffoldMessenger.of(context);
    Navigator.of(context).pop();
    messenger.showSnackBar(
      const SnackBar(content: Text('Eingeplant. Zählt jetzt in der Prognose mit')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final accounts = _accounts;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Geplante Ausgabe', style: textTheme.titleLarge),
            const SizedBox(height: 6),
            Text(
              'Bis sie bezahlt ist, zählt sie in „frei verfügbar“ und in der '
              'Prognose mit.',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _label,
              autofocus: true,
              enabled: !_saving,
              maxLength: 80,
              decoration: const InputDecoration(
                labelText: 'Wofür?',
                hintText: 'z. B. Handwerkerrechnung',
                counterText: '',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _amount,
              enabled: !_saving,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(labelText: 'Betrag in Euro'),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _saving ? null : _pickDay,
              icon: const Icon(Icons.event_rounded),
              label: Text('Am ${formatDate(_day)}'),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              initialValue: _accountId,
              decoration: const InputDecoration(labelText: 'Von welchem Konto?'),
              items: [
                for (final account in accounts)
                  if (account['id'] is int)
                    DropdownMenuItem(
                      value: account['id'] as int,
                      child: Text(account['name']?.toString() ?? 'Konto'),
                    ),
              ],
              onChanged: _saving ? null : (value) => setState(() => _accountId = value),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: textTheme.bodySmall?.copyWith(color: klar.warn)),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(_saving ? 'Speichert …' : 'Einplanen'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Asks how much comes back for an expense and notes it.
Future<void> showMoneyBackDialog(
  BuildContext context, {
  required MobileConnectionController controller,
  required int transactionId,
  required int expenseCents,
}) async {
  final cents = await showDialog<int>(
    context: context,
    builder: (context) => _MoneyBackDialog(expenseCents: expenseCents),
  );
  if (cents == null || !context.mounted) return;
  final messenger = ScaffoldMessenger.of(context);
  final error = await controller.createExpected(transactionId, cents);
  messenger.showSnackBar(
    SnackBar(
      content: Text(error ?? 'Gemerkt. Bleibt offen, bis das Geld da ist'),
    ),
  );
}

class _MoneyBackDialog extends StatefulWidget {
  const _MoneyBackDialog({required this.expenseCents});

  final int expenseCents;

  @override
  State<_MoneyBackDialog> createState() => _MoneyBackDialogState();
}

class _MoneyBackDialogState extends State<_MoneyBackDialog> {
  late final TextEditingController _amount = TextEditingController(
    text: (widget.expenseCents.abs() / 100)
        .toStringAsFixed(2)
        .replaceAll('.', ','),
  );

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Geld kommt zurück'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Kommt derselbe Betrag vom selben Absender auf diesem Konto an, '
            'hakt Kassensturz ihn von selbst ab.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _amount,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Betrag in Euro'),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Abbrechen'),
        ),
        FilledButton(
          onPressed: () =>
              Navigator.of(context).pop(parseAmountToCents(_amount.text)),
          child: const Text('Merken'),
        ),
      ],
    );
  }
}
