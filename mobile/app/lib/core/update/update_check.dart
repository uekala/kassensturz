import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../networking/mobile_api_client.dart';

/// Version dieses Builds. Release-Builds bekommen sie aus dem Release-Tag
/// (`--dart-define=KASSENSTURZ_VERSION=0.3.8`); andere Builds haben keine und
/// suchen nie nach Updates.
const appVersion = String.fromEnvironment('KASSENSTURZ_VERSION');

/// Das Repository enthält auch Add-on-Releases (`v0.3.6`), deshalb durchsucht die App
/// die jüngsten Releases, statt nach dem neuesten zu fragen.
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

  /// Direkter Link zur APK oder die Release-Seite, wenn das Release keine hat.
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

/// True, wenn [candidate] eine höhere Version als [current] ist.
bool isNewerVersion(String candidate, String current) {
  final a = parseVersion(candidate);
  final b = parseVersion(current);
  if (a == null || b == null) return false;
  for (var i = 0; i < 3; i++) {
    if (a[i] != b[i]) return a[i] > b[i];
  }
  return false;
}

/// Fragt GitHub einmal pro App-Start, ob es ein neueres App-Release gibt. Abgerufen
/// wird nur die öffentliche Release-Liste, ohne Zugangsdaten; nichts über den Nutzer,
/// den Server oder die Finanzen verlässt das Handy.
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

  /// Nur Release-Builds auf Android können sich aus einer APK aktualisieren.
  bool get supported => _isAndroid && parseVersion(currentVersion) != null;

  Future<bool> get enabled => _preference.enabled;

  Future<void> setEnabled(bool value) => _preference.setEnabled(value);

  /// Gibt das neueste neuere Release zurück, oder null, wenn es keines gibt, die Prüfung
  /// abgeschaltet oder nicht unterstützt ist oder GitHub nicht erreichbar ist.
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

/// Sucht das neueste App-Release aus GitHubs Release-Liste heraus.
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
    // Ein Release ohne seine APK wird noch gebaut; vorerst überspringen.
    if (apk == null) continue;
    best = UpdateInfo(version: version, downloadUrl: apk, pageUrl: page);
  }
  return best;
}
