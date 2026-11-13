import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../networking/mobile_api_client.dart';

/// Version of this build. Release builds get it from the release tag
/// (`--dart-define=KASSENSTURZ_VERSION=0.3.8`); other builds have none and
/// never look for updates.
const appVersion = String.fromEnvironment('KASSENSTURZ_VERSION');

/// The repository also holds add-on releases (`v0.3.6`), so the app looks
/// through the recent releases instead of asking for the latest one.
final _releasesUri = Uri.parse(
  'https://api.github.com/repos/uekala/kassensturz/releases?per_page=15',
);

const _tagPrefix = 'mobile-v';

class UpdateInfo {
  const UpdateInfo({
    required this.version,
    required this.downloadUrl,
    required this.pageUrl,
  });

  final String version;

  /// Direct link to the APK, or the release page when the release has none.
  final String downloadUrl;
  final String pageUrl;
}

/// Remembers whether the user wants update checks.
abstract interface class UpdatePreference {
  Future<bool> get enabled;

  Future<void> setEnabled(bool value);
}

class SecureUpdatePreference implements UpdatePreference {
  const SecureUpdatePreference([this._storage = const FlutterSecureStorage()]);

  static const _key = 'update_check';

  final FlutterSecureStorage _storage;

  @override
  Future<bool> get enabled async => (await _storage.read(key: _key)) != 'off';

  @override
  Future<void> setEnabled(bool value) =>
      _storage.write(key: _key, value: value ? 'on' : 'off');
}

class InMemoryUpdatePreference implements UpdatePreference {
  InMemoryUpdatePreference([this._enabled = true]);

  bool _enabled;

  @override
  Future<bool> get enabled async => _enabled;

  @override
  Future<void> setEnabled(bool value) async => _enabled = value;
}

/// Parses "0.3.7" into numbers; null for anything else.
List<int>? parseVersion(String value) {
  final match = RegExp(r'^(\d+)\.(\d+)\.(\d+)$').firstMatch(value.trim());
  if (match == null) return null;
  return [for (var i = 1; i <= 3; i++) int.parse(match.group(i)!)];
}

/// True when [candidate] is a higher version than [current].
bool isNewerVersion(String candidate, String current) {
  final a = parseVersion(candidate);
  final b = parseVersion(current);
  if (a == null || b == null) return false;
  for (var i = 0; i < 3; i++) {
    if (a[i] != b[i]) return a[i] > b[i];
  }
  return false;
}

/// Asks GitHub once per app start whether a newer app release exists. Only
/// the public release list is fetched, without credentials; nothing about
/// the user, the server or the finances leaves the phone.
class UpdateChecker {
  UpdateChecker({
    MobileTransport? transport,
    UpdatePreference preference = const SecureUpdatePreference(),
    String? currentVersion,
    bool? isAndroid,
  }) : _transport = transport,
       _preference = preference,
       currentVersion = currentVersion ?? appVersion,
       _isAndroid = isAndroid ?? Platform.isAndroid;

  MobileTransport? _transport;
  final UpdatePreference _preference;
  final String currentVersion;
  final bool _isAndroid;

  /// Only release builds on Android can update from an APK.
  bool get supported => _isAndroid && parseVersion(currentVersion) != null;

  Future<bool> get enabled => _preference.enabled;

  Future<void> setEnabled(bool value) => _preference.setEnabled(value);

  /// Returns the newest newer release, or null when there is none, the check
  /// is switched off or not supported, or GitHub cannot be reached.
  Future<UpdateInfo?> check() async {
    if (!supported) return null;
    try {
      if (!await enabled) return null;
      final transport = _transport ??= IoMobileTransport(
        timeout: const Duration(seconds: 10),
      );
      final response = await transport.send(
        method: 'GET',
        uri: _releasesUri,
        headers: const {
          'Accept': 'application/vnd.github+json',
          'User-Agent': 'Kassensturz-App',
        },
      );
      if (response.statusCode != 200) return null;
      return updateFromReleases(jsonDecode(response.body), currentVersion);
    } on Object {
      return null;
    }
  }
}

/// Picks the newest app release out of GitHub's release list.
UpdateInfo? updateFromReleases(dynamic releases, String currentVersion) {
  if (releases is! List) return null;
  UpdateInfo? best;
  for (final release in releases) {
    if (release is! Map) continue;
    final tag = release['tag_name'];
    final page = release['html_url'];
    if (tag is! String || page is! String || !tag.startsWith(_tagPrefix)) {
      continue;
    }
    if (release['draft'] == true || release['prerelease'] == true) continue;
    final version = tag.substring(_tagPrefix.length);
    if (!isNewerVersion(version, best?.version ?? currentVersion)) continue;
    String? apk;
    final assets = release['assets'];
    if (assets is List) {
      for (final asset in assets) {
        final url = asset is Map ? asset['browser_download_url'] : null;
        final name = asset is Map ? asset['name'] : null;
        if (name is String &&
            url is String &&
            RegExp(r'^kassensturz-[0-9.]+\.apk$').hasMatch(name) &&
            url.startsWith('https://github.com/uekala/kassensturz/')) {
          apk = url;
          break;
        }
      }
    }
    // A release without its APK is still being built; skip it for now.
    if (apk == null) continue;
    best = UpdateInfo(version: version, downloadUrl: apk, pageUrl: page);
  }
  return best;
}
