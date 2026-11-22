# Architekturentscheidung 0001: Lokale Produktarchitektur

- Status: als Produktrichtung angenommen; Einzelheiten der Umsetzung stehen unter Vorbehalt einer Sicherheitsprüfung.
- Datum: 2026-11-03
- Umfang: Handy-Apps von Kassensturz, Home-Assistant-Integration und eigenständige Installation.

## Entscheidung

Kassensturz wird ein **lokales Produkt für einen einzelnen Haushalt**. Jeder Kunde betreibt eine Kassensturz-Installation auf seinem eigenen Home-Assistant-Host, NAS, Mini-PC oder Heimserver. Diese Installation ist der maßgebliche Datenbestand für Konten, Umsätze, Verträge, Kategorien, Regeln und Prognosen.

Die Apps für iOS und Android sind Clients dieser Installation. Sie verbinden sich direkt über das lokale Netz des Kunden oder ein Fernzugriffsnetz, das der Kunde selbst kontrolliert (zum Beispiel ein VPN). Kassensturz betreibt keinen zentralen Dienst, der Bankzugangsdaten oder Umsatzhistorien von Kunden speichert.

„Lokal“ heißt nicht „ganz ohne Dritte“: Der direkte FinTS-Zugang geht an die Bank, während eine Open-Banking-Verbindung über Enable Banking zwangsläufig diesen Anbieter einbezieht. Die App muss den Datenfluss klar erklären und darf Anbieter-Integrationen nur zu Bedingungen anbieten, die die vorgesehene Nutzung durch Kunden erlauben.

## Aufbau des Produkts

```text
                         Vom Kunden kontrolliertes Netz
  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                  │
  │  iOS-App ──────────────┐                                         │
  │                        ├── HTTPS / VPN ──> Kassensturz-Instanz   │
  │  Android-App ──────────┘                       │                  │
  │                                               ├── lokales SQLite │
  │  HA-Oberfläche / Sensoren ── HA-Adapter ──────┤                  │
  │                                               ├── FinTS ──> Bank │
  │                                               └── Open Banking   │
  │                                                      │           │
  └──────────────────────────────────────────────────────┼───────────┘
                                                         v
                                                  Enable Banking
```

Im Standardaufbau gibt es keine von Kassensturz betriebene Umsatzdatenbank, keinen Identitätsdienst, kein Synchronisations-Relay und keinen Telemetrie-Endpunkt.

## Bausteine und Zuständigkeiten

### 1. Fachkern (Python)

Die bestehende Finanzlogik bleibt in Python und wird nach und nach von Installation und Oberfläche getrennt.

Zuständigkeiten:
- Modell für Konten und Umsätze;
- Vereinheitlichung von Importen und Erkennung von Dubletten;
- Kategorisierung und eigene Regeln;
- Erkennung von Verträgen und Abos;
- Budgets, Auswertungen und Prognosen;
- Anbieter-Adapter für FinTS und unterstützte Open-Banking-APIs.

Der Kern darf nicht von Anfrageobjekten von Home Assistant, Ingress-Headern, Oberflächencode der Handy-App oder einem zentralen Kassensturz-Dienst abhängen.

### 2. Lokaler Anwendungsdienst (FastAPI)

Der lokale Dienst besitzt die Datenbank eines Haushalts und stellt eine versionierte API bereit.

Ziel-Präfix der API: `/api/v1`.

Zuständigkeiten:
- Anfragen prüfen und die Berechtigung von Geräten durchsetzen;
- stabile DTOs unabhängig vom Tabellenaufbau in SQLite liefern;
- Importe und Bankabgleich ausführen;
- Zustand und verfügbare Funktionen melden;
- Fachereignisse an verbundene Clients senden, wo es sinnvoll ist.

Die bisherigen Routen `/api/*` bleiben die Kompatibilitätsschnittstelle der Weboberfläche in Home Assistant, bis eine eigene Umstellung geplant ist. Sie dürfen im Zuge der ersten Grundlage für die Handy-App nicht kaputtgehen.

### 3. Speicherung

- SQLite für die lokale Installation eines einzelnen Haushalts beibehalten.
- Die Datenbank als maßgeblichen Bestand behandeln.
- Ausdrückliche Schema-Migrationen einführen, bevor das Datenmodell wächst.
- Tabellen für Geräte und Sitzungen getrennt von den Finanztabellen anlegen.
- Eine Cloud-Datenbank nie zur Voraussetzung für den Betrieb der App machen.
- Verschlüsselte Sicherung und Wiederherstellung festlegen, bevor mit verschlüsselten Sicherungen geworben wird.

SQLite passt für die heutige Installation eines einzelnen Haushalts. Ein Wechsel zu PostgreSQL ist keine Voraussetzung für das lokale Produkt.

### 4. Home-Assistant-Adapter

Home Assistant bleibt eine unterstützte Installationsart und Integration, aber keine Abhängigkeit des Fachkerns.

- Das heutige Erlebnis als Add-on bzw. im App Store erhalten.
- Ingress als Standardweg für den Browserzugriff beibehalten.
- Die API nicht auf einem neuen Host-Port freigeben, bevor Geräteanmeldung, Berechtigungen, Ratenbegrenzung und Transportsicherheit umgesetzt sind.
- Sensoren und Benachrichtigungen von Home Assistant hinter einem Adapter halten.
- Eine dokumentierte eigenständige Docker-Installation mit demselben Python-Kern und API-Dienst anbieten.

