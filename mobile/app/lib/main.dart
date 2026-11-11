import 'package:flutter/widgets.dart';

import 'app/kassensturz_app.dart';
import 'core/networking/mobile_api_client.dart';
import 'core/networking/mobile_connection_controller.dart';
import 'core/networking/mobile_session_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // The installed app keeps no financial records on the device: accounts,
  // budgets and transactions come from the paired Kassensturz server only.
  // Files written by earlier versions are left untouched and are not read.
  runApp(
    KassensturzApp(
      serverOnly: true,
      mobileConnectionController: MobileConnectionController(
        apiClient: MobileApiClient(sessionStore: SecureMobileSessionStore()),
      ),
    ),
  );
}
