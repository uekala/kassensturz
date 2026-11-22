import 'package:flutter/widgets.dart';

import 'app/kassensturz_app.dart';
import 'core/networking/mobile_api_client.dart';
import 'core/networking/mobile_connection_controller.dart';
import 'core/networking/mobile_session_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Die App führt keine Finanzdaten auf dem Gerät: Konten, Budgets und Umsätze
  // kommen nur vom gekoppelten Kassensturz-Server. Dateien von Versionen vor
  // 0.2.0 bleiben unberührt und werden nicht gelesen.
  runApp(
    KassensturzApp(
      mobileConnectionController: MobileConnectionController(
        apiClient: MobileApiClient(sessionStore: SecureMobileSessionStore()),
      ),
    ),
  );
}