### 5. Handy-Apps

Ein gemeinsamer Flutter-Code für iOS und Android.

Erste Aufgaben der App:
- Server-Adresse von Hand eingeben und Kopplung per QR-Code;
- Geräte registrieren und widerrufen;
- Dashboard, Konten, Umsätze, Budgets und Verträge;
- Gerätezugangsdaten sicher im Keychain bzw. Android Keystore speichern;
- optional ein verschlüsselter lokaler Cache nach Prüfung des Bedrohungsmodells;
- Wiederverbinden und klare Anzeige von Offline-Zustand und veralteten Daten.

Die Handy-App ist in der ersten Version keine Bankanbindung. Bankzugangsdaten und Banksitzungen bleiben in der Kassensturz-Instanz des Kunden.

## Verbindungs- und Vertrauensmodell

1. Der Nutzer startet die Kopplung in der vertrauenswürdigen lokalen Kassensturz-Oberfläche oder mit einem lokalen Verwaltungsbefehl.
2. Die Instanz erzeugt ein einmaliges, kurzlebiges Kopplungsgeheimnis und zeigt es als QR-Code an.
3. Die Handy-App tauscht das Kopplungsgeheimnis gegen gerätespezifische Zugangsdaten.
4. Der Server speichert von Refresh-Zugangsdaten nur einen Prüfwert bzw. Hash, notiert Gerätename und letzte Nutzung und erlaubt den sofortigen Widerruf eines Geräts.
5. Für API-Aufrufe dienen kurzlebige Zugangsdaten; Refresh-Zugangsdaten rotieren, und die vorherigen werden ungültig.
6. Kopplung und API-Verkehr verlangen HTTPS. Für Fernzugriff wird ein vom Kunden verwaltetes VPN empfohlen. Den Dienst nicht direkt ins öffentliche Internet stellen.
7. Kein gemeinsames globales App-Passwort und kein fest eingebautes Hersteller-Geheimnis.

Genaues Tokenformat, kryptografische Verfahren, Schlüsselrotation und Grenzen für Kopplungsversuche müssen in einer Sicherheits-Architekturentscheidung festgelegt und vor der Umsetzung geprüft werden.

## Netzwerkarten

Unterstützte Arten, nach Vorrang:

1. **Lokales LAN:** Der Nutzer gibt die HTTPS-Adresse seiner eigenen Instanz ein oder scannt sie.
2. **Vom Kunden verwaltetes VPN:** Dieselbe lokale API wird über WireGuard, Tailscale oder ein gleichwertiges privates Netz erreicht.
3. **Installation in Home Assistant:** Ein eigens angemeldeter API-Listener darf erst nach den oben beschriebenen Sicherheitsarbeiten eingeschaltet werden. Ingress bleibt der Standardweg für die Browser-Oberfläche.

Kein Kassensturz-Relay, kein Hersteller-VPN, kein Reverse-Proxy und kein gehosteter Suchdienst gehört zum ersten Aufbau.

## Grenzen der Monetarisierung

Die erste Version soll keinen zentralen Berechtigungsserver brauchen. Das Premium-Konzept muss eigens geklärt werden, weil die Kaufprüfung bei Apple und Google unterschiedliche Vertrauens- und Plattformanforderungen hat.

Vor der Umsetzung der Monetarisierung:
- entscheiden, ob Premium über die Abrechnung der Stores, einen erlaubten externen Kaufweg oder eine signierte Lizenz gekauft wird;
- dokumentieren, wie eine Berechtigung geprüft wird, ohne Store-Geheimnisse in die Handy-App zu legen;
- entscheiden, wie ein Kauf nach Neuinstallation oder Gerätewechsel wiederhergestellt wird;
- sicherstellen, dass sich der lokale Server weiter ohne Bindung an ein Konto sichern und wiederherstellen lässt.

Keinen clientseitigen Wahrheitswert als einzige Premium-Berechtigung umsetzen.

## Keine Ziele der ersten Version der Handy-App

- Cloud-Konto für mehrere Haushalte oder Familien;
- zentrale, von Kassensturz betriebene Bankaggregation;
- Teilen von Finanzdaten zwischen Nutzern;
- vom Hersteller verwalteter Fernzugriff;
- standardmäßige KI-Verarbeitung von Banktransaktionen;
- sofortiger Ersatz der bestehenden Oberfläche in Home Assistant.

## Abnahmekriterien der Architektur

- Die Finanzlogik des Kerns lässt sich ohne Home Assistant importieren und testen.
- Dieselbe Instanz kann die Oberfläche in Home Assistant und angemeldete Handy-Apps bedienen.
- Keine Anfrage einer Handy-App kann vor Kopplung und Berechtigung Daten lesen.
- Jedes Gerät lässt sich einzeln widerrufen.
- Kein API-Listener wird standardmäßig freigegeben, bevor die Sicherheitsmaßnahmen existieren.
- Das Produkt bleibt ohne Kassensturz-Cloudkonto nutzbar.
- Datenflüsse und Lizenzbeschränkungen der Bankanbieter sind dokumentiert.
