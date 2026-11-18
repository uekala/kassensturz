import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';
import '../budget/budget_editor_sheet.dart';
import '../budget/triage_page.dart';
import '../more/changes_page.dart';
import '../more/household_page.dart';
import '../projects/projects_page.dart';
import 'account_value_sheet.dart';
import 'loan_sheet.dart';
import 'net_worth_trend.dart';

/// Accounts as the server reports them; they are managed in Home Assistant.
class ServerAccountsPage extends StatelessWidget {
  const ServerAccountsPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final data = controller.overviewData;
    final accounts = _maps(data?['accounts']);
    final textTheme = Theme.of(context).textTheme;
    // A child's pocket money is an arrangement, not money in the bank; it
    // does not count towards the adults' net worth.
    final known = accounts
        .where((item) => item['balance_known'] == true && !_isPocket(item))
        .toList();
    final total = known.fold<int>(
      0,
      (sum, item) => sum + _integer(item['balance_cents']),
    );
    // Older servers send no group; they only know everyday accounts,
    // reserves and depots.
    String groupOf(Map<String, dynamic> item) {
      final group = item['group'];
      if (group is String && _groupLabels.containsKey(group)) return group;
      if (item['type'] == 'depot') return 'depots';
      return item['in_forecast'] != false ? 'alltag' : 'ruecklagen';
    }

    final sums = <String, int>{};
    for (final item in known) {
      final group = groupOf(item);
      sums[group] = (sums[group] ?? 0) + _integer(item['balance_cents']);
    }
    final note = [
      for (final entry in _groupLabels.entries)
        if (entry.key == 'alltag' || (sums[entry.key] ?? 0) != 0)
          '${entry.value} ${formatEuro((sums[entry.key] ?? 0) / 100)}',
    ].join(' · ');
    // With a household the server only sends the accounts of this person
    // and the shared ones; say so and mark which is which.
    final household = data?['household'];
    final split = household is Map && household['private_accounts'] == true;
    final person = household is Map ? household['person'] : null;
    final viewer = person is Map ? _string(person['name'], '') : '';
    final String scope;
    if (controller.isReadOnly) {
      scope = 'Das ist dein Geld. Ändern können es nur die Erwachsenen.';
    } else if (viewer.isEmpty) {
      scope = 'Du siehst hier nur die gemeinsamen Konten.';
    } else {
      scope = 'Du siehst deine eigenen und die gemeinsamen Konten ($viewer).';
    }
    // What is open between this person and the others from shared expenses.
    final open = household is Map ? household['balances'] : null;
    final owed = _maps(open).map(_owedLine).toList();

    return RefreshIndicator(
      onRefresh: controller.loadFinancialData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          // A child only has its pocket money; groups would read as 0,00 €.
          AmountHeadline(
            label: controller.isReadOnly ? 'Dein Geld' : 'Vermögen',
            amount: formatEuro(total / 100),
            note: controller.isReadOnly ? null : note,
          ),
          if (split) ...[
            const SizedBox(height: 8),
            Text(scope, style: textTheme.bodySmall),
            for (final line in owed) Text(line, style: textTheme.bodySmall),
            if (controller.canShareExpenses)
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  onPressed: () => Navigator.of(context).push<void>(
                    MaterialPageRoute(
                      builder: (_) => HouseholdPage(controller: controller),
                    ),
                  ),
                  child: const Text('Geteilte Ausgaben und Ausgleich'),
                ),
              ),
          ],
          if (controller.canShowChanges)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: () => Navigator.of(context).push<void>(
                  MaterialPageRoute(
                    builder: (_) => ChangesPage(controller: controller),
                  ),
                ),
                child: const Text('Wer hat was geändert?'),
              ),
            ),
          const SizedBox(height: 22),
          if (controller.canShowNetWorthHistory && data != null)
            NetWorthTrend(controller: controller),
          if (controller.financeLoading && data == null)
            const Center(child: CircularProgressIndicator())
          else if (data == null)
            _LoadError(
              message: controller.financeError,
              onRetry: controller.loadFinancialData,
            )
          else if (accounts.isEmpty)
            const QuietMessage('Der Server liefert noch keine Konten.')
          else
            for (final account in accounts)
              _AccountPanel(
                account: account,
                showOwnership: split,
                onTap: _accountTap(context, controller, account),
              ),
          if (controller.financeError != null && data != null) ...[
            const SizedBox(height: 8),
            Text(
              controller.financeError!,
              style: textTheme.bodySmall?.copyWith(color: klar.warn),
            ),
          ],
          const SizedBox(height: 10),
          if (!controller.isReadOnly)
            Text(
              controller.canEditAccountValues
                  ? _valuesInApp
                  : _valuesInHomeAssistant,
              style: textTheme.bodySmall,
            ),
        ],
      ),
    );
  }
}

