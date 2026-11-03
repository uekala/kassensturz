import 'package:flutter/widgets.dart';

import 'app/kassensturz_app.dart';
import 'core/data/budget_repository.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    KassensturzApp(
      budgetRepository: LocalBudgetRepository(
        store: SharedPreferencesStringKeyValueStore(),
      ),
    ),
  );
}
