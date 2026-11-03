# Kassensturz Mobile – Flutter

Kassensturz Mobile wird als **eine gemeinsame Flutter-App für iOS und Android** entwickelt.

## Produktprinzip

Die App verbindet sich direkt mit der eigenen Kassensturz-Installation des Nutzers. Unterstützte Verbindungswege sind das lokale Netzwerk und ein vom Nutzer verwaltetes VPN. Kassensturz betreibt dafür keinen zentralen Daten- oder Sync-Dienst.

Bankzugänge, FinTS-PINs, TANs und Open-Banking-Private-Keys verbleiben auf dem Server. Die Mobile-App erhält ausschließlich die für die Oberfläche benötigten Daten über eine authentifizierte, versionierte API.

## Status am 03.11.2026

- [x] Entscheidung für Flutter und gemeinsame iOS-/Android-Codebasis dokumentiert.
- [x] Zielstruktur und Sicherheitsgrenzen beschrieben.
- [ ] Flutter-Projekt-Bootstrap mit festgelegter Toolchain.
- [ ] Verbindungsassistent und Server-Healthcheck.
- [ ] QR-Pairing gegen die implementierte Mobile-API.
- [ ] Sichere Credential-Ablage über iOS-Keychain und Android Keystore.
- [ ] Dashboard, Konten und Buchungsliste.
- [ ] Budgets und Verträge.
- [ ] Integrationstests auf iOS und Android.
- [ ] Signierte Store-Builds und Veröffentlichung.

**Wichtig:** Das ist eine Architektur- und Umsetzungsplanung, noch kein ausführbares Flutter-Projekt. Die Mobile-API ist serverseitig ebenfalls noch nicht implementiert. Die bestehende Home-Assistant-Oberfläche bleibt bis zur späteren Migration unverändert.

## Geplante Projektstruktur

```text
mobile/
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

## Sicherheitsregeln

1. Keine Bank-PINs, TANs, Bank-Sessions oder privaten Bank-Schlüssel in der App.
2. Keine Access-/Refresh-Tokens in Klartextdateien, Logs, Analytics oder Crash-Reports.
3. Geräte-Credentials ausschließlich in iOS-Keychain bzw. Android Keystore-geschützter Ablage.
4. Keine Deaktivierung der TLS-Zertifikatsprüfung.
5. Pairing-Secrets werden niemals in URLs oder Query-Parametern übertragen.
6. Ein widerrufenes oder ungültiges Gerät löscht seine lokale Sitzung und muss neu gekoppelt werden.
7. Kein Finanzdaten-Offlinecache in Version 1, bis Verschlüsselung und Löschverhalten separat entschieden sind.

## Nächste Schritte

1. Mobile-API auf dem Server implementieren und alle Sicherheits-Release-Gates bestehen lassen.
2. Flutter-Projekt für beide Plattformen bootstrappen und CI für Formatierung, Analyse und Tests ergänzen.
3. UI-Grundgerüst und API-Mocks parallel entwickeln.
4. Nach Freigabe des Backends echtes Pairing und den ersten vollständigen Leseablauf integrieren.
5. Auf iOS und Android testen und die Store-Veröffentlichungen gemeinsam vorbereiten.

Weitere Architekturdetails: [ADR 0006 – Flutter Mobile Client](architecture/0006-flutter-mobile-client.md).