/// A loan opens its repayment plan, a deposit the form for its value.
VoidCallback? _accountTap(
  BuildContext context,
  MobileConnectionController controller,
  Map<String, dynamic> account,
) {
  final id = _integer(account['id']);
  final loan = account['type'] == 'kredit';
  final editable =
      controller.canEditAccountValues && account['value_editable'] == true;
  void editValue() => showAccountValueSheet(
    context,
    controller: controller,
    accountId: id,
    name: _string(account['name'], loan ? 'Kredit' : 'Konto'),
    loan: loan,
    currentCents: account['balance_known'] == true
        ? _integer(account['balance_cents'])
        : null,
  );
  if (loan && controller.canShowLoans) {
    return () => showLoanSheet(
      context,
      controller: controller,
      accountId: id,
      name: _string(account['name'], 'Kredit'),
      onEditValue: editable ? editValue : null,
    );
  }
  return editable ? editValue : null;
}

const _valuesInApp =
    'Konten legst du in Kassensturz in Home Assistant an. Tipp auf Depot, '
    'Festgeld, Immobilie oder Kredit, um den heutigen Wert einzutragen. '
    'Umsätze von Hand gehen nur auf Konten ohne Bankabruf; ein Konto für '
    'Bargeld legt die App über das Plus selbst an.';
const _valuesInHomeAssistant =
    'Konten legst du in Kassensturz in Home Assistant an, dort trägst du '
    'auch Werte für Depot, Festgeld, Immobilie und Kredit ein. Umsätze von '
    'Hand gehen nur auf Konten ohne Bankabruf; ein Konto für Bargeld legt '
    'die App über das Plus selbst an.';

class _AccountPanel extends StatelessWidget {
  const _AccountPanel({
    required this.account,
    this.showOwnership = false,
    this.onTap,
  });

  final Map<String, dynamic> account;

  /// Opens more about the account, for a loan its repayment plan.
  final VoidCallback? onTap;

  /// Only with a household: say whether the account is private or shared.
  final bool showOwnership;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final balance = _integer(account['balance_cents']);
    final known = account['balance_known'] == true;
    final date = _string(account['balance_date'], '');
    final type = _string(account['type'], '');
    final previous = account['previous_value_cents'];
    final previousDate = _string(account['previous_value_date'], '');
    final due = _string(account['matures_on'], '');
    final detail = [
      _typeLabels[type] ?? 'Konto',
      if (showOwnership) _ownershipLabel(account['ownership']),
      if (date.isNotEmpty) 'Stand ${formatShortDate(date)}',
      if (previous is int && previousDate.isNotEmpty)
        '${formatSignedEuro((balance - previous) / 100)} seit '
            '${formatShortDate(previousDate)}',
      if (due.isNotEmpty)
        '${type == 'kredit' ? 'läuft bis' : 'fällig am'} '
            '${formatShortDate(due)}',
      if (!known)
        type == 'kredit'
            ? 'Restschuld fehlt'
            : _valueTypes.contains(type)
            ? 'Wert fehlt'
            : 'Saldo nicht bestätigt',
    ].join(' · ');

    final panel = OutlinedPanel(
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _string(account['name'], 'Konto'),
                  style: textTheme.titleMedium,
                ),
                const SizedBox(height: 3),
                Text(detail, style: textTheme.bodySmall),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(
            known ? formatEuro(balance / 100) : '–',
            style: textTheme.titleMedium?.copyWith(
              color: balance < 0 ? klar.warn : klar.ink,
            ),
          ),
          if (onTap != null) ...[
            const SizedBox(width: 4),
            Icon(Icons.chevron_right_rounded, color: klar.mutedInk),
          ],
        ],
      ),
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: onTap == null
          ? panel
          : InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(14),
              child: panel,
            ),
    );
  }
}

