import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';

/// Sorts transactions without a real category one after the other: one card,
/// one tap on a category, next card. The server learns from every choice.
class TriagePage extends StatefulWidget {
  const TriagePage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<TriagePage> createState() => _TriagePageState();
}

class _TriagePageState extends State<TriagePage> {
  List<ServerTransaction> _items = const [];
  final _skipped = <int>{};
  int _total = 0;
  int _sorted = 0;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  String? _lastResult;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.loadTriage();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = result.error;
      if (result.error == null) {
        _items = result.items;
        _total = result.total;
      }
    });
  }

  ServerTransaction? get _current {
    for (final item in _items) {
      if (!_skipped.contains(item.id)) return item;
    }
    return null;
  }

  Future<void> _assign(ServerTransaction transaction, ServerCategory to) async {
    if (_saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final failure = await widget.controller.updateTransaction(transaction.id, {
      'category_id': to.id,
    });
    if (!mounted) return;
    if (failure != null) {
      setState(() {
        _saving = false;
        _error = failure;
      });
      return;
    }
    final also = widget.controller.lastAlsoChanged;
    _sorted += 1 + also;
    _lastResult = switch (also) {
      0 => '${to.name} gemerkt.',
      1 => '${to.name} gemerkt, eine ähnliche Buchung gleich mit.',
      _ => '${to.name} gemerkt, $also ähnliche Buchungen gleich mit.',
    };
    // Similar entries moved along, so the list is read again.
    await _load();
    if (mounted) setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final current = _current;
    final left = _total - _skipped.length;

    Widget body;
    if (_loading) {
      body = const Center(child: CircularProgressIndicator());
    } else if (current == null) {
      body = ListView(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
        children: [
          Text(
            _error ??
                (_skipped.isEmpty
                    ? 'Alles zugeordnet.'
                    : 'Bis auf die übersprungenen ist alles zugeordnet.'),
            style: textTheme.headlineSmall,
          ),
          if (_sorted > 0) ...[
            const SizedBox(height: 8),
            Text(
              _sorted == 1
                  ? 'Eine Buchung hat jetzt eine Kategorie.'
                  : '$_sorted Buchungen haben jetzt eine Kategorie.',
              style: textTheme.bodyLarge,
            ),
          ],
          const SizedBox(height: 20),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Fertig'),
          ),
        ],
      );
    } else {
      final income = current.amountCents > 0;
      final choices = widget.controller.categories
          .where(
            (category) =>
                category.kind == (income ? 'income' : 'expense') &&
                category.id != current.categoryId,
          )
          .toList();
      body = ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          Text(
            left == 1 ? 'Noch eine Buchung' : 'Noch $left Buchungen',
            style: textTheme.labelMedium,
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: klar.surface,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: klar.ink, width: 1.5),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  current.counterparty?.isNotEmpty == true
                      ? current.counterparty!
                      : 'Ohne Namen',
                  style: textTheme.titleLarge,
                ),
                const SizedBox(height: 6),
                Text(
                  '${income ? '+' : ''}${formatEuro(current.amountCents / 100)}',
                  style: textTheme.headlineMedium,
                ),
                const SizedBox(height: 6),
                Text(
                  [
                    _germanDate(current.bookingDate),
                    if (current.accountName?.isNotEmpty == true)
                      current.accountName!,
                  ].join(' · '),
                  style: textTheme.bodyMedium,
                ),
                if (current.purpose?.isNotEmpty == true) ...[
                  const SizedBox(height: 8),
                  Text(
                    current.purpose!,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: textTheme.bodyMedium,
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text('Wohin gehört das?', style: textTheme.labelMedium),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final category in choices)
                ActionChip(
                  label: Text(category.name),
                  onPressed: _saving ? null : () => _assign(current, category),
                ),
            ],
          ),
          const SizedBox(height: 16),
          if (_saving)
            const Center(
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            )
          else
            TextButton(
              onPressed: () => setState(() {
                _skipped.add(current.id);
                _lastResult = null;
              }),
              child: const Text('Überspringen'),
            ),
          if (_lastResult != null && !_saving) ...[
            const SizedBox(height: 6),
            Text(_lastResult!, style: textTheme.bodyMedium),
          ],
          if (_error != null) ...[
            const SizedBox(height: 6),
            Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
          ],
          const SizedBox(height: 14),
          Text(
            'Kassensturz merkt sich die Wahl für diesen Empfänger und ordnet '
            'ähnliche Buchungen gleich mit zu, auch künftige.',
            style: textTheme.bodySmall,
          ),
        ],
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Zuordnen')),
      body: SafeArea(child: body),
    );
  }
}

