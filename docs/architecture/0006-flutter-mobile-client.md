# Architecture Decision Record 0006: Gemeinsame Flutter-App für iOS und Android

- Status: Accepted
- Datum: 2026-11-03
- Geltungsbereich: Native Mobile-Clients von Kassensturz

## Entscheidung

Kassensturz wird für iOS und Android gleichzeitig mit **einer gemeinsamen Flutter-Codebasis** entwickelt. Die fachliche Oberfläche, API-Integration, Datenmodelle und Zustandslogik werden plattformübergreifend geteilt. Plattformabhängige Funktionen wie sichere Credential-Ablage, QR-Kamera, App-Lifecycle und Netzwerkdetails werden hinter kleinen Adaptern gekapselt.

Es werden keine zwei unabhängig entwickelten nativen Apps gepflegt. Die Zielplattformen sind iOS und Android; Desktop- und Web-Builds sind nicht Teil des ersten Mobile-Releases.

## Produkt- und Vertrauensmodell

- Die App verbindet sich direkt mit genau einer vom Nutzer verwalteten Kassensturz-Installation.
- Verbindung über das lokale Netzwerk oder ein vom Nutzer verwaltetes VPN.
- Kein Kassensturz-Relay, kein zentraler Sync-Dienst und kein Cloudkonto als Voraussetzung.
- Die App speichert keine Bank-PINs, TANs, FinTS-Sitzungen oder Open-Banking-Private-Keys. Diese bleiben ausschließlich auf dem Kassensturz-Server.
- Der Nutzer muss die Serveridentität über HTTPS mit gültiger Zertifikatsprüfung bestätigen können. Es gibt keinen allgemeinen „Zertifikatsfehler ignorieren“-Modus.
- Serverseitig gelieferte Finanzdaten werden erst nach Umsetzung der Mobile-API-Authentifizierung eingebunden.
- Der aktuelle Flutter-Prototyp unterstützt zusätzlich manuell erfasste Konten. Diese bleiben ausschließlich auf dem Gerät und werden in einer verschlüsselten SQLite3MultipleCiphers-Datenbank gespeichert; der zufällige Datenbankschlüssel liegt separat im Plattform-Secure-Storage.
- Der Prototyp enthält weiterhin synthetische Buchungen und Budgetauswertungen. Die Budgetlimits liegen derzeit in leichtgewichtigem, nicht verschlüsseltem App-Speicher und dürfen keine Credentials oder vollständigen Bankdaten enthalten.

## Verantwortungsgrenzen

### Gemeinsamer Flutter-Code

- Serveradresse und Verbindungsstatus verwalten.
- QR-Pairing starten und Antworten validieren.
- API-v1-DTOs und Fehlerobjekte abbilden.
- Access-/Refresh-Token-Lifecycle und Single-Flight-Refresh umsetzen.
- Dashboard, Konten, Buchungen, Budgets und Verträge darstellen.
- Netzwerkfehler, abgelaufene Sitzung und nicht erreichbaren Server klar unterscheiden.
- Keine Finanzdaten oder Credentials in Logs, Analytics oder Crash-Reports schreiben.

### Plattformadapter

- **iOS:** Geräte-Credentials in der iOS-Keychain.
- **Android:** Geräte-Credentials in Android Keystore-geschützter sicherer Ablage.
- Kamera- und QR-Code-Zugriff mit expliziter Berechtigung und manueller Fallback-Eingabe.
- App-Lifecycle und Hintergrundverhalten ohne unautorisierte Token- oder Finanzdatenübertragung.

Der gemeinsame Code darf keine Klartextdatei als Ersatz für die sichere Plattformablage verwenden. Ist Secure Storage nicht verfügbar, muss die App die Sitzung sicher ablehnen und eine verständliche Meldung anzeigen.

## Zielstruktur des Repositories

Die Flutter-App erhält ein eigenes Verzeichnis `mobile/`, getrennt von der bestehenden Python-/Home-Assistant-Anwendung.

Vorgesehene Struktur:

```text
mobile/
  README.md
  app/
    pubspec.yaml
    lib/
      main.dart
      app/
      core/
        config/
        networking/
        security/
        routing/
        design/
      features/
        server_connection/
        pairing/
        dashboard/
        accounts/
        transactions/
        budgets/
        contracts/
    test/
    integration_test/
    android/
    ios/
```

Die Struktur ist ein Zielbild. Sie wird erst mit dem Flutter-Bootstrap erzeugt; es wird kein unvollständiges oder nicht ausführbares Flutter-Projekt als fertiger Client ausgegeben.

## API- und Sitzungsregeln

