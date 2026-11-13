import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';
import 'package:kassensturz_mobile/core/security/app_lock.dart';

void main() {
  testWidgets('a locked app shows nothing until the owner confirms', (
    tester,
  ) async {
    var allow = false;
    var asked = 0;
    final lock = AppLock.inMemory(
      enabled: true,
      authenticate: (_) async {
        asked++;
        return allow;
      },
    );
    await tester.pumpWidget(KassensturzApp(appLock: lock));
    await tester.pumpAndSettle();

    expect(asked, 1);
    expect(find.text('Kassensturz ist gesperrt'), findsOneWidget);
    expect(find.byTooltip('Einstellungen').hitTestable(), findsNothing);

    allow = true;
    await tester.tap(find.text('Entsperren'));
    await tester.pumpAndSettle();
    expect(asked, 2);
    expect(find.text('Kassensturz ist gesperrt'), findsNothing);
    expect(find.byTooltip('Einstellungen').hitTestable(), findsOneWidget);
  });

  testWidgets('locks again after a minute in the background', (tester) async {
    var asked = 0;
    final lock = AppLock.inMemory(
      enabled: true,
      authenticate: (_) async {
        asked++;
        return true;
      },
    );
    await tester.pumpWidget(
      MaterialApp(
        home: AppLockGate(
          lock: lock,
          relockAfter: Duration.zero,
          child: const Text('Inhalt'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(asked, 1);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(asked, 2);
  });

  testWidgets('without the setting or a screen lock the app stays open', (
    tester,
  ) async {
    var asked = 0;
    Future<bool> authenticate(String _) async {
      asked++;
      return false;
    }

    for (final lock in [
      AppLock.inMemory(authenticate: authenticate),
      AppLock.inMemory(
        enabled: true,
        supported: false,
        authenticate: authenticate,
      ),
    ]) {
      await tester.pumpWidget(
        MaterialApp(
          key: UniqueKey(),
          home: AppLockGate(lock: lock, child: const Text('Inhalt')),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Kassensturz ist gesperrt'), findsNothing);
    }
    expect(asked, 0);
  });

  testWidgets('the switch needs the confirmation in both directions', (
    tester,
  ) async {
    var allow = false;
    final lock = AppLock.inMemory(authenticate: (_) async => allow);
    await tester.pumpWidget(KassensturzApp(appLock: lock));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Einstellungen'));
    await tester.pumpAndSettle();
    await tester.dragUntilVisible(
      find.text('App-Sperre'),
      find.byType(ListView).last,
      const Offset(0, -300),
    );

    await tester.tap(find.widgetWithText(SwitchListTile, 'App-Sperre'));
    await tester.pumpAndSettle();
    expect(await lock.enabled, isFalse);
    expect(find.text('Nicht bestätigt, nichts geändert.'), findsOneWidget);

    allow = true;
    await tester.tap(find.widgetWithText(SwitchListTile, 'App-Sperre'));
    await tester.pumpAndSettle();
    expect(await lock.enabled, isTrue);

    allow = false;
    await tester.tap(find.widgetWithText(SwitchListTile, 'App-Sperre'));
    await tester.pumpAndSettle();
    expect(await lock.enabled, isTrue);
  });

  test('errors of the phone never lock the owner out', () async {
    final lock = AppLock(
      read: () => throw StateError('kaputt'),
      write: (_) async {},
      deviceSupported: () => throw StateError('kaputt'),
      authenticate: (_) => throw StateError('kaputt'),
    );
    expect(await lock.enabled, isFalse);
    expect(await lock.supported, isFalse);
    expect(await lock.unlock('x'), isFalse);
  });
}
