import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';

/// The project of a transaction, with a picker to change it. Shows nothing
/// while there are no projects.
class ProjectSection extends StatefulWidget {
  const ProjectSection({
    required this.controller,
    required this.transactionId,
    super.key,
  });

  final MobileConnectionController controller;
  final int transactionId;

  @override
  State<ProjectSection> createState() => _ProjectSectionState();
}

class _ProjectSectionState extends State<ProjectSection> {
  int? _current;
  List<({int id, String name})> _options = const [];
  bool _loaded = false;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final result = await widget.controller.readOnce(
      (api) => api.transactionProject(widget.transactionId),
    );
    if (!mounted) return;
    final data = result.data;
    final raw = data?['projects'];
    setState(() {
      _loaded = true;
      final current = data?['project_id'];
      _current = current is int ? current : null;
      _options = [
        if (raw is List)
          for (final item in raw.whereType<Map>())
            if (item['id'] is int)
              (id: item['id'] as int, name: item['name']?.toString() ?? ''),
      ];
    });
  }

  String get _label {
    for (final option in _options) {
      if (option.id == _current) return option.name;
    }
    return 'Keines';
  }

  Future<void> _pick() async {
    final picked = await showDialog<int>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: const Text('Projekt'),
        children: [
          SimpleDialogOption(
            onPressed: () => Navigator.of(dialogContext).pop(0),
            child: const Text('Keines'),
          ),
          for (final option in _options)
            SimpleDialogOption(
              onPressed: () => Navigator.of(dialogContext).pop(option.id),
              child: Text(option.name),
            ),
        ],
      ),
    );
    if (picked == null || !mounted) return;
    final next = picked == 0 ? null : picked;
    if (next == _current) return;
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _saving = true);
    final error = await widget.controller.setTransactionProject(
      widget.transactionId,
      next,
    );
    if (!mounted) return;
    setState(() {
      _saving = false;
      if (error == null) _current = next;
    });
    messenger.showSnackBar(
      SnackBar(content: Text(error ?? 'Projekt gespeichert')),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded || _options.isEmpty) return const SizedBox.shrink();
    final klar = KlarColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Projekt', style: textTheme.labelMedium),
          const SizedBox(height: 6),
          Material(
            color: klar.surface,
            clipBehavior: Clip.antiAlias,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: BorderSide(color: klar.fieldBorder, width: 1.5),
            ),
            child: InkWell(
              onTap: _saving ? null : _pick,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 14,
                ),
                child: Row(
                  children: [
                    Expanded(child: Text(_label, style: textTheme.bodyLarge)),
                    const Icon(Icons.expand_more_rounded),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