/// Budgets of the current month as the server reports them.
class ServerBudgetPage extends StatelessWidget {
  const ServerBudgetPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final data = controller.overviewData;
    final budgets = _maps(data?['budgets']);
    // With a household these are the shared budgets; the person's own ones
    // only count the own accounts and come separately.
    final ownBudgets = _maps(data?['own_budgets']);
    final household = data?['household'];
    final split = household is Map && household['private_accounts'] == true;
    final textTheme = Theme.of(context).textTheme;
    final totalLimit = budgets.fold<int>(
      0,
      (sum, item) => sum + _integer(item['limit_cents']),
    );
    final totalSpent = budgets.fold<int>(
      0,
      (sum, item) => sum + _integer(item['spent_cents']),
    );
    final remaining = totalLimit - totalSpent;

    return RefreshIndicator(
      onRefresh: controller.loadFinancialData,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          AmountHeadline(
            label: remaining < 0 ? 'Über dem Budget' : 'Noch verfügbar',
            amount: formatEuro(remaining.abs() / 100),
            note:
                'Ausgegeben: ${formatEuro(totalSpent / 100)} '
                'von ${formatEuro(totalLimit / 100)}',
            size: 40,
          ),
          const SizedBox(height: 12),
          ThickBar(
            value: totalLimit <= 0
                ? 0.0
                : (totalSpent / totalLimit).clamp(0.0, 1.0).toDouble(),
            over: remaining < 0,
            height: 14,
          ),
          const SizedBox(height: 24),
          if (controller.canTriage && controller.triageTotal > 0) ...[
            LinkTile(
              icon: Icons.rule_folder_outlined,
              title: controller.triageTotal == 1
                  ? 'Eine Buchung zuordnen'
                  : '${controller.triageTotal} Buchungen zuordnen',
              subtitle: controller.triageExpenseCents > 0
                  ? '${formatEuro(controller.triageExpenseCents / 100)} '
                        'Ausgaben ohne richtige Kategorie'
                  : 'Noch ohne richtige Kategorie',
              onTap: () => Navigator.of(context).push<void>(
                MaterialPageRoute(
                  builder: (_) => TriagePage(controller: controller),
                ),
              ),
            ),
            const SizedBox(height: 10),
          ],
          if (controller.canShowProjects && !controller.isReadOnly) ...[
            LinkTile(
              icon: Icons.folder_open_rounded,
              title: 'Projekte',
              subtitle: 'Was etwas insgesamt gekostet hat',
              onTap: () => Navigator.of(context).push<void>(
                MaterialPageRoute(
                  builder: (_) => ProjectsPage(controller: controller),
                ),
              ),
            ),
            const SizedBox(height: 10),
          ],
          if (controller.canSuggestBudgets &&
              controller.canEditBudgets &&
              data != null) ...[
            LinkTile(
              icon: Icons.auto_graph_rounded,
              title: 'Budgets vorschlagen',
              subtitle: 'Aus deinen Ausgaben der letzten Monate',
              onTap: () => Navigator.of(context).push<void>(
                MaterialPageRoute(
                  builder: (_) => BudgetSuggestionsPage(controller: controller),
                ),
              ),
            ),
            const SizedBox(height: 18),
          ],
          if (controller.financeLoading && data == null)
            const Center(child: CircularProgressIndicator())
          else if (data == null)
            _LoadError(
              message: controller.financeError,
              onRetry: controller.loadFinancialData,
            )
          else if (budgets.isEmpty)
            const QuietMessage('Noch keine Budgets.')
          else
            for (final budget in budgets)
              _BudgetBlock(
                budget: budget,
                onTap: controller.canEditBudgets
                    ? () => showBudgetEditor(
                        context,
                        controller: controller,
                        categoryId: _integer(budget['category_id']),
                        categoryName: _string(budget['name'], ''),
                        limitCents: _integer(budget['limit_cents']),
                      )
                    : null,
              ),
          if (controller.canEditBudgets && data != null) ...[
            const SizedBox(height: 4),
            OutlinedButton.icon(
              onPressed: () =>
                  showBudgetEditor(context, controller: controller),
              icon: const Icon(Icons.add),
              label: const Text('Budget anlegen'),
            ),
          ],
          if (split && controller.canEditOwnBudgets && data != null) ...[
            const SizedBox(height: 22),
            Text('Nur für dich', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'Diese Budgets zählen nur Ausgaben von deinen eigenen Konten.',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 10),
            for (final budget in ownBudgets)
              _BudgetBlock(
                budget: budget,
                onTap: () => showBudgetEditor(
                  context,
                  controller: controller,
                  categoryId: _integer(budget['category_id']),
                  categoryName: _string(budget['name'], ''),
                  limitCents: _integer(budget['limit_cents']),
                  own: true,
                ),
              ),
            const SizedBox(height: 4),
            OutlinedButton.icon(
              onPressed: () =>
                  showBudgetEditor(context, controller: controller, own: true),
              icon: const Icon(Icons.add),
              label: const Text('Eigenes Budget anlegen'),
            ),
          ],
          if (controller.financeError != null && data != null) ...[
            const SizedBox(height: 8),
            Text(
              controller.financeError!,
              style: textTheme.bodySmall?.copyWith(color: klar.warn),
            ),
          ],
          const SizedBox(height: 6),
          Text(_budgetHint(controller), style: textTheme.bodySmall),
          ..._savingsSections(context, data),
        ],
      ),
    );
  }
}

