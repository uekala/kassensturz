import 'package:material_ui/material_ui.dart';

import '../../core/networking/mobile_connection_controller.dart';
import '../../core/widgets/klar_widgets.dart';

String _stamp(String value) {
  final at = DateTime.tryParse(value);
  if (at == null) return value;
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(at.day)}.${two(at.month)}.${at.year}, '
      '${two(at.hour)}:${two(at.minute)} Uhr';
}

/// Das Änderungsprotokoll: wer was in Home Assistant oder auf einem Handy geändert hat.
class ChangesPage extends StatefulWidget {
  const ChangesPage({required this.controller, super.key});

  final MobileConnectionController controller;

  @override
  State<ChangesPage> createState() => _ChangesPageState();
}

class _ChangesPageState extends State<ChangesPage> {
  final _items = <Map<String, dynamic>>[];
  int _total = 0;
  bool _loading = false;
  bool _loaded = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  Future<void> _load({required bool reset}) async {
    if (_loading) return;
    setState(() => _loading = true);
    final offset = reset ? 0 : _items.length;
    final result = await widget.controller.readOnce(
      (api) => api.changes(offset: offset),
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      _loaded = true;
      _error = result.error;
      final data = result.data;
      if (data == null) return;
      if (reset) _items.clear();
      final raw = data['items'];
      if (raw is List) {
        _items.addAll(raw.whereType<Map>().map(Map<String, dynamic>.from));
      }
      final total = data['total'];
      _total = total is int ? total : _items.length;
    });
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Änderungen')),
      body: RefreshIndicator(
        onRefresh: () => _load(reset: true),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            Text(
              'Wer wann was geändert hat, in Home Assistant oder am Handy. '
              'Bankabrufe und was Kassensturz von selbst erledigt, stehen '
              'nicht darin. Du siehst nur Einträge zu Konten, die du siehst.',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 14),
            if (!_loaded)
              const Center(child: CircularProgressIndicator())
            else if (_items.isEmpty)
              QuietMessage(_error ?? 'Noch nichts geändert.')
            else ...[
              for (final item in _items)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 9),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item['text']?.toString() ?? '',
                        style: textTheme.bodyLarge,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        [
                          item['actor']?.toString() ?? '',
                          if (item['phone'] == true) 'am Handy',
                          _stamp(item['at']?.toString() ?? ''),
                        ].where((part) => part.isNotEmpty).join(', '),
                        style: textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              if (_items.length < _total)
                Center(
                  child: TextButton(
                    onPressed: _loading ? null : () => _load(reset: false),
                    child: Text(_loading ? 'Lädt …' : 'Weitere laden'),
                  ),
                ),
              if (_error != null) QuietMessage(_error!),
            ],
          ],
        ),
      ),
    );
  }
}
