// Bildschirmfotos der App, gerendert mit echten Antworten des Servers.
//
// Erst die Antworten erzeugen, dann rendern:
//   python3 tools/app_fixture.py mobile/app/tool/bilder/server.json
//   cd mobile/app && flutter test tool/bilder/app_bilder.dart
// Die Bilder liegen danach unter mobile/app/build/app-bilder.
//
// Die Datei liegt mit Absicht nicht unter test/: Sie braucht die erzeugten
// Antworten und läuft deshalb nicht bei jedem "flutter test" mit.
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';

import '../../test/support/fake_server.dart';

const _answersPath = 'tool/bilder/server.json';
const _outputFolder = 'build/app-bilder';

/// What the server answered, per person: "anna" is an adult, "mia" a child.
late final Map<String, dynamic> _views;

/// Registers the fonts of the app. Without this, tests draw every letter as
/// a box.
Future<void> _loadFonts() async {
  final manifest =
      jsonDecode(await rootBundle.loadString('FontManifest.json'))
          as List<dynamic>;
  for (final entry in manifest) {
    final family = entry as Map<String, dynamic>;
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List<dynamic>) {
      final asset = (font as Map<String, dynamic>)['asset'] as String;
      loader.addFont(rootBundle.load(asset));
    }
    await loader.load();
  }
}

Map<String, dynamic> _answers(String view) =>
    _views[view] as Map<String, dynamic>;

/// The body of a recorded answer, for reading a name to tap on.
Map<String, dynamic> _body(String view, String path) {
  final answer = _answers(view)['GET $path'] as Map<String, dynamic>;
  return answer['body'] as Map<String, dynamic>;
}

MobileHttpResponse _replay(String view, RecordedRequest request) {
  final answer = _answers(view)['${request.method} ${request.uri.path}'];
  if (answer is Map<String, dynamic>) {
    return MobileHttpResponse(
      statusCode: answer['status'] as int,
      body: jsonEncode(answer['body']),
    );
  }
  if (request.method == 'POST') {
    return jsonResponse(200, {'ok': true});
  }
  return errorResponse(404, 'not_found', 'Unbekannt.');
}

/// One running app on a phone-sized screen.
class _Phone {
  _Phone(this.tester, this.frame);

  final WidgetTester tester;
  final GlobalKey frame;

  /// Things a scene looked for and did not find.
  final missing = <String>[];

  static Future<_Phone> start(
    WidgetTester tester, {
    String view = 'anna',
    bool dark = false,
  }) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    if (dark) {
      tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
      addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
    }
    final controller = MobileConnectionController(
      apiClient: MobileApiClient(
        sessionStore: await pairedStore(),
        transport: ScriptedTransport((request) => _replay(view, request)),
        refreshRetryDelay: Duration.zero,
      ),
      readRetryDelay: Duration.zero,
    );
    final frame = GlobalKey();
    await tester.pumpWidget(
      RepaintBoundary(
        key: frame,
        child: KassensturzApp(mobileConnectionController: controller),
      ),
    );
    await tester.pumpAndSettle();
    return _Phone(tester, frame);
  }

  /// Saves what is on the screen, twice as sharp as the screen is large.
  Future<void> shot(String name) async {
    await tester.pumpAndSettle();
    final boundary =
        frame.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    await tester.runAsync(() async {
      final image = await boundary.toImage(pixelRatio: 2);
      final data = await image.toByteData(format: ui.ImageByteFormat.png);
      image.dispose();
      final file = File('$_outputFolder/$name.png');
      await file.parent.create(recursive: true);
      await file.writeAsBytes(data!.buffer.asUint8List());
    });
  }

  /// Scrolls the visible page down by [distance].
  Future<void> down([double distance = 520]) async {
    await tester.dragFrom(const Offset(195, 560), Offset(0, -distance));
    await tester.pumpAndSettle();
  }

  /// Scrolls until [target] can be tapped, then taps it. Looks further down
  /// first and then back up, so it does not matter where the page stands.
  Future<bool> open(Finder target, String what) async {
    for (final distance in [300.0, -300.0]) {
      for (var step = 0; step < 14; step++) {
        final visible = target.hitTestable();
        if (visible.evaluate().isNotEmpty) {
          await tester.tap(visible.first);
          await tester.pumpAndSettle();
          return true;
        }
        await down(distance);
      }
    }
    missing.add(what);
    return false;
  }

  /// Switches to one of the four tabs at the bottom.
  Future<void> tab(String label) async {
    final visible = find.text(label).hitTestable();
    if (visible.evaluate().isEmpty) {
      missing.add('Reiter $label');
      return;
    }
    await tester.tap(visible.last);
    await tester.pumpAndSettle();
  }

  /// Closes the page, sheet or dialog on top.
  Future<void> back() async {
    tester.state<NavigatorState>(find.byType(Navigator).first).pop();
    await tester.pumpAndSettle();
  }

  void done() {
    expect(missing, isEmpty, reason: 'Nicht gefunden: ${missing.join(', ')}');
  }
}