class _BudgetBlock extends StatelessWidget {
  const _BudgetBlock({required this.budget, this.onTap});

  final Map<String, dynamic> budget;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final limit = _integer(budget['limit_cents']);
    final spent = _integer(budget['spent_cents']);
    final left = _integer(budget['remaining_cents']);
    final progress = limit <= 0
        ? 0.0
        : (spent / limit).clamp(0.0, 1.0).toDouble();
    final over = spent > limit || _string(budget['state'], 'ok') == 'over';

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _string(budget['name'], 'Budget'),
                    style: textTheme.titleMedium,
                  ),
                ),
                Text(
                  '${formatEuro(spent / 100)} von ${formatEuro(limit / 100)}',
                  style: textTheme.bodyMedium,
                ),
              ],
            ),
            const SizedBox(height: 7),
            ThickBar(value: progress, over: over),
            const SizedBox(height: 6),
            Text(
              over
                  ? '${formatEuro(left.abs() / 100)} über dem Budget'
                  : '${formatEuro(left / 100)} übrig',
              style: textTheme.bodySmall?.copyWith(
                color: over ? klar.warn : klar.mutedInk,
                fontWeight: over ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadError extends StatelessWidget {
  const _LoadError({required this.message, required this.onRetry});

  final String? message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off_outlined, size: 32),
          const SizedBox(height: 10),
          const Text('Serverdaten konnten nicht geladen werden.'),
          if (message != null) Text(message!, textAlign: TextAlign.center),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Erneut versuchen'),
          ),
        ],
      ),
    ),
  );
}

const _typeLabels = {
  'giro': 'Girokonto',
  'tagesgeld': 'Tagesgeld',
  'sparkonto': 'Sparkonto',
  'festgeld': 'Festgeld',
  'vl': 'VL / Bausparen',
  'depot': 'Depot',
  'immobilie': 'Immobilie',
  'kredit': 'Kredit',
  'kreditkarte': 'Kreditkarte',
  'paypal': 'PayPal',
  'taschengeld': 'Taschengeld',
  'sonstiges': 'Sonstiges',
};

/// The pocket money account of a child, as an adult sees it.
bool _isPocket(Map<String, dynamic> item) => item['ownership'] == 'child';

String _ownershipLabel(dynamic ownership) => switch (ownership) {
  'mine' => 'nur für dich',
  'child' => 'für ein Kind',
  _ => 'gemeinsam',
};

const _valueTypes = {'depot', 'festgeld', 'vl', 'immobilie', 'kredit'};

/// Parts of the net worth, in the order they are shown.
const _groupLabels = {
  'alltag': 'Alltag',
  'ruecklagen': 'Rücklagen',
  'depots': 'Depots',
  'immobilien': 'Immobilien',
  'kredite': 'Kredite',
};

List<Map<String, dynamic>> _maps(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
}

