# Kassensturz Handy-App

Flutter-Quellcode für iOS und Android. Beide Plattformen teilen den Dart-Code der App.

## Stand

Die App ist ein Client für genau einen Kassensturz-Server. Alle Finanzdaten liegen auf dem Server; die installierte App behält nur die Serveradresse und die Gerätezugangsdaten (im sicheren Speicher der Plattform).

Mit einem gekoppelten Server (0.3.0 oder neuer) kann die App

- Übersicht, Konten, Budgets, Umsätze und Verträge vom Server zeigen,
- manuelle Umsätze auf Konten ohne Bankanbindung anlegen, ändern und löschen,
- Kategorie und Notiz von Bankumsätzen ändern,
- die Umsatzliste nach Konto und Kategorie filtern,
- den Verbindungszustand, den letzten erfolgreichen Abgleich und eine Meldung mit dem Grund zeigen, wenn der Server nicht erreichbar ist,
- neu laden, wenn die App wieder in den Vordergrund kommt.

Ohne Verbindung zeigt die installierte App statt Beispieldaten eine Seite „Verbinden“. Mit einem älteren Server gekoppelt bleibt sie bei reinem Lesen und bittet darum, den Server zu aktualisieren.

Das Demo-Dashboard, der Kontoeditor auf dem Gerät (verschlüsseltes SQLite) und die Budgetgrenzen auf dem Gerät sind in 0.3.1 entfallen, zusammen mit den Paketen, die sie brauchten. Dateien von Versionen vor 0.2.0 bleiben auf dem Gerät und werden nicht gelesen.

## Speichern und wiederholte Anfragen

Jedes Formular „Neuer Umsatz“ erzeugt eine Anfrage-ID und schickt sie mit jedem Speicherversuch. Der Server speichert die ID, ein wiederholtes Speichern nach einer abgebrochenen Verbindung bucht also nie doppelt. Schreibende Anfragen werden nie automatisch wiederholt; lesende Anfragen einmal.

## Erneuern der Sitzung

Access-Tokens werden mit dem Refresh-Token erneuert, sobald der Server mit 401 antwortet. Es läuft immer nur eine Erneuerung zugleich. Der Server akzeptiert ein ersetztes Refresh-Token genau ein weiteres Mal innerhalb von zehn Minuten, um eine verlorene Antwort abzufangen. Der Client wiederholt eine Erneuerung deshalb einmal sofort, wenn die Verbindung nach dem Senden der Anfrage abbrach, und nicht, wenn die Verbindung nie zustande kam. Lehnt der Server die Erneuerung ab, wird die lokale Sitzung entfernt, und das Gerät muss neu gekoppelt werden.

## Voraussetzungen

- Flutter SDK 3.47.9 aus dem stable-Kanal (dieselbe Version wie in der CI)
- Android SDK für die Android-Entwicklung
- Xcode auf macOS für die iOS-Entwicklung

Der stable-Kanal von Flutter ist der empfohlene Kanal für neue Projekte und Produktiv-Releases: https://docs.flutter.dev/install/upgrade

## Lokale Einrichtung

In diesem Verzeichnis:

```bash
flutter pub get
flutter test
flutter analyze
```

Die automatischen Tests decken den API-Client (Kopplung, Erneuern, wiederholtes Erneuern, schreibende Aufrufe), den Verbindungs-Controller (Zustand, Abgleich, Speichern, Filter), Antwortmodelle, Fehlermeldungen, die nicht gekoppelte App und die verbundene App auf jedem Tab in Handygröße ab. Der Code wird mit `flutter_lints` geprüft. Die Härtung des Android-Manifests wird mit pytest getestet (`tests/test_android_manifest.py`).

Die nativen Projektdateien für Android und iOS einmal erzeugen. Das Skript trägt außerdem die Berechtigung INTERNET ins Release-Manifest ein und nimmt die App-Daten von Android-Sicherung und Geräteumzug aus:

```bash
bash tool/bootstrap-platforms.sh
```

Das Skript überschreibt keine vorhandenen Plattform-Ordner. Nach der ersten Erzeugung die erzeugten Verzeichnisse android/ und ios/ unter Versionskontrolle halten, wenn eine echte Entwicklungsumgebung vorbereitet wird.

Auf einem angeschlossenen Gerät oder Simulator starten:

```bash
flutter devices
flutter run
```

## Sicherheit und API-Anbindung

Die Flutter-App enthält HTTPS-Zustandsprüfungen, einmalige Kopplung, automatisches Erneuern, Lesen und Schreiben über den Server und einen nativen QR-Scanner für die versionierten Kopplungsdaten von Kassensturz. Der QR-Scanner nutzt die Kamera erst, wenn der Nutzer ihn öffnet; das iOS-Skript ergänzt die nötige Begründung für die Kameranutzung. Der API-Client nutzt die normale Prüfung von TLS-Zertifikaten, schaltet Weiterleitungen bei angemeldeten Anfragen ab, hält Access-Tokens im Authorization-Header und sendet Refresh-Tokens nur im Body einer HTTPS-Anfrage. Ein 401 auf ein Access-Token löst genau eine Erneuerung aus; eine abgelehnte Erneuerung entfernt die gespeicherte Sitzung. Zugangsdaten liegen im sicheren Speicher der Plattform. Keine Platzhalter-Tokens, keine Ausnahmen für Zertifikate und keine Logs mit Zugangsdaten einbauen.

Siehe [Architektur der Handy-App](../../docs/architecture/0006-flutter-mobile-client.md) und [Sicherheitsanforderungen der Handy-App](../../docs/architecture/0002-mobile-api-security.md).

## Veröffentlichen

Ein Tag `mobile-v<version>` (die Version aus `pubspec.yaml` ohne Build-Nummer, z. B. `mobile-v0.3.4`) führt die Tests aus, baut die signierte arm64-APK und hängt sie mit dem passenden Abschnitt aus `CHANGELOG.md` an ein GitHub-Release. Der Build braucht die vier Repository-Secrets `ANDROID_*`; ohne sie bricht er vor dem Bauen ab. Die Build-Nummer kommt aus der Laufnummer des Workflows, jedes Release installiert sich also über das vorige.

## Bildschirmfotos aus der CI

Der Ablauf „App-Bilder“ rendert bei jedem Pull Request jede Seite der App und legt die Bilder als Artefakt
`kassensturz-app-bilder` an den Lauf: hell, dunkel und so, wie das Handy eines Kindes sie sieht.

Die Daten dafür sind nicht von Hand gebaut. `tools/app_fixture.py` startet den Server mit den Beispieldaten und einem
kleinen Haushalt und speichert, was er der App antwortet. `tool/bilder/app_bilder.dart` spielt diese Antworten ab. Passen
Server und App nicht mehr zusammen, sieht man es in den Bildern oder der Lauf schlägt fehl.

Von Hand:

```bash
python3 tools/app_fixture.py mobile/app/tool/bilder/server.json
cd mobile/app && flutter test tool/bilder/app_bilder.dart
```

Die Bilder liegen danach unter `mobile/app/build/app-bilder`.
