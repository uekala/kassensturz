import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/core/design/app_theme.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/networking/mobile_connection_controller.dart';
import 'package:kassensturz_mobile/features/accounts/net_worth_trend.dart';

import 'support/fake_server.dart';

Future<MobileConnectionController> _controller(
  List<Map<String, dynamic>> history,
) async {
  final transport = ScriptedTransport((request) {
    if (request.uri.path == '/api/v1/networth') {
      return jsonResponse(200, {'history': history});
    }
    return serverAnswer(
      request,
      capabilities: const [...fullCapabilities, 'networth'],
    );
  });
  final controller = MobileConnectionController(
    apiClient: MobileApiClient(
      sessionStore: await pairedStore(),
      transport: transport,
      refreshRetryDelay: Duration.zero,
    ),
    readRetryDelay: Duration.zero,
  );
  await controller.restore();
  return controller;
}

Future<void> _pump(
  WidgetTester tester,
  MobileConnectionController controller,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: NetWorthTrend(key: ObjectKey(controller), controller: controller),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the change since the first point is put into words', (
    tester,
  ) async {
    final controller = (await tester.runAsync(
      () => _controller([
        {'date': '2026-08-31', 'cents': 1200000},
        {'date': '2026-09-30', 'cents': 1150000},
        {'date': '2026-11-15', 'cents': 1385050},
      ]),
    ))!;
    addTearDown(controller.dispose);
    expect(controller.canShowNetWorthHistory, isTrue);
    await _pump(tester, controller);
    expect(find.text('+1.850,50 € seit Ende August 2026'), findsOneWidget);
    expect(find.byType(CustomPaint), findsWidgets);
  });

  testWidgets('a loss is named and a single point shows nothing', (
    tester,
  ) async {
    final loss = (await tester.runAsync(
      () => _controller([
        {'date': '2026-10-31', 'cents': 500000},
        {'date': '2026-11-15', 'cents': 420000},
      ]),
    ))!;
    addTearDown(loss.dispose);
    await _pump(tester, loss);
    expect(find.text('−800,00 € seit Ende Oktober 2026'), findsOneWidget);

    final single = (await tester.runAsync(
      () => _controller([
        {'date': '2026-11-15', 'cents': 420000},
      ]),
    ))!;
    addTearDown(single.dispose);
    await _pump(tester, single);
    expect(find.textContaining('seit Ende'), findsNothing);
  });
}