int _integer(dynamic value) => value is int ? value : 0;

/// One line per other person: positive cents mean they owe this person.
String _owedLine(Map<String, dynamic> item) {
  final name = _string(item['person'], 'Jemand');
  final cents = _integer(item['cents']);
  final amount = formatEuro(cents.abs() / 100);
  return cents > 0
      ? '$name schuldet dir $amount.'
      : 'Du schuldest $name $amount.';
}

String _string(dynamic value, String fallback) =>
    value is String && value.isNotEmpty ? value : fallback;

/// Savings goals and the reserve for rare costs, as far as the server sends
/// them. Both are maintained in Kassensturz in Home Assistant.
List<Widget> _savingsSections(
  BuildContext context,
  Map<String, dynamic>? data,
) {
  final textTheme = Theme.of(context).textTheme;
  final goals = _maps(data?['goals']);
  final forecast = data?['forecast'];
  final reserve = forecast is Map ? forecast['reserve'] : null;
  final items = reserve is Map
      ? _maps(reserve['items'])
      : const <Map<String, dynamic>>[];

  return [
    if (goals.isNotEmpty) ...[
      const SizedBox(height: 28),
      const SectionTitle('Sparziele'),
      const SizedBox(height: 10),
      for (final goal in goals) _GoalBlock(goal: goal),
    ],
    if (reserve is Map && items.isNotEmpty) ...[
      const SizedBox(height: 22),
      const SectionTitle('Jahreskosten'),
      const SizedBox(height: 6),
      Text(
        'Dafür solltest du heute '
        '${formatEuro(_integer(reserve['reserved_cents']) / 100)} '
        'zurückgelegt haben, das sind '
        '${formatEuro(_integer(reserve['monthly_cents']) / 100)} im Monat.'
        '${reserve['deducted'] == true ? ' Der Betrag ist von „frei verfügbar“ abgezogen.' : ''}',
        style: textTheme.bodySmall,
      ),
      const SizedBox(height: 4),
      for (final item in items)
        EntryRow(
          title: _string(item['name'], 'Vertrag'),
          detail:
              '${_string(item['interval'], '')} · nächste Zahlung '
              '${formatShortDate(_string(item['next_due'], ''))}',
          amount: formatEuro(_integer(item['amount_cents']) / 100),
        ),
    ],
  ];
}

class _GoalBlock extends StatelessWidget {
  const _GoalBlock({required this.goal});

  final Map<String, dynamic> goal;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final saved = _integer(goal['saved_cents']);
    final target = _integer(goal['target_cents']);
    final rest = _integer(goal['rest_cents']);
    final monthly = goal['monthly_cents'];
    final due = _string(goal['due_date'], '');
    final status = goal['status'];
    final progress = goal['progress'];
    final detail = status == 'done'
        ? 'Erreicht'
        : status == 'late'
        ? 'Ziel war ${formatShortDate(due)}, es fehlen '
              '${formatEuro(rest / 100)}'
        : monthly is int && due.isNotEmpty
        ? '${formatEuro(monthly / 100)} im Monat bis ${formatShortDate(due)}'
        : 'Es fehlen ${formatEuro(rest / 100)}';
    // With a household a goal can belong to this person alone.
    final own = goal['ownership'] == 'mine';
    final note = own ? '$detail · nur für dich' : detail;

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  _string(goal['name'], 'Sparziel'),
                  style: textTheme.titleSmall,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                '${formatEuro(saved / 100)} von ${formatEuro(target / 100)}',
                style: textTheme.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: 8),
          ThickBar(value: progress is num ? progress.toDouble() : 0),
          const SizedBox(height: 6),
          Text(note, style: textTheme.bodySmall),
        ],
      ),
    );
  }
}

/// What the line below the budgets says, depending on what this phone may do.
String _budgetHint(MobileConnectionController controller) {
  if (controller.canEditBudgets) {
    return 'Tippe auf ein Budget, um es zu ändern oder zu entfernen.';
  }
  if (controller.isReadOnly) {
    return 'Budgets legen die Erwachsenen im Haushalt fest.';
  }
  return 'Budgets änderst du in Kassensturz in Home Assistant. Ab Server '
      '0.3.9 geht das auch hier.';
}
