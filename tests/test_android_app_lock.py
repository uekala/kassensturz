"""Android-Vorbereitung für die App-Sperre."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "mobile" / "app" / "tool"
_spec = importlib.util.spec_from_file_location("app_lock_tool", TOOL / "configure-android-app-lock.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

ACTIVITY = """package de.uekala.kassensturz.kassensturz_mobile

import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity()
"""
MANIFEST = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application android:label="kassensturz_mobile">
    </application>
</manifest>
"""
STYLES = """<resources>
    <style name="LaunchTheme" parent="@android:style/Theme.Light.NoTitleBar">
    </style>
    <style name="NormalTheme" parent="@android:style/Theme.Light.NoTitleBar">
    </style>
</resources>
"""


def _project(tmp_path: Path) -> Path:
    main = tmp_path / "main"
    (main / "kotlin" / "de").mkdir(parents=True)
    (main / "kotlin" / "de" / "MainActivity.kt").write_text(ACTIVITY, encoding="utf-8")
    (main / "AndroidManifest.xml").write_text(MANIFEST, encoding="utf-8")
    for name in ("values", "values-night"):
        (main / "res" / name).mkdir(parents=True)
        (main / "res" / name / "styles.xml").write_text(STYLES, encoding="utf-8")
    return main


def test_prepares_activity_permission_and_themes(tmp_path):
    main = _project(tmp_path)
    script = TOOL / "configure-android-app-lock.py"
    for _ in range(2):  # zweimal: das Skript darf nichts doppelt eintragen
        assert subprocess.run([sys.executable, str(script), str(main)], check=False).returncode == 0
    activity = (main / "kotlin" / "de" / "MainActivity.kt").read_text(encoding="utf-8")
    assert activity.count("FlutterFragmentActivity") == 2 and "FlutterActivity\n" not in activity
    manifest = (main / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert manifest.count("android.permission.USE_BIOMETRIC") == 1
    for name in ("values", "values-night"):
        styles = (main / "res" / name / "styles.xml").read_text(encoding="utf-8")
        assert styles.count('parent="Theme.AppCompat.DayNight.NoActionBar"') == 2


def test_unknown_template_fails_loudly(tmp_path):
    with pytest.raises(tool.AppLockSetupError):
        tool.fragment_activity("class MainActivity : Activity()")
    with pytest.raises(tool.AppLockSetupError):
        tool.appcompat_themes("<resources></resources>")
    main = _project(tmp_path)
    (main / "kotlin" / "de" / "MainActivity.kt").unlink()
    script = TOOL / "configure-android-app-lock.py"
    assert subprocess.run([sys.executable, str(script), str(main)], check=False).returncode == 1


def test_bootstrap_runs_the_preparation():
    bootstrap = (TOOL / "bootstrap-platforms.sh").read_text(encoding="utf-8")
    assert bootstrap.index("flutter create") < bootstrap.index("configure-android-app-lock.py")
