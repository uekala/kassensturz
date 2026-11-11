import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';

void _useTallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 1800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  testWidgets('unpaired app asks to connect and shows no data', (tester) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());
    await tester.pumpAndSettle();

    expect(find.text('Noch nicht verbunden'), findsWidgets);
    expect(find.text('NICHT VERBUNDEN'), findsOneWidget);
    expect(find.text('Frei verfügbar'), findsNothing);

    for (final tab in ['Umsätze', 'Planung', 'Konten']) {
      await tester.tap(find.text(tab).last);
      await tester.pumpAndSettle();
      expect(find.text('Noch nicht verbunden'), findsWidgets);
    }
  });

  testWidgets('connect button opens the settings', (tester) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Mit Server verbinden').first);
    await tester.pumpAndSettle();

    expect(find.text('MIT DEINEM SERVER VERBINDEN'), findsOneWidget);
    expect(find.text('Gerät sicher koppeln'), findsOneWidget);
    expect(find.text('OFFLINE'), findsOneWidget);
    expect(find.text('https://dein-server.ts.net'), findsOneWidget);
  });

  testWidgets('plus button explains that a connection is needed', (
    tester,
  ) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Umsatz anlegen'));
    await tester.pump();

    expect(
      find.text('Verbinde die App zuerst mit deinem Kassensturz-Server.'),
      findsOneWidget,
    );
  });

  testWidgets('pairing form requires HTTPS server URL and a one-time code', (
    tester,
  ) async {
    _useTallViewport(tester);
    await tester.pumpWidget(const KassensturzApp());
    await tester.tap(find.byTooltip('Einstellungen'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Gerät sicher koppeln'));
    await tester.pumpAndSettle();

    expect(
      find.text('Bitte eine gültige HTTPS-Adresse eingeben.'),
      findsOneWidget,
    );
    expect(find.text('Der Pairing-Code ist ungültig.'), findsOneWidget);
    expect(find.text('OFFLINE'), findsOneWidget);
  });
}
