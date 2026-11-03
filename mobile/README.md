# Kassensturz Mobile – Flutter für iOS und Android

**Beschlossen:** eine gemeinsame Flutter-Codebasis für iOS und Android.

Kassensturz Mobile wird gleichzeitig für beide Plattformen entwickelt. Oberfläche, API-Client, DTOs und Sitzungslogik werden gemeinsam in Dart umgesetzt; plattformspezifische Funktionen bleiben hinter Adaptern.

Die Architekturentscheidung ist in [ADR 0006 – Flutter Mobile Client](../docs/architecture/0006-flutter-mobile-client.md) festgehalten.

Die erste Serverplattform ist der vorhandene **Home Assistant Green**. Kassensturz läuft dort als bestehende Home-Assistant-App; ein separater Server wird zunächst nicht beschafft. Die Deployment-Entscheidung und die Sicherheitsgrenzen sind in [ADR 0007 – Home Assistant Green](../docs/architecture/0007-home-assistant-green-deployment.md) festgehalten.

## Produkt- und Vertrauensmodell

- Die App verbindet sich direkt mit genau einer vom Nutzer verwalteten Kassensturz-Installation.
- Remote-Zugriff ist über einen separaten Tailscale Service `svc:kassensturz` im eigenen Tailnet vorgesehen; Tailscale Funnel wird dafür nicht verwendet.
- Das optionale Host-Port-Mapping 8099/TCP bleibt standardmäßig deaktiviert. Der Zugang wird erst nach Verifikation des Tailscale-Proxy-Peers und dessen HTTPS-Headern freigeschaltet.
- Kein Kassensturz-Cloudkonto, kein Relay und kein zentraler Transaktionsspeicher.
- Die erste App-Version ist ein Companion-Client und kein eigener Bankconnector.
- FinTS-PINs, TANs, Bank-Sessions und Open-Banking-Private-Keys bleiben auf dem Server.
- Geräte-Credentials liegen auf iOS in der Keychain und auf Android in einer Keystore-geschützten Ablage.
- HTTPS und normale Zertifikatsprüfung sind zwingend. Es gibt keinen „unsichere Zertifikate ignorieren“-Schalter.
- Kein Finanzdaten-Offlinecache in Version 1; dafür ist zuerst eine eigene Datenschutz- und Verschlüsselungsentscheidung nötig.

## Status am 03.11.2026

- [x] Flutter als gemeinsamer Client für iOS und Android beschlossen.
- [x] Zielarchitektur, Sicherheitsgrenzen und erste UI-Funktionen dokumentiert.
- [x] Flutter-Dart-Projekt mit Demo-Oberfläche und Widget-Tests angelegt.
- [x] CI für Flutter-Formatierung, statische Analyse und Widget-Tests eingerichtet.
- [x] Reproduzierbares Erzeugen von Android- und iOS-Projektdateien ergänzt.
- [ ] Verbindungsassistent und Server-Healthcheck.
- [x] Server-Endpunkte für Pairing, Refresh, Logout und lokale Geräteverwaltung.
- [x] Serverseitiger Pairing-/Token-Lifecycle mit Tests (Einmal-Secrets, Tokenrotation, Replay-Erkennung und Gerätewiderruf).
- [x] HTTPS-Sperre für reservierte Mobile-API-Pfade und Prüfung explizit vertrauenswürdiger Proxy-Header.
- [x] Netzwerk-Rate-Limits vor dem Route-Dispatch für Pairing, Refresh, Logout, Lesezugriffe und Geräteverwaltung.
- [x] Default-deny-Netzwerkgrenze; `trusted_proxies` und `mobile_client_networks` sind als HA-App-Optionen vorhanden und standardmäßig leer.
- [ ] Sichere Credential-Ablage im Flutter-Client und Tokenrotation über die API.
- [x] Demo-Oberflächen für Dashboard, Konten, Buchungen und Budgets mit klar gekennzeichneten Beispieldaten.
- [x] Manuelle lokale Kontenpflege mit verschlüsselter SQLite-Datenbank und Schlüsselablage im Betriebssystem.
- [x] Lokale Speicherung der Budgetlimits.
- [x] Allowlist-DTOs und geschützte Server-Endpunkte für Übersicht, Konten, Budgets und paginierte Buchungsliste.
- [ ] Flutter-Anbindung an echte Serverdaten; Verträge und weitere Live-Funktionen.
- [ ] Integrationstests auf iOS und Android.
- [ ] Signierte Builds und Store-Veröffentlichungen.

