import 'dart:async';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

/// Läuft vor jeder Testdatei: gibt dem Plugin für sicheren Speicher einen leeren
/// Speicher im Arbeitsspeicher, damit beim App-Start gelesene Einstellungen (App-Sperre,
/// Update-Prüfung) antworten, statt auf eine nicht vorhandene Plattform zu warten.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  FlutterSecureStorage.setMockInitialValues({});
  await testMain();
}