String _germanDate(String iso) {
  final day = DateTime.tryParse(iso);
  if (day == null) return iso;
  return '${day.day.toString().padLeft(2, '0')}.'
      '${day.month.toString().padLeft(2, '0')}.${day.year}';
}

/// Budgets proposed from the spending of the last full months, to accept one
/// by one or all at once.
class BudgetSuggestionsPage extends StatefulWidget {
  const BudgetSuggestionsPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<BudgetSuggestionsPage> createState() => _BudgetSuggestionsPageState();
}

class _BudgetSuggestionsPageState extends State<BudgetSuggestionsPage> {
  List<BudgetSuggestion> _items = const [];
  int _months = 0;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  int _accepted = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.loadBudgetSuggestions();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = result.error;
      _items = result.items;
      _months = result.months;
    });
  }

  Future<void> _accept(List<BudgetSuggestion> chosen) async {
    if (_saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    for (final suggestion in chosen) {
      final failure = await widget.controller.setBudget(
        suggestion.categoryId,
        suggestion.suggestedCents,
      );
      if (!mounted) return;
      if (failure != null) {
        setState(() {
          _saving = false;
          _error = failure;
        });
        return;
      }
      setState(() {
        _accepted += 1;
        _items = [
          for (final item in _items)
            if (item.categoryId != suggestion.categoryId) item,
        ];
      });
    }
    if (mounted) setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final span = _months == 1
        ? 'des letzten vollen Monats'
        : 'der letzten $_months vollen Monate';
    return Scaffold(
      appBar: AppBar(title: const Text('Budgets vorschlagen')),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
                children: [
                  if (_error != null)
                    Text(
                      _error!,
                      style: TextStyle(color: klar.warn, fontSize: 13),
                    )
                  else if (_months == 0)
                    const QuietMessage(
                      'Für einen Vorschlag braucht Kassensturz mindestens '
                      'einen vollen Monat an Buchungen.',
                    )
                  else if (_items.isEmpty)
                    QuietMessage(
                      _accepted > 0
                          ? 'Übernommen. Deine Budgets passen jetzt zu deinen '
                                'Ausgaben.'
                          : 'Deine Budgets passen schon zu deinen Ausgaben.',
                    )
                  else ...[
                    Text(
                      'Aus den Ausgaben $span, aufgerundet. Buchungen in '
                      '„Sonstiges“ zählen nicht mit; ordne sie zuerst zu, '
                      'dann werden die Vorschläge genauer.',
                      style: textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 14),
                    FilledButton(
                      onPressed: _saving ? null : () => _accept(_items),
                      child: Text(
                        _saving ? 'Wird übernommen …' : 'Alle übernehmen',
                      ),
                    ),
                    const SizedBox(height: 14),
                    for (final item in _items)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: Material(
                          color: klar.surface,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                            side: BorderSide(color: klar.border, width: 1.5),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        item.name,
                                        style: textTheme.titleMedium,
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        'Im Schnitt '
                                        '${formatEuro(item.averageCents / 100)}'
                                        '${item.currentCents == null ? ', bisher kein Budget' : ', bisher ${formatEuro(item.currentCents! / 100)}'}',
                                        style: textTheme.bodySmall,
                                      ),
                                    ],
                                  ),
                                ),
                                TextButton(
                                  onPressed: _saving
                                      ? null
                                      : () => _accept([item]),
                                  child: Text(
                                    formatEuro(item.suggestedCents / 100),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    Text(
                      'Tippe auf einen Betrag, um nur diesen zu übernehmen. '
                      'Ändern kannst du jedes Budget danach wie gewohnt.',
                      style: textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
      ),
    );
  }
}