- Die App kommuniziert ausschließlich mit den versionierten Endpunkten unter `/api/v1`.
- Bestehende Home-Assistant-Routen unter `/api/*` werden nicht als mobile API missbraucht.
- Pairing-Code und Serveradresse werden als QR-Daten gelesen; das Secret wird niemals in eine URL oder Query-Zeichenfolge übernommen. Es wird aus dem App-Speicher direkt im HTTPS-Request-Body übertragen.
- Der Access-Token wird nur im Authorization-Header gesendet.
- Refresh-Aufrufe werden pro App-Instanz als Single-Flight ausgeführt.
- Nach Gerätewiderruf oder fehlgeschlagenem Refresh wird der lokale Credential-Satz gelöscht und eine erneute Kopplung verlangt.
- TLS-Zertifikatsprüfung darf nicht deaktiviert werden. Remote-Zugriff erfolgt über ein Kunden-VPN.

## UI-Umfang für die erste Version

1. Einrichtungsassistent mit Serveradresse und Verbindungstest.
2. QR-Pairing und verständliche Fehlerbehandlung.
3. Dashboard mit Konten, Saldoübersicht und Prognose.
4. Kontenübersicht.
5. Buchungsliste mit Pagination und Filtern.
6. Budgets und Kategorien.
7. Verträge und wiederkehrende Zahlungen.
8. Geräte-/Sitzungsstatus sowie Logout.

Die erste Version ist primär lesend. Änderungen an Buchungen, Regeln, Konten oder Bankverbindungen werden nicht in den mobilen Client aufgenommen, bevor die entsprechenden API-Berechtigungen und Sicherheitsprüfungen separat spezifiziert sind.

## Test- und Release-Strategie

- Gemeinsame Unit-Tests für DTOs, API-Client, Sitzungszustände und Refresh-Single-Flight.
- API-Vertragstests gegen einen lokalen Mock-Server und später gegen die echte FastAPI-Implementierung.
- Integrationstests auf iOS und Android für Pairing, sichere Ablage, Logout und Widerruf.
- Plattformtests auf unterstützten iOS- und Android-Versionen vor jedem Release.
- CI muss Flutter-Formatierung, statische Analyse und Unit-Tests ausführen; Release-Builds werden erst mit signierten, geschützten Build-Secrets eingerichtet.
- iOS- und Android-App-Store-Veröffentlichungen werden gemeinsam geplant, können aber nach erfolgreichem Plattform-Review zeitlich getrennt erfolgen.

## Offene technische Entscheidungen

Vor dem Flutter-Bootstrap werden Paketversionen und Mindestversionen der Zielplattformen anhand der aktuellen Flutter-/Dart-Toolchain festgelegt. Die Entscheidung für State-Management, Routing, HTTP-Client und QR-Bibliothek wird im Bootstrap dokumentiert und durch Tests abgesichert. Keine Plattform wird gegenüber der anderen als spätere Option behandelt.

## Abhängigkeiten und Freigabereihenfolge

Die Flutter-Arbeit kann mit UI-Prototypen, Navigation, DTO-Mocks und Tests vorbereitet werden. Ein produktiver Login und Finanzdatenzugriff sind jedoch vom sicheren Mobile-Backend abhängig.

Die App darf erst als nutzbar freigegeben werden, wenn Pairing, Tokenrotation, Gerätewiderruf, HTTPS-Proxy-Vertrauensgrenze und Authentifizierung jeder Finanzdatenroute implementiert und im CI getestet sind.


## Aktueller Prototypstand (2026-11-03)

- Die gemeinsame Flutter-App enthält ein lokales Kontenmodell mit EUR-Salden als ganzzahlige Centbeträge.
- Konten können manuell angelegt, geändert und gelöscht werden. Es gibt keine Bankabfrage und keinen Server-Sync.
- Vollständige IBANs und Kartennummern sind nicht Bestandteil des Kontenmodells; optional werden nur die letzten vier Ziffern gehalten.
- Für Konten verwendet der produktive App-Einstieg eine SQLite3MultipleCiphers-Datenbank im SQLCipher-Kompatibilitätsmodus. Ein zufälliger 256-Bit-Schlüssel wird getrennt über die Plattformablage für Geheimnisse gespeichert.
- Automatisierte Tests prüfen Datenbank-Persistenz, verschlüsselte Dateikennung und Zurückweisung eines falschen Schlüssels.
- Dies ist ein Implementierungsprototyp, keine abgeschlossene Sicherheitsfreigabe. Backup-/Restore-Verhalten, Datenbank-WAL-Dateien, Gerätesicherung, Schlüsselverlust und Gerätekompromittierung müssen vor einem produktiven Release gesondert bewertet werden.
