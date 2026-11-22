import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/design/app_theme.dart';
import '../../core/networking/mobile_connection_controller.dart';
import '../../core/networking/mobile_models.dart';

/// Zeigt, was eine Bank während eines Abrufs fragt, und sendet die Antwort: eine TAN,
/// welches Verfahren, oder dass der Zugriff in der Banking-App freigegeben wurde.
class BankQuestionPanel extends StatefulWidget {
  const BankQuestionPanel({
    required this.controller,
    required this.question,
    super.key,
  });

  final MobileConnectionController controller;
  final BankQuestion question;

  @override
  State<BankQuestionPanel> createState() => _BankQuestionPanelState();
}

class _BankQuestionPanelState extends State<BankQuestionPanel> {
  final _tan = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _tan.dispose();
    super.dispose();
  }

  Future<void> _send({String? value, bool cancel = false}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final error = await widget.controller.answerBankQuestion(
      widget.question.qid,
      value: value,
      cancel: cancel,
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = error;
    });
  }

  void _sendTan() {
    final tan = _tan.text.trim();
    if (tan.isEmpty) {
      setState(() => _error = 'Bitte gib die TAN ein.');
      return;
    }
    _send(value: tan);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final klar = KlarColors.of(context);
    final question = widget.question;
    final cancel = TextButton(
      onPressed: _busy ? null : () => _send(cancel: true),
      child: const Text('Abruf abbrechen'),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(switch (question.kind) {
          'tan' => '${question.bank} verlangt eine TAN',
          'decoupled' => '${question.bank}: Freigabe in der Banking-App',
          _ => question.bank,
        }, style: textTheme.titleMedium),
        const SizedBox(height: 4),
        if (question.kind == 'choice') ...[
          Text(question.title, style: textTheme.bodyMedium),
          const SizedBox(height: 6),
          for (final option in question.options)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: _busy ? null : () => _send(value: option.value),
                  child: Text(
                    option.hint.isEmpty
                        ? option.label
                        : '${option.label} (${option.hint})',
                  ),
                ),
              ),
            ),
        ] else
          Text(question.text, style: textTheme.bodyMedium),
        if (question.kind == 'tan') ...[
          if (question.image != null) ...[
            const SizedBox(height: 10),
            Center(
              child: Image.memory(
                question.image!,
                width: 260,
                filterQuality: FilterQuality.none,
                errorBuilder: (_, _, _) =>
                    const Text('Die Grafik ließ sich nicht anzeigen.'),
              ),
            ),
          ] else if (question.flicker.isNotEmpty) ...[
            const SizedBox(height: 10),
            _Flicker(frames: question.flicker),
          ],
          const SizedBox(height: 10),
          TextField(
            controller: _tan,
            enabled: !_busy,
            keyboardType: TextInputType.visiblePassword,
            autocorrect: false,
            enableSuggestions: false,
            autofillHints: const [AutofillHints.oneTimeCode],
            decoration: const InputDecoration(labelText: 'TAN'),
            onSubmitted: (_) => _sendTan(),
          ),
        ],
        if (_error != null) ...[
          const SizedBox(height: 8),
          Text(_error!, style: TextStyle(color: klar.warn, fontSize: 13)),
        ],
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (question.kind == 'tan')
              FilledButton(
                onPressed: _busy ? null : _sendTan,
                child: const Text('TAN senden'),
              ),
            if (question.kind == 'decoupled')
              FilledButton(
                onPressed: _busy ? null : () => _send(value: 'ok'),
                child: const Text('Ich habe freigegeben'),
              ),
            cancel,
          ],
        ),
      ],
    );
  }
}

/// Die fünf blinkenden Balken, an die ein chipTAN-Leser gehalten wird.
class _Flicker extends StatefulWidget {
  const _Flicker({required this.frames});

  final List<String> frames;

  @override
  State<_Flicker> createState() => _FlickerState();
}

class _FlickerState extends State<_Flicker> {
  Timer? _timer;
  int _frame = 0;
  int _millis = 80;

  @override
  void initState() {
    super.initState();
    _start();
  }

  void _start() {
    _timer?.cancel();
    _timer = Timer.periodic(Duration(milliseconds: _millis), (_) {
      if (mounted) setState(() => _frame += 1);
    });
  }

  void _speed(int change) {
    setState(() => _millis = (_millis + change).clamp(30, 200));
    _start();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final frame = widget.frames[_frame % widget.frames.length];
    return Column(
      children: [
        Container(
          color: Colors.black,
          padding: const EdgeInsets.all(10),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (var bar = 0; bar < 5; bar++)
                Container(
                  width: 34,
                  height: 90,
                  margin: const EdgeInsets.symmetric(horizontal: 5),
                  color: frame[bar] == '1' ? Colors.white : Colors.black,
                ),
            ],
          ),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextButton(
              onPressed: () => _speed(15),
              child: const Text('Langsamer'),
            ),
            TextButton(
              onPressed: () => _speed(-15),
              child: const Text('Schneller'),
            ),
          ],
        ),
      ],
    );
  }
}
