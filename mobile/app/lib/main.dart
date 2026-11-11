import 'package:flutter/widgets.dart';

import 'app/kassensturz_app.dart';
import 'core/networking/mobile_api_client.dart';
import 'core/networking/mobile_connection_controller.dart';
import 'core/networking/mobile_session_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // The app keeps no financial records on the device: accounts, budgets and
  // transactions come from the paired Kassensturz server only. Files written
  // by versions before 0.2.0 are left untouched and are not read.
  runApp(
    KassensturzApp(
      mobileConnectionController: MobileConnectionController(
        apiClient: MobileApiClient(sessionStore: SecureMobileSessionStore()),
      ),
    ),
  );
}
