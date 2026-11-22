# Sicherheitsanforderungen an die API für die Handy-App

- Status: vorgeschlagene Grundlage für die Umsetzung
- Zugehörige Entscheidung: [Lokale Architektur](0001-local-first-architecture.md)

Dieses Dokument legt Anforderungen fest; es behauptet nicht, dass die heutige API sie schon erfüllt.

## Heutiger Stand

Die heutige FastAPI-Anwendung ist für Ingress von Home Assistant gebaut. Bestehende Routen außerhalb der Handy-App bleiben auf die Ingress-Gegenstelle und IPv4/IPv6-Loopback beschränkt. Die Namensräume der Handy-App verlangen HTTPS und akzeptieren entweder ein ausdrücklich eingerichtetes Client-CIDR oder eine Anfrage von einer ausdrücklich vertrauenswürdigen Reverse-Proxy-Gegenstelle. Beide Einstellungen lassen sich über die Optionen des Home-Assistant-Add-ons oder Umgebungsvariablen im eigenständigen Betrieb setzen und sind standardmäßig leer. Der Entwicklungsmodus umgeht diese Grenze nicht. Die API-Routen setzen Anmeldung per Bearer-Token um, Fernzugriff ist aber standardmäßig nicht eingeschaltet: Die Portfreigabe der HA-App bleibt aus.

FinTS-PINs und der private Schlüssel für Enable Banking liegen jetzt in einem mit AES-256-GCM verschlüsselten Umschlag. Die Installation nutzt standardmäßig eine lokale 256-Bit-Schlüsseldatei mit Modus 0600 oder einen von außen gesetzten `KASSENSTURZ_MASTER_KEY` aus 64 Hex-Zeichen. Sicherungen von Home Assistant lassen die verschlüsselte Geheimnisdatei und ihren lokalen Schlüssel aus. Umstellung, Wiederherstellung und Grenzen gegenüber Angreifern stehen unter [Lokale Verschlüsselung von Geheimnissen](0005-local-secret-encryption.md).

SQLite speichert Finanzumsätze und Verbindungsdaten. Das Datenverzeichnis ist auf Modus 0700 beschränkt, die Hauptdatenbank auf Modus 0600. Diese Maßnahmen verschlüsseln weder die SQLite-Datenbank noch ihre Sicherungen. Die lokale Schlüsseldatei schützt eine isolierte Kopie der verschlüsselten Geheimnisdatei, aber nicht gegen einen Angreifer, der das gesamte laufende Datenverzeichnis lesen kann.

### Stand der Umsetzung für die Handy-App (2026-11-03)

| Baustein | Stand |
|---|---|
| Tabellen für Kopplung, Geräte und Tokens | Schema vorhanden; Migration und Einschränkungen getestet |
| Dienst für Kopplung und Token-Lebenszyklus | Als interner Dienst ohne HTTP umgesetzt; Unit-Tests decken einmalige Kopplung, Ablauf, Rotation, Erkennung von Wiederverwendung und Widerruf ab |
| DTO-Abbildung für Übersicht und Umsätze | Als interne Lesedienste umgesetzt, mit Feld-Allowlists, Seitenaufteilung und Tests der Abfrageprüfung |
| Routen zum Erzeugen und Einlösen von Kopplungsgeheimnissen | Umgesetzt: Erzeugen durch den Admin über vertrauenswürdiges Ingress/Loopback; einmaliges Einlösen über eine HTTPS-Route für die Handy-App |
| HTTP-Routen für Access- und Refresh-Tokens | Umgesetzt: Rotation beim Erneuern, Bearer-Anmeldung und Abmelden eines Geräts |
| Routen zum Auflisten und Widerrufen von Geräten | Umgesetzt: nur für Admins über Ingress von Home Assistant (`panel_admin: true`) oder vertrauenswürdiges lokales Loopback; Ingress verlangt zusätzlich den vom Supervisor gesetzten Header `X-Remote-User-Id` |
| Angemeldete DTO-Routen für die Handy-App | Umgesetzt: `/api/v1/me`, `/overview` und seitenweise `/transactions` mit Feld-Allowlists |
| HTTPS-Pflicht für die Namensräume der Handy-App | Middleware-Sperre für `/api/v1/*` und `/api/mobile/*`; akzeptiert direktes TLS oder `X-Forwarded-Proto: https` von ausdrücklich erlaubten Proxys. Der Listener bleibt auf Ingress/Loopback beschränkt, plus die optionale ausdrückliche Allowlist für das Netz der Handy-App. |
| Netz-Allowlist für Handy-Clients | `KASSENSTURZ_MOBILE_CLIENT_NETWORKS` nimmt ausdrückliche IP-/CIDR-Bereiche; standardmäßig leer. Die bestehende Browser-Oberfläche bleibt auf Ingress/Loopback beschränkt. Eine ausdrücklich vertrauenswürdige Reverse-Proxy-Gegenstelle wird unabhängig von dieser Liste zugelassen; beide Maßnahmen bleiben Opt-in. |
| Ratenbegrenzung im Netz | Begrenzter, prozesslokaler Sliding-Window-Limiter für Kopplung, Erneuern, Abmelden, Lesen und Geräteverwaltung. Grenzen je Gerät beim Erneuern und ein gemeinsamer Speicher für mehrere Worker fehlen noch. |
| Flutter-Client | Oberflächen-Prototyp; keine Serververbindung und keine Anmeldung der Handy-App |
| Lokaler Kontospeicher | Verschlüsselte SQLite3MultipleCiphers-Datenbank; zufälliger 256-Bit-Schlüssel im sicheren Speicher der Plattform; nur von Hand erfasste Kontodaten |
| Lokale Budget-Einstellungen | SharedPreferences; nur Kategorie-IDs und Grenzen, nicht verschlüsselt |
| Import von Bankkonten / Abgleich von Umsätzen | Nicht umgesetzt |

