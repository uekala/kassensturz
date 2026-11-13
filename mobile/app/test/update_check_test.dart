import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kassensturz_mobile/app/kassensturz_app.dart';
import 'package:kassensturz_mobile/core/networking/mobile_api_client.dart';
import 'package:kassensturz_mobile/core/update/update_check.dart';

import 'support/fake_server.dart';

Map<String, Object?> _release(
  String tag, {
  bool apk = true,
  bool draft = false,
  bool prerelease = false,
}) {
  final version = tag.replaceFirst('mobile-v', '');
  return {
    'tag_name': tag,
    'html_url': 'https://github.com/uekala/kassensturz/releases/tag/$tag',
    'draft': draft,
    'prerelease': prerelease,
    'assets': [
      if (apk)
        {
          'name': 'kassensturz-$version.apk',
          'browser_download_url':
              'https://github.com/uekala/kassensturz/releases/download/$tag/'
              'kassensturz-$version.apk',
        },
    ],
  };
}

UpdateChecker _checker(
  ScriptedTransport transport, {
  String version = '0.3.7',
  bool android = true,
  bool enabled = true,
}) => UpdateChecker(
  transport: transport,
  preference: InMemoryUpdatePreference(enabled),
  currentVersion: version,
  isAndroid: android,
);

void main() {
  test('versions are compared by number', () {
    expect(isNewerVersion('0.3.10', '0.3.9'), isTrue);
    expect(isNewerVersion('0.4.0', '0.3.99'), isTrue);
    expect(isNewerVersion('0.3.7', '0.3.7'), isFalse);
    expect(isNewerVersion('0.3.6', '0.3.7'), isFalse);
    expect(isNewerVersion('abc', '0.3.7'), isFalse);
    expect(isNewerVersion('0.3.8', ''), isFalse);
  });

  test('picks the newest app release and ignores everything else', () {
    final update = updateFromReleases([
      _release('v0.9.0'),
      _release('mobile-v0.3.9', draft: true),
      _release('mobile-v0.4.0', prerelease: true),
      _release('mobile-v0.3.10', apk: false),
      _release('mobile-v0.3.8'),
      _release('mobile-v0.3.9'),
      _release('mobile-v0.3.6'),
      'kaputt',
    ], '0.3.7');
    expect(update!.version, '0.3.9');
    expect(
      update.downloadUrl,
      endsWith('/mobile-v0.3.9/kassensturz-0.3.9.apk'),
    );
    expect(updateFromReleases([_release('mobile-v0.3.7')], '0.3.7'), isNull);
    expect(updateFromReleases({'tag_name': 'mobile-v9.9.9'}, '0.3.7'), isNull);
  });

  test('an APK from another place is not offered', () {
    final release = _release('mobile-v0.3.9');
    (release['assets']! as List).single['browser_download_url'] =
        'https://example.org/kassensturz-0.3.9.apk';
    expect(updateFromReleases([release], '0.3.7'), isNull);
  });

  test('asks GitHub without credentials', () async {
    final transport = ScriptedTransport(
      (_) => MobileHttpResponse(
        statusCode: 200,
        body: jsonEncode([_release('mobile-v0.3.8')]),
      ),
    );
    final update = await _checker(transport).check();
    expect(update!.version, '0.3.8');
    final request = transport.requests.single;
    expect(request.uri.host, 'api.github.com');
    expect(request.uri.path, '/repos/uekala/kassensturz/releases');
    expect(request.headers.keys, isNot(contains('Authorization')));
  });

  test('stays silent when switched off, unsupported or failing', () async {
    final ok = ScriptedTransport(
      (_) => MobileHttpResponse(
        statusCode: 200,
        body: jsonEncode([_release('mobile-v0.3.8')]),
      ),
    );
    expect(await _checker(ok, enabled: false).check(), isNull);
    expect(await _checker(ok, android: false).check(), isNull);
    expect(await _checker(ok, version: '').check(), isNull);
    expect(ok.requests, isEmpty);

    final limited = ScriptedTransport(
      (_) => const MobileHttpResponse(statusCode: 403, body: '{}'),
    );
    expect(await _checker(limited).check(), isNull);
    final broken = ScriptedTransport(
      (_) => const MobileHttpResponse(statusCode: 200, body: 'kein json'),
    );
    expect(await _checker(broken).check(), isNull);
    final offline = ScriptedTransport(
      (_) => throw const MobileNetworkException(
        MobileNetworkFailure.unreachable,
        requestSent: false,
      ),
    );
    expect(await _checker(offline).check(), isNull);
  });

  testWidgets('the app shows a banner and a switch in the settings', (
    tester,
  ) async {
    final transport = ScriptedTransport(
      (_) => MobileHttpResponse(
        statusCode: 200,
        body: jsonEncode([_release('mobile-v0.3.8')]),
      ),
    );
    final checker = _checker(transport);
    await tester.pumpWidget(KassensturzApp(updateChecker: checker));
    await tester.pumpAndSettle();

    expect(
      find.text('Kassensturz 0.3.8 ist verfügbar (installiert: 0.3.7).'),
      findsOneWidget,
    );
    expect(find.text('Update laden'), findsOneWidget);
    await tester.tap(find.text('Später'));
    await tester.pumpAndSettle();
    expect(find.text('Update laden'), findsNothing);

    await tester.tap(find.byTooltip('Einstellungen'));
    await tester.pumpAndSettle();
    await tester.dragUntilVisible(
      find.text('Nach App-Updates suchen'),
      find.byType(ListView).last,
      const Offset(0, -300),
    );
    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    expect(await checker.enabled, isFalse);
  });
}
