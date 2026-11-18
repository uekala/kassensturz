import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';

List<Map<String, dynamic>> _maps(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
}

int _int(dynamic value) => value is int ? value : 0;

const _monthNames = [
  'Januar',
  'Februar',
  'März',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
];

String _monthLabel(String month) {
  final parts = month.split('-');
  if (parts.length != 2) return month;
  final index = int.tryParse(parts[1]) ?? 0;
  if (index < 1 || index > 12) return month;
  return '${_monthNames[index - 1]} ${parts[0]}';
}

String _span(Map<String, dynamic> project) {
  final count = _int(project['count']);
  if (count == 0) return 'Noch keine Buchungen';
  final first = project['first']?.toString() ?? '';
  final last = project['last']?.toString() ?? '';
  final when = first == last
      ? formatShortDate(first)
      : '${formatShortDate(first)} bis ${formatShortDate(last)}';
  return '$count ${count == 1 ? 'Buchung' : 'Buchungen'}, $when';
}

/// Projects with their total costs. Opens one with a tap.
class ProjectsPage extends StatefulWidget {
  const ProjectsPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<ProjectsPage> createState() => _ProjectsPageState();
}

class _ProjectsPageState extends State<ProjectsPage> {
  List<Map<String, dynamic>>? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.readOnce((api) => api.projects());
    if (!mounted) return;
    setState(() {
      _items = result.data == null ? null : _maps(result.data!['items']);
      _error = result.error;
    });
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Projekte')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            Text(
              'Was der Urlaub, das Auto oder die Renovierung insgesamt '
              'gekostet hat, über alle Kategorien und Monate. Anlegen geht in '
              'Kassensturz in Home Assistant; Buchungen ordnest du auch hier '
              'an der Buchung zu.',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            if (items == null && _error == null)
              const Center(child: CircularProgressIndicator())
            else if (items == null)
              QuietMessage(_error ?? 'Die Projekte ließen sich nicht laden.')
            else if (items.isEmpty)
              const QuietMessage('Noch keine Projekte.')
            else
              for (final project in items)
                _ProjectRow(
                  project: project,
                  onTap: () => Navigator.of(context).push<void>(
                    MaterialPageRoute(
                      builder: (_) => ProjectDetailPage(
                        controller: widget.controller,
                        projectId: _int(project['id']),
                        name: project['name']?.toString() ?? 'Projekt',
                      ),
                    ),
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

class _ProjectRow extends StatelessWidget {
  const _ProjectRow({required this.project, required this.onTap});

  final Map<String, dynamic> project;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final budget = project['budget_cents'];
    final left = project['left_cents'];
    final note = [
      _span(project),
      if (project['archived'] == true) 'abgeschlossen',
      if (budget is int && left is int)
        left >= 0
            ? 'noch ${formatEuro(left / 100)} im Rahmen'
            : '${formatEuro(-left / 100)} über dem Rahmen',
    ].join(' · ');
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: OutlinedPanel(
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      project['name']?.toString() ?? 'Projekt',
                      style: textTheme.titleMedium,
                    ),
                    const SizedBox(height: 3),
                    Text(
                      note,
                      style: textTheme.bodySmall?.copyWith(
                        color: left is int && left < 0 ? klar.warn : null,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Text(
                formatEuro(_int(project['cost_cents']) / 100),
                style: textTheme.titleMedium,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One project: total, frame, costs by category and month, bookings.
class ProjectDetailPage extends StatefulWidget {
  const ProjectDetailPage({
    required this.controller,
    required this.projectId,
    required this.name,
    super.key,
  });

  final MobileConnectionController controller;
  final int projectId;
  final String name;

  @override
  State<ProjectDetailPage> createState() => _ProjectDetailPageState();
}

class _ProjectDetailPageState extends State<ProjectDetailPage> {
  Map<String, dynamic>? _data;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.readOnce(
      (api) => api.project(widget.projectId),
    );
    if (!mounted) return;
    setState(() {
      _data = result.data;
      _error = result.error;
    });
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return Scaffold(
      appBar: AppBar(title: Text(widget.name)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: data == null
              ? [
                  if (_error == null)
                    const Center(child: CircularProgressIndicator())
                  else
                    QuietMessage(_error!),
                ]
              : _content(context, data),
        ),
      ),
    );
  }

  List<Widget> _content(BuildContext context, Map<String, dynamic> data) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final cost = _int(data['cost_cents']);
    final budget = data['budget_cents'];
    final left = data['left_cents'];
    final back = _int(data['back_cents']);
    final categories = _maps(data['categories']);
    final months = _maps(data['months']);
    final bookings = _maps(data['transactions']);
    final top = categories.isEmpty ? 1 : _int(categories.first['cents']);
    return [
      AmountHeadline(
        label: 'Gekostet',
        amount: formatEuro(cost / 100),
        note: [
          _span(data),
          if (back > 0)
            'ausgegeben ${formatEuro(_int(data['spent_cents']) / 100)}, '
                'zurückbekommen ${formatEuro(back / 100)}',
        ].join(' · '),
        size: 40,
      ),
      if (budget is int && budget > 0 && left is int) ...[
        const SizedBox(height: 12),
        ThickBar(
          value: (cost / budget).clamp(0.0, 1.0).toDouble(),
          over: left < 0,
          height: 12,
        ),
        const SizedBox(height: 6),
        Text(
          left >= 0
              ? 'Noch ${formatEuro(left / 100)} von '
                    '${formatEuro(budget / 100)} im Rahmen.'
              : '${formatEuro(-left / 100)} über dem Rahmen von '
                    '${formatEuro(budget / 100)}.',
          style: textTheme.bodySmall?.copyWith(
            color: left < 0 ? klar.warn : null,
          ),
        ),
      ],
      if (categories.isNotEmpty) ...[
        const SizedBox(height: 24),
        const SectionTitle('Nach Kategorie'),
        const SizedBox(height: 8),
        for (final category in categories) ...[
          Row(
            children: [
              Expanded(
                child: Text(
                  category['name']?.toString() ?? '',
                  style: textTheme.bodyMedium,
                ),
              ),
              Text(
                formatEuro(_int(category['cents']) / 100),
                style: textTheme.bodyMedium,
              ),
            ],
          ),
          const SizedBox(height: 4),
          ThickBar(
            value: top <= 0
                ? 0.0
                : (_int(category['cents']) / top).clamp(0.0, 1.0).toDouble(),
            height: 8,
          ),
          const SizedBox(height: 10),
        ],
      ],
      if (months.length > 1) ...[
        const SizedBox(height: 14),
        const SectionTitle('Nach Monat'),
        for (final month in months)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _monthLabel(month['month']?.toString() ?? ''),
                    style: textTheme.bodyMedium,
                  ),
                ),
                Text(
                  formatEuro(_int(month['cents']) / 100),
                  style: textTheme.bodyMedium,
                ),
              ],
            ),
          ),
      ],
      if (bookings.isNotEmpty) ...[
        const SizedBox(height: 18),
        const SectionTitle('Buchungen'),
        for (final booking in bookings)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        booking['counterparty']?.toString() ?? 'Buchung',
                        style: textTheme.titleMedium,
                      ),
                      Text(
                        [
                          formatShortDate(
                            booking['booking_date']?.toString() ?? '',
                          ),
                          booking['transfer'] == true
                              ? 'Umbuchung, zählt nicht'
                              : booking['category']?.toString() ?? '',
                        ].where((part) => part.isNotEmpty).join(', '),
                        style: textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                Text(
                  formatSignedEuro(_int(booking['amount_cents']) / 100),
                  style: textTheme.titleMedium,
                ),
              ],
            ),
          ),
      ],
    ];
  }
}