Die FastAPI-Anwendung registriert die versionierten Endpunkte der Handy-App jetzt neben den bestehenden Routen für Home Assistant. Die alten Routen `/api/*` bleiben getrennt und dürfen nicht als per Gerät angemeldete Routen gelten. Finanzrouten der Handy-App verlangen ein Bearer-Token. Anlegen, Auflisten und Widerrufen von Geräten ist auf die Ingress-Gegenstelle mit einer vom Supervisor angemeldeten Nutzer-ID oder vertrauenswürdiges lokales Loopback beschränkt. Das Add-on setzt ausdrücklich `panel_admin: true`, sodass Nicht-Admins den Ingress-Bereich nicht öffnen können; ein fehlender `X-Remote-User-Id` wird an der API abgelehnt. Die eigenständige Installation bindet weiter nur an Loopback und stellt die API der Handy-App deshalb nicht für Clients im LAN oder VPN bereit.

Der ausführliche Vertrag in [0003](0003-mobile-api-contract.md) und die Zustandsmaschine in [0004](0004-mobile-api-dto-state-machine.md) bleiben die API-Spezifikationen. Die Dienste `mobile_auth.py` und `mobile_read.py` werden über `mobile_api.py` bereitgestellt. Die Einstellungen `trusted_proxies` und `mobile_client_networks` der HA-App speisen jetzt dieselbe im Zweifel sperrende Regel wie die Umgebungsvariablen im eigenständigen Betrieb. Weitergeleitete Transport- und Client-Header zählen nur, wenn die direkte Gegenstelle in `KASSENSTURZ_TRUSTED_PROXIES` steht. Einem vertrauenswürdigen Loopback-Proxy wird der Zugriff auf die lokalen Routen der Geräteverwaltung ausdrücklich verweigert, damit ein Tailscale-Proxy keine lokalen Ingress-Rechte erbt. Die optionale Portfreigabe des Containers für 8099/TCP ist deklariert, aber standardmäßig aus (`null`). Netz-Ratenbegrenzungen greifen vor der Weiterleitung an die Route, der Limiter im Speicher gilt aber nur für einen Prozess. Grenzen je Gerät, ein dauerhafter gemeinsamer Zustand der Ratenbegrenzung, der Verbindungs- und Kopplungsablauf in Flutter und die Härtung für Releases fehlen noch.


## Nötige Maßnahmen, bevor ein breiterer Netzzugriff für die Handy-App eingeschaltet wird

### Transport
- HTTPS ist Pflicht für Kopplung und angemeldeten API-Zugriff.
- Fernzugriff soll über ein vom Kunden verwaltetes VPN laufen.
- Öffentliche Portweiterleitung nicht als Standardeinrichtung einschalten.
- Zugangsdaten und Tokens im Klartext ablehnen.
- Ungültige TLS-Zertifikate nicht stillschweigend akzeptieren.

### Kopplung und Geräteidentität
- Kopplungsgeheimnisse erzeugt die lokale Instanz; sie gelten einmal und kurz.
- Kopplungsversuche sind in der Rate begrenzt.
- Kopplungsgeheimnisse brauchen genug Entropie; ein kurzer, für Menschen lesbarer Code muss durch strenge Versuchsgrenzen geschützt sein.
- Jede erfolgreiche Kopplung legt einen eigenen Gerätedatensatz an.
- Gerätedatensätze enthalten Erstellungszeit, letzte Nutzung und eine vom Nutzer änderbare Gerätebezeichnung.
- Nutzer können ein Gerät widerrufen, ohne andere Geräte zu berühren.
- Gerätezugangsdaten werden nie in Anwendungslogs geschrieben.

