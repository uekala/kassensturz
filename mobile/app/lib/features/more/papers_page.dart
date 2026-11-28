import 'package:material_ui/material_ui.dart';

import '../../core/design/app_theme.dart';
import '../../core/formatting.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';
import '../../core/widgets/klar_widgets.dart';

/// Steuerübersicht je Jahr und die Garantien, nur zum Lesen. Einen Umsatz markieren
/// und Belege hinzufügen geschieht im Umsatz selbst.
class PapersPage extends StatefulWidget {
  const PapersPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<PapersPage> createState() => _PapersPageState();
}

class _PapersPageState extends State<PapersPage> {
  PapersOverview? _data;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({int? year}) async {
    setState(() => _loading = true);
    final result = await widget.controller.loadPapers(year: year);
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = result.error;
      _data = result.data ?? _data;
    });
  }

  static String _date(String iso) {
    final day = DateTime.tryParse(iso);
    if (day == null) return iso;
    return '${day.day.toString().padLeft(2, '0')}.'
        '${day.month.toString().padLeft(2, '0')}.${day.year}';
  }

  static String _left(int days) => switch (days) {
    0 => 'endet heute',
    1 => 'noch 1 Tag',
    < 60 => 'noch $days Tage',
    _ => 'noch ${(days / 30.4).round()} Monate',
  };

  @override
  Widget build(BuildContext context) {
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final data = _data;
    final years = data == null
        ? const <int>[]
        : (data.years.contains(data.year)
              ? data.years
              : [data.year, ...data.years]);

    Widget row(String title, String detail, String value, {bool warn = false}) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(
                    detail,
                    style: textTheme.bodySmall?.copyWith(
                      color: warn ? klar.warn : null,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Text(value, style: textTheme.titleMedium),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Steuer und Garantien')),
      body: SafeArea(
        child: _loading && data == null
            ? const Center(child: CircularProgressIndicator())
            : data == null
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _error ?? 'Die Übersicht ließ sich nicht laden.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : RefreshIndicator(
                onRefresh: () => _load(year: data.year),
                child: ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
                  children: [
                    Text('Steuer', style: textTheme.headlineSmall),
                    const SizedBox(height: 8),
                    if (years.length > 1)
                      Wrap(
                        spacing: 8,
                        children: [
                          for (final year in years)
                            ChoiceChip(
                              label: Text('$year'),
                              selected: year == data.year,
                              onSelected: (_) => _load(year: year),
                            ),
                        ],
                      ),
                    if (data.groups.isEmpty)
                      const QuietMessage(
                        'Noch nichts markiert. Öffne eine Buchung und wähle '
                        '„Für die Steuererklärung“.',
                      )
                    else ...[
                      for (final group in data.groups)
                        row(
                          group.label,
                          '${group.count == 1 ? '1 Buchung' : '${group.count} Buchungen'}'
                          '${group.missingReceipts > 0 ? ', ${group.missingReceipts} ohne Beleg' : ''}',
                          formatEuro(group.totalCents / 100),
                          warn: group.missingReceipts > 0,
                        ),
                      const SizedBox(height: 4),
                      Text(
                        'Zusammen ${formatEuro(data.totalCents / 100)} in '
                        '${data.year}. Die Liste als Datei gibt es in '
                        'Kassensturz in Home Assistant.',
                        style: textTheme.bodySmall,
                      ),
                    ],
                    const SizedBox(height: 26),
                    Text('Garantien', style: textTheme.headlineSmall),
                    const SizedBox(height: 8),
                    if (data.running.isEmpty && data.expired.isEmpty)
                      const QuietMessage(
                        'Noch keine Garantie eingetragen. Öffne einen Kauf '
                        'und setze „Garantie bis“.',
                      ),
                    for (final item in data.running)
                      row(
                        item.label,
                        '${formatEuro(item.amountCents.abs() / 100)}, '
                        '${_left(item.daysLeft)}'
                        '${item.hasReceipt ? '' : ', ohne Beleg'}',
                        _date(item.until),
                        warn: item.daysLeft <= 30,
                      ),
                    if (data.expired.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      Text('Kürzlich abgelaufen', style: textTheme.labelMedium),
                      for (final item in data.expired)
                        row(
                          item.label,
                          '${formatEuro(item.amountCents.abs() / 100)}, '
                          'abgelaufen',
                          _date(item.until),
                        ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: 10),
                      Text(
                        _error!,
                        style: TextStyle(color: klar.warn, fontSize: 13),
                      ),
                    ],
                  ],
                ),
              ),
      ),
    );
  }
}
