import 'package:flutter/widgets.dart';

import 'app/kassensturz_app.dart';
import 'core/data/account_repository.dart';
import 'core/data/budget_repository.dart';
import 'core/networking/mobile_api_client.dart';
import 'core/networking/mobile_connection_controller.dart';
import 'core/networking/mobile_session_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    KassensturzApp(
      budgetRepository: LocalBudgetRepository(
        store: SharedPreferencesStringKeyValueStore(),
      ),
      accountRepository: EncryptedAccountRepository(
        keyStore: SecureAccountKeyStore(store: FlutterSecureValueStore()),
      ),
      mobileConnectionController: MobileConnectionController(
        apiClient: MobileApiClient(sessionStore: SecureMobileSessionStore()),
      ),
    ),
  );
}