### Sitzungszugangsdaten
- Kurzlebige Access-Zugangsdaten nutzen.
- Rotierende, widerrufbare Refresh-Zugangsdaten nutzen.
- Auf dem Server einen Prüfwert bzw. Hash der Refresh-Zugangsdaten speichern, nicht die Zugangsdaten selbst.
- Die Wiederverwendung rotierter Refresh-Zugangsdaten erkennen und die betroffene Sitzungsfamilie widerrufen.
- Bearer-Zugangsdaten nicht in URLs, Query-Strings oder Analysedaten ablegen.
- Ein sicheres Verfahren zum Zurücksetzen und Wiederherstellen von Zugangsdaten festlegen.

### Berechtigungen der API
- Endpunkte der Handy-App unter `/api/v1` versionieren.
- Für alle Finanzdaten und ändernden Endpunkte eine Berechtigung verlangen.
- Unbekannte Routen und Methoden standardmäßig ablehnen.
- Prüfung der Anfrage-DTOs, Grenzen für Seitenaufteilung und Uploads durchsetzen.
- Netz-Ratenbegrenzungen vor der Weiterleitung und Grenzen je Gerät für Kopplung, Anmeldung/Erneuern und aufwendige Vorgänge anwenden. Die heutige Umsetzung im Speicher gilt nur für einen Prozess; vor einer Installation mit mehreren Workern einen gemeinsamen transaktionalen Zustand nutzen.
- CORS ausgeschaltet lassen, außer ein dokumentierter Browser-Client braucht bestimmte Origins.
- Für native Clients Bearer-Header gegenüber Cookie-Sitzungen bevorzugen.

### Datenschutz
- Nie PINs, TANs, private Schlüssel, Access-Tokens, vollständige IBANs oder Verwendungszwecke loggen.
- Fehler der Anbieter schwärzen, bevor sie an die Handy-App gehen.
- Verschlüsselung im Ruhezustand für Bankzugangsdaten und jeden lokalen Cache der App festlegen.
- Dateirechte für Datenbank, Geheimnisse und Sicherungen beschränken.
- Vom Nutzer gesteuerten Datenexport und vollständiges Löschen anbieten.
- Erklären, dass die Verschlüsselung einer SQLite-Datenbank nicht automatisch Sicherungen, WAL-Dateien, temporäre Dateien oder Caches der Handy-App verschlüsselt.

### Härtung der Importe
- Größengrenzen für gepackte und entpackte Archive durchsetzen.
- Anzahl der ZIP-Einträge, Größe je Eintrag, entpackte Gesamtgröße und Laufzeit des Parsers begrenzen.
- Pfad-Traversal und Symlinks in Archiven ablehnen.
- Größengrenzen für Uploads und Importe aus überwachten Ordnern einheitlich anwenden.
- Dateinamen, MIME-Typen und CSV-Inhalten nicht vertrauen.

### Ablauf bei Open Banking
- Exakte Übereinstimmung des OAuth-State verlangen; keinen Callback-Code ohne passenden State annehmen.
- Offene Autorisierungszustände ablaufen lassen und genau einmal verbrauchen.
- Weiterleitungs-URL und Kontokennungen des Anbieters als nicht vertrauenswürdige Eingabe behandeln.
- Dokumentieren, wer den regulierten Kontoinformationsdienst erbringt.
- Die gewerblichen bzw. Nutzungsbedingungen des Anbieters prüfen, bevor Nutzer außerhalb des eigenen Haushalts freigeschaltet werden.

## Sicherheitstests
- Unit-Tests für Ablauf und Einmaligkeit der Kopplung, Token-Rotation, Widerruf, Auswertung vertrauenswürdiger Proxys, HTTPS-Pflicht und Grenzen der Ratenbegrenzung.
- API-Tests, die belegen, dass nicht angemeldete Clients keine Finanzdaten lesen oder ändern können.
- Tests der Mandantentrennung, falls je mehrere Nutzer unterstützt werden.
- Importtests für übergroße und fehlerhafte ZIP-Archive und XML-Dateien.
- Statische Analyse und Prüfung der Abhängigkeiten auf Schwachstellen in der CI.
- Eine Release-Checkliste für Wiederherstellung von Sicherungen, Rotation von Geheimnissen und Widerruf von Geräten.

## Freigabe-Schranke

Fernzugriff bleibt aus, bis die Maßnahmen der Abschnitte „Transport“, „Kopplung und Geräteidentität“, „Sitzungszugangsdaten“ und „Berechtigungen der API“ umgesetzt und durch Tests abgedeckt sind. Vor dem Einschalten der optionalen Host-Portfreigabe in HA die genaue Reverse-Proxy-Gegenstelle der Tailscale Services in der Add-on-Option `trusted_proxies` eintragen, `X-Forwarded-Proto: https` und das Verhalten der Quelladresse auf dem Green prüfen, eine nur für das Tailnet geltende Freigabe für den Tailscale Service einrichten und belegen, dass direkte Anfragen aus dem LAN abgelehnt werden. Keine Portweiterleitung im Router und keinen Tailscale Funnel einrichten.