/// A test that draws real shadows; the test default paints them as blocks.
void _scene(String name, Future<void> Function(WidgetTester tester) body) {
  testWidgets(name, (tester) async {
    debugDisableShadows = false;
    try {
      await body(tester);
    } finally {
      debugDisableShadows = true;
    }
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  // This file is a test, it only lives outside test/ (see the note on top).
  // ignore: invalid_use_of_visible_for_testing_member
  FlutterSecureStorage.setMockInitialValues({});

  setUpAll(() async {
    final file = File(_answersPath);
    if (!file.existsSync()) {
      fail(
        'Es fehlt $_answersPath. Erst tools/app_fixture.py laufen lassen.',
      );
    }
    final content = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    _views = content['views'] as Map<String, dynamic>;
    await _loadFonts();
  });

  _scene('Heute, Leisten, Papierkram, Auswertung', (tester) async {
    final phone = await _Phone.start(tester);
    await phone.shot('01-heute');
    if (await phone.open(find.text('Kann ich mir das leisten?'), 'Leisten')) {
      await tester.enterText(find.byType(TextField).hitTestable(), '300');
      await tester.tap(find.text('Prüfen').hitTestable());
      await phone.shot('03-leisten');
      await phone.back();
    }
    if (await phone.open(find.text('Steuer und Garantien'), 'Papierkram')) {
      await phone.shot('04-steuer-und-garantien');
      await phone.back();
    }
    if (await phone.open(find.text('Auswertung'), 'Auswertung')) {
      await phone.shot('05-auswertung');
      await phone.down();
      await phone.shot('06-auswertung-unten');
      await phone.back();
    }
    await phone.down();
    await phone.shot('02-heute-unten');
    phone.done();
  });

  _scene('Umsätze und Buchung', (tester) async {
    final phone = await _Phone.start(tester);
    await phone.tab('Umsätze');
    await phone.shot('07-umsaetze');
    final items =
        (_body('anna', '/api/v1/transactions')['items'] as List<dynamic>)
            .cast<Map<String, dynamic>>();
    // An ordinary expense from the bank, not the pocket money on top.
    final first = items.firstWhere(
      (item) => (item['amount_cents'] as int) < 0,
      orElse: () => items.first,
    );
    final title = first['counterparty'].toString();
    if (await phone.open(find.text(title), 'Buchung $title')) {
      await phone.shot('08-buchung');
      await phone.down();
      await phone.shot('09-buchung-unten');
      await phone.back();
    }
    if (await phone.open(find.byTooltip('Umsatz anlegen'), 'Umsatz anlegen')) {
      await phone.shot('10-neuer-umsatz');
      await phone.back();
    }
    phone.done();
  });

  _scene('Planung, Budgets, Verträge', (tester) async {
    final phone = await _Phone.start(tester);
    await phone.tab('Planung');
    await phone.shot('11-planung');
    if (await phone.open(find.text('Budgets vorschlagen'), 'Vorschläge')) {
      await phone.shot('13-budget-vorschlaege');
      await phone.back();
    }
    if (await phone.open(find.text('Projekte'), 'Projekte')) {
      await phone.shot('28-projekte');
      if (await phone.open(find.text('Auto'), 'Projekt Auto')) {
        await phone.shot('29-projekt');
        await phone.back();
      }
      await phone.back();
    }
    await phone.down();
    await phone.shot('12-planung-unten');
    await phone.tab('Verträge');
    await phone.shot('14-vertraege');
    final contracts =
        _body('anna', '/api/v1/contracts')['items'] as List<dynamic>;
    final name = (contracts.first as Map<String, dynamic>)['name'].toString();
    if (await phone.open(find.text(name), 'Vertrag $name')) {
      await phone.shot('15-vertrag');
      await phone.back();
    }
    phone.done();
  });

  _scene('Konten und Haushalt', (tester) async {
    final phone = await _Phone.start(tester);
    await phone.tab('Konten');
    await phone.shot('16-konten');
    if (await phone.open(
      find.text('Geteilte Ausgaben und Ausgleich'),
      'Haushalt',
    )) {
      await phone.shot('17-haushalt');
      await phone.back();
    }
    await phone.down();
    await phone.shot('18-konten-unten');
    if (await phone.open(find.text('Autokredit'), 'Tilgungsplan')) {
      await phone.shot('30-tilgungsplan');
      await phone.back();
    }
    phone.done();
  });

  _scene('Einstellungen', (tester) async {
    final phone = await _Phone.start(tester);
    if (await phone.open(find.byTooltip('Einstellungen'), 'Einstellungen')) {
      await phone.shot('19-einstellungen');
    }
    phone.done();
  });

  _scene('Handy eines Kindes', (tester) async {
    final phone = await _Phone.start(tester, view: 'mia');
    // A child's phone is read-only on purpose; nothing there may suggest
    // that the server is outdated or that something can be added.
    expect(find.textContaining('aktualisieren'), findsNothing);
    expect(find.byTooltip('Umsatz anlegen'), findsNothing);
    expect(find.text('Dein Geld'), findsOneWidget);
    await phone.shot('20-kind-heute');
    await phone.tab('Umsätze');
    await phone.shot('21-kind-umsaetze');
    await phone.tab('Planung');
    await phone.shot('22-kind-planung');
    await phone.tab('Konten');
    await phone.shot('23-kind-konten');
    phone.done();
  });

  _scene('Dunkel', (tester) async {
    final phone = await _Phone.start(tester, dark: true);
    await phone.shot('24-dunkel-heute');
    await phone.tab('Umsätze');
    await phone.shot('25-dunkel-umsaetze');
    await phone.tab('Planung');
    await phone.shot('26-dunkel-planung');
    await phone.tab('Konten');
    await phone.shot('27-dunkel-konten');
    phone.done();
  });
}