**Aktueller Implementierungsstand:** Das Python-Backend stellt Mobile-Endpunkte für Pairing, Tokenrotation, Logout, lokale Geräteverwaltung, Geräteidentität, Übersicht und Buchungen bereit. Finanzdaten sind per Bearer-Token geschützt; Geräteverwaltung ist Ingress/Loopback vorbehalten. HTTPS, private Client-Netz-Allowlist und Netzwerk-Rate-Limits sind in der Middleware umgesetzt. Die Flutter-App ist noch nicht mit dem Server verbunden und nutzt für Dashboard/Buchungen weiterhin Beispieldaten. Die Add-on-Optionen `trusted_proxies` und `mobile_client_networks` werden beim Start aus der HA-Konfiguration gelesen; Tailscale-Proxy-Adresse und `X-Forwarded-Proto` müssen vor einer Remote-Freigabe auf dem Green überprüft werden. Der aktuelle Rate-Limiter ist prozesslokal und setzt einen einzelnen App-Prozess voraus; gerätebezogene Limits und gemeinsamer Zustand für Mehrprozessbetrieb stehen noch aus. Die optionale Umgebungsvariable `KASSENSTURZ_MOBILE_CLIENT_NETWORKS` ist standardmäßig leer und öffnet weder einen Port noch registriert sie API-Routen. Die nativen Android-/iOS-Projektdateien werden per Bootstrap-Skript erzeugt und anschließend für einen lokalen Entwickler-Workspace eingecheckt. Die bestehenden Home-Assistant-Routen sind keine mobile Authentifizierung und dürfen nicht von der App verwendet werden.

## Geplante Projektstruktur

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

Der Dart-Quellcode und die Tests unter `mobile/app` sind bereits vorhanden. Die nativen `android/`- und `ios/`-Runner werden mit `tool/bootstrap-platforms.sh` aus dem Flutter-SDK generiert.

## Geplanter App-Umfang – erste Version

1. Serveradresse eingeben oder QR-Einrichtung starten.
2. Verbindung und Serverstatus anzeigen.
3. Pairing und Verwaltung des eigenen Geräts.
4. Dashboard und Kontenübersicht.
5. Buchungsliste mit Filtern und Pagination.
6. Budgets, Kategorien und Verträge.
7. Logout und klare Anzeige eines Gerätewiderrufs.

Die erste Version bleibt überwiegend lesend. Schreibende Funktionen werden erst ergänzt, wenn API-Berechtigungen und Sicherheitsprüfungen dafür freigegeben sind.

## Vorgesehene technische Bereiche

- `core/config`: Serveradresse und App-Konfiguration.
- `core/networking`: HTTPS-API-Client, DTOs, Fehlerbehandlung und Refresh-Single-Flight.
- `core/security`: Plattformadapter für Keychain und Android Keystore.
- `core/routing`: Navigation und geschützte App-Bereiche.
- `core/design`: gemeinsames Designsystem.
- `features/*`: fachliche Funktionen mit gemeinsamer Plattformlogik.

Die konkrete Auswahl und Versionierung von State-Management, Routing, HTTP-Client und QR-Paket erfolgt beim Bootstrap anhand der dann aktuellen Flutter-/Dart-Versionen. Das wird nicht vorab durch ungetestete Paketversionen festgeschrieben.

## API und Sicherheitsvorgaben

- Die App kommuniziert ausschließlich mit den versionierten Endpunkten unter `/api/v1`.
- Pairing-Secrets werden nie in URLs oder Query-Parametern übertragen.
- Access-Tokens kommen ausschließlich in den Authorization-Header.
- Refresh-Aufrufe laufen pro App-Instanz als Single-Flight.
- Nach Widerruf oder fehlgeschlagenem Refresh wird die lokale Sitzung gelöscht und erneutes Pairing verlangt.
- Credentials, Kontodaten und Verwendungszwecke dürfen nicht in Logs, Analytics oder Crash-Reports gelangen.

Die Spezifikation steht in:

- [Mobile API contract](../docs/architecture/0003-mobile-api-contract.md)
- [Mobile API security requirements](../docs/architecture/0002-mobile-api-security.md)
- [DTOs, Token-Lifecycle und Testmatrix](../docs/architecture/0004-mobile-api-dto-state-machine.md)

## Build- und Freigabereihenfolge

1. Mobile-API mit Pairing, Gerätewiderruf, Tokenrotation und Authentifizierung implementieren.
2. Sicherheits-Release-Gates und API-Tests bestehen lassen.
3. Flutter-Projekt für beide Plattformen bootstrappen und CI ergänzen.
4. UI-Grundgerüst und API-Mocks parallel entwickeln.
5. Den ersten echten End-to-End-Ablauf vom Pairing bis zum Dashboard integrieren.
6. Auf realen iOS- und Android-Geräten testen.
7. Signierte Builds und App-Store-/Google-Play-Veröffentlichung vorbereiten.
