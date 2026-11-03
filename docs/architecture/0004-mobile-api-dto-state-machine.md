# Mobile API: DTOs, Zustandsmodell und Testmatrix

- Status: Teilweise umgesetzt – interne DTO-Mapper vorhanden; HTTP-Endpunkte und Freigabe fehlen weiterhin
- Geltungsbereich: API v1 und lokale Geräteverwaltung
- Voraussetzung: ADR 0002 (Sicherheitsanforderungen) und ADR 0003 (API-Vertrag)

Dieses Dokument präzisiert die Schnittstelle. Es beschreibt **noch keine implementierten Endpunkte**. Bis die unten genannten Tests bestehen, bleiben Pairing und Mobile-API deaktiviert.

## 1. Grundregeln

- Die API ist für genau eine lokale Kassensturz-Installation und einen Haushalt ausgelegt.
- Mobile-Clients erhalten keine direkten Datenbankzugriffe und keine vollständigen SQLite-Zeilen.
- Jede Antwort ist ein versioniertes DTO. Interne Datenbankspalten dürfen umbenannt werden, ohne den Clientvertrag zu brechen.
- Geldbeträge werden als ganzzahlige Minor Units (z. B. Cent) und mit Währungscode ausgegeben, niemals als binäre Fließkommazahl.
- Zeitstempel sind ISO-8601 mit Zeitzonenoffset; Datumsfelder ohne Uhrzeit bleiben `YYYY-MM-DD`.
- Listen sind paginiert und haben serverseitige Obergrenzen.
- Keine Tokens, Pairing-Codes, PINs, TANs, vollständigen IBANs oder ungefilterten Providerfehler in Logs oder Fehlerantworten.

## 2. Pairing

### Administration: Pairing erzeugen

`POST /api/mobile/pairings`

Nur aus der authentifizierten Home-Assistant-Ingress-Administration erreichbar. Die Anfrage benötigt keinen frei wählbaren Ablaufzeitpunkt.

Antwort (Beispiel):

```json
{
  "pairing_secret": "<one-time-secret>",
  "expires_at": "2026-11-03T12:05:00+01:00"
}
```

Der geheime Wert wird einmalig in der Administrationsoberfläche angezeigt und darf nicht in URL, Browser-Verlauf, Telemetrie oder Logs gelangen. Ein QR-Code darf nur den Server-Endpunkt und das Secret im HTTPS-Request transportieren; das Secret darf nicht Bestandteil einer URL sein.

### Mobile: Pairing einlösen

`POST /api/v1/pair`

Anfrage:

```json
{
  "pairing_secret": "<one-time-secret>",
  "device_name": "iPhone"
}
```

Erfolgsantwort:

```json
{
  "device": {
    "id": "opaque-device-id",
    "name": "iPhone"
  },
  "access_token": "<opaque-access-token>",
  "access_expires_in": 600,
  "refresh_token": "<opaque-refresh-token>",
  "refresh_expires_in": 2592000,
  "token_type": "Bearer"
}
```

Der Server akzeptiert das Secret nur, wenn es existiert, nicht abgelaufen und noch nicht verbraucht ist. Verbrauch des Secrets und Anlegen des Geräts sowie der ersten Token müssen in **einer SQLite-Transaktion** erfolgen. Zwei parallele Einlösungen desselben Secrets dürfen nicht zwei Geräte erzeugen.

Das Pairing-Secret und beide Token sind kryptografisch zufällige, nicht erratbare opaque Werte. Es gibt keine JWT-Payload, die der Client selbst auswerten oder verändern könnte. Der Server speichert ausschließlich Hashwerte. Für Secrets mit mindestens 256 Bit Entropie ist ein schneller kryptografischer Hash wie SHA-256 zur Datenbankprüfung geeignet; diese Werte sind keine menschlichen Passwörter.

## 3. Token- und Geräteablauf

### Access Token

- Gültigkeit: zunächst 10 Minuten.
- Wird ausschließlich im HTTP-Header `Authorization: Bearer …` übertragen.
- Darf niemals in URL, Query-Parametern, App-Logs oder Crash-Berichten auftauchen.
- Serverprüfung: Hash finden, Ablauf prüfen, Widerruf prüfen, Gerät muss aktiv sein.

### Refresh Token

- Gültigkeit: zunächst 30 Tage.
- Jede erfolgreiche Erneuerung ersetzt das bisherige Token.
- Das alte Token wird atomar als verbraucht markiert und auf den Nachfolger verknüpft.
- Wird ein bereits rotiertes Token erneut vorgelegt, ist das ein möglicher Replay- bzw. Diebstahlhinweis: alle Token des betroffenen Geräts werden widerrufen.
- Die Antwort der Erneuerung enthält ein neues Access- und Refresh-Token-Paar. Ein zweiter gleichzeitiger Refresh mit demselben alten Token darf nicht parallel zwei gültige Tokenketten erzeugen.

`POST /api/v1/auth/refresh`

Anfrage:

```json
{
  "refresh_token": "<opaque-refresh-token>"
}
```

Die Antwort hat dasselbe Tokenformat wie beim Pairing, jedoch ohne ein neues Geräteobjekt.

### Logout und Widerruf

`POST /api/v1/auth/logout`

- Benötigt ein gültiges Access-Token.
- Widerruft alle Token des aktuellen Geräts und beendet die Sitzung.
- Ist danach nicht mehr für authentifizierte Routen verwendbar.

`DELETE /api/mobile/devices/{id}`

- Nur durch die lokale HA-Administration.
- Widerruft das Gerät und sämtliche zugehörigen Token.
- Ein Widerruf muss ab dem nächsten Request greifen, auch wenn ein Access-Token noch nicht abgelaufen ist.

## 4. Mobile Endpunkte und Datenverträge

| Methode | Pfad | Zweck | Antwort |
|---|---|---|---|
| GET | `/api/v1/me` | Geräteidentität und Serverstatus | `device`, `server`, `capabilities` |
| GET | `/api/v1/overview` | Dashboard-Kennzahlen | `as_of`, `currency`, `accounts`, `forecast`, `budgets`, `alerts` |
| GET | `/api/v1/transactions` | Buchungsliste | `items`, `total`, `limit`, `offset` |
| POST | `/api/v1/auth/refresh` | Tokenrotation | neues Tokenpaar |
| POST | `/api/v1/auth/logout` | Gerät abmelden | `{"ok": true}` |

### Transaktionen

Query-Parameter:

- `limit`: Standard 50, Minimum 1, Maximum 100.
- `offset`: Standard 0, Minimum 0.
- `month`: optional, Format `YYYY-MM`.
- `account_id`: optional positive Ganzzahl.
- `category_id`: optional positive Ganzzahl.

Jeder Eintrag enthält nur die für die Oberfläche benötigten Felder: stabile Transaktions-ID, Buchungsdatum, Betrag in Cent, Währung, Zahlungspartner, gekürzter Verwendungszweck, Konto-Kurzname und Kategorie. Vollständige IBANs und interne Import-Hashes werden nicht ausgegeben.

### Fehlerformat

Einheitliches Format:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Anmeldung erforderlich."
  }
}
```

- `400`: syntaktisch ungültige Eingabe.
- `401`: fehlende, ungültige, abgelaufene oder widerrufene Zugangsdaten; keine Detailauskunft, die Tokenzustände verrät.
- `403`: gültige Identität ohne erforderliche Berechtigung.
- `404`: Ressource nicht vorhanden oder für dieses Gerät nicht zugänglich.
- `409`: Konflikt wie ein bereits verbrauchtes Pairing-Secret, sofern kein vertraulicher Status offengelegt wird.
- `429`: Rate-Limit erreicht; mit angemessenem `Retry-After`.
- `5xx`: generische Meldung und serverseitige Korrelations-ID; keine Stacktraces oder Bankanbieter-Rohantworten.

## 5. Persistenzanforderungen und Abgleich mit dem aktuellen Schema

Die Tabellen `mobile_pairings`, `mobile_devices` und `mobile_tokens` sind im SQLite-Schema vorbereitet. Sie enthalten derzeit:

| Tabelle | Relevante Felder | Zweck |
|---|---|---|
| `mobile_pairings` | `secret_hash`, `created_at`, `expires_at`, `consumed_at` | einmalige Pairing-Einlösung |
| `mobile_devices` | `id`, `name`, `created_at`, `last_used_at`, `revoked_at` | Geräteidentität und Gerätewiderruf |
| `mobile_tokens` | `token_hash`, `device_id`, `token_type`, `created_at`, `expires_at`, `revoked_at`, `replaced_by_hash` | Access-/Refresh-Token und Refresh-Replay-Erkennung |

Die internen Funktionen in `kassensturz/app/kassensturz/mobile_read.py` bilden bereits die Übersicht und Buchungsliste auf explizite, getestete Allowlist-DTOs ab. Sie registrieren keine HTTP-Routen. Vor produktiver Verwendung müssen Service und Tests folgende Regeln zwingend einhalten:

- `secret_hash` und `token_hash` enthalten ausschließlich typgebundene Hashes der 256-Bit-Zufallswerte, nie die Rohwerte.
- Zeitstempel werden einheitlich in UTC gespeichert, damit Ablaufvergleiche nicht von lokalen Zeitzonen oder unterschiedlichen ISO-Offsets abhängen.
- Ein Pairing-Datensatz ist genau einmal verbrauchbar. Das Setzen von `consumed_at` muss mit Geräte- und Tokenanlage in derselben Transaktion liegen.
- Ein Refresh-Datensatz wird bei Rotation mit `revoked_at` und `replaced_by_hash` markiert. Das erneute Vorlegen eines solchen Vorgängers widerruft das gesamte Gerät und alle seine Tokens.
- Ein Logout und ein administrativer Widerruf setzen `mobile_devices.revoked_at` und widerrufen alle Token desselben Geräts atomar.
- Der Gerätewiderruf muss bei jeder Access-Token-Prüfung zusätzlich zur Tokenzeile kontrolliert werden.
- Aktive Pairing-Datensätze und abgelaufene Token müssen regelmäßig bereinigt werden. Die Bereinigung darf aktive oder gerade rotierte Token nicht entfernen.
- Pairing-Rate-Limits benötigen einen eigenen, vertrauenswürdigen Schlüssel auf Basis der tatsächlichen Netzwerk-Gegenstelle. Vom Client gelieferte Forwarding-Header sind dafür ohne freigegebene Proxy-Allowlist unzulässig.

Ein separater Session-Family-Identifier ist für das aktuelle Modell nicht zwingend: Pro Gerät wird eine Tokenkette geführt und ein Reuse widerruft das gesamte Gerät. Sollte künftig eine App mehrere unabhängige Sitzungen pro Gerät unterstützen, muss das Datenmodell vor dieser Erweiterung um eine eigene Sitzungsidentität ergänzt werden.

### Atomare Pairing-Einlösung

Die Serviceimplementierung muss die Einlösung als Schreibtransaktion (SQLite `BEGIN IMMEDIATE`) ausführen:

1. Hash des eingereichten Pairing-Secrets bilden.
2. Datensatz anhand des Hashs laden.
3. Ablaufzeit und `consumed_at IS NULL` prüfen.
4. `consumed_at` nur mit einer bedingten Aktualisierung setzen und genau eine geänderte Zeile verlangen.
5. Geräteidentität und Hashes für Access- und Refresh-Token anlegen.
6. Alles gemeinsam committen; bei jedem Fehler vollständig rollbacken.

### Atomare Tokenrotation

Die Refresh-Verarbeitung muss ebenfalls mit `BEGIN IMMEDIATE` serialisiert werden:

1. Refresh-Token-Hash laden und Gerät identifizieren.
2. Gerät, Ablaufzeit und Widerrufsstatus prüfen.
3. Ist `replaced_by_hash` bereits gesetzt, liegt ein Replay-Verdacht vor: Gerät und alle zugehörigen Token widerrufen und keinen Nachfolger ausgeben.
4. Ist das Token gültig, neuen Access- und Refresh-Zufallswert erzeugen, nur deren Hashes speichern, den Vorgänger widerrufen und seinen `replaced_by_hash` setzen.
5. Vorgänger und Nachfolger gemeinsam committen.

Die mobile App muss Refresh-Aufrufe als Single-Flight behandeln. Ein legitimer doppelter Refresh-Request wird aus Sicherheitssicht wie eine Wiederverwendung eines bereits rotierten Tokens behandelt und führt zum Gerätewiderruf.

Datenbankmigrationen müssen rückwärtsverträglich sein und auf einer Kopie einer bestehenden Installation getestet werden. Bestehende Finanzdaten dürfen durch die Einführung der Geräteverwaltung weder umgeschrieben noch gelöscht werden.

## 6. Verbindliche Testmatrix

| Bereich | Test | Erwartetes Ergebnis |
|---|---|---|
| Pairing | Unbekanntes Secret | 401/409, kein Gerät |
| Pairing | Abgelaufenes Secret | abgewiesen |
| Pairing | Doppelte Einlösung | genau ein Gerät wird angelegt |
| Pairing | Zwei parallele Einlösungen | höchstens eine erfolgreich |
| Pairing | Secret in Logs | nicht vorhanden |
| Access | Anfrage ohne Token | 401, keine Finanzdaten |
| Access | Ungültiges/abgelaufenes Token | 401 |
| Access | Token eines widerrufenen Geräts | 401 sofort |
| Refresh | Gültiger Refresh | altes Token ungültig, genau ein neues Paar |
| Refresh | Wiederverwendung alten Refresh-Tokens | Gerät vollständig widerrufen |
| Refresh | Zwei gleichzeitige Refresh-Anfragen | maximal eine Rotation; erkannter Replay-Vorgänger widerruft das Gerät |
| Refresh | Single-Flight im Mobile-Client | parallele API-Aufrufe werden clientseitig zu einem Refresh zusammengeführt |
| Refresh | Vorgänger nach Rotation erneut vorgelegt | Gerät und alle Token widerrufen, kein Nachfolger |
| Logout | erneute Verwendung nach Logout | 401 |
| Geräte | Widerruf über HA-Administration | alle Token des Geräts ungültig |
| Daten | Transaktionsliste | Pagination und Feld-Allowlist eingehalten |
| Daten | API-Fehler | keine IBAN, PIN, TAN, Tokens oder Provider-Rohdaten |
| Transport | HTTP ohne TLS außerhalb Loopback | abgewiesen |
| Limits | übergroßes Limit / häufiges Pairing | validiert bzw. 429 |
| Regression | HA-Oberfläche und bestehende Endpunkte | bisherige Funktion bleibt erhalten |

### Implementierte DTO-Allowlists (Stand 03.11.2026)

Die internen Read-Services liefern derzeit folgende Felder:

- Übersicht: `as_of`, `currency`, `accounts`, `forecast`, `month`, `budgets`, `alerts`.
- Konto: ID, Anzeigename, Typ, Saldo in Cent, Kennzeichen für bekannten Saldo, Saldo-Datum und Buchungsanzahl.
- Prognose: freie Mittel, Tagesbetrag, Zeitraum, Fixkosten, erwartete variable Ausgaben, Puffer, Tiefpunkt und kommende Zahlungen.
- Budget: Kategorie-ID, Anzeigename, Limit, bisherige Ausgaben, Restbetrag und Status.
- Buchungen: ID, Buchungs-/Wertstellungsdatum, Betrag in Cent, Währung, Zahlungspartner, gekürzter Verwendungszweck, Kontoname und Kategorie.
- Buchungspagination: `total`, `limit`, `offset`; Standardlimit 50, Höchstlimit 100.

Vollständige IBANs, Gegenkonten-IBANs, Banking-Referenzen, Import-Hashes, Quellinformationen, Vertrags-Keys und rohe Datenbankzeilen werden nicht ausgegeben. Die Mapper sind durch `tests/test_mobile_read.py` gegen versehentliche Feldweitergabe abgesichert. Es existiert weiterhin kein HTTP-Endpunkt, der diese DTOs ausliefert.

## 7. Freigabeentscheidung

Eine Mobile-API-Freigabe erfolgt erst nach:

1. Implementierung des Zustandsautomaten und der atomaren Datenbankoperationen;
2. vollständiger Testmatrix im CI;
3. verifizierter HTTPS-Konfiguration einschließlich Proxy-Vertrauensgrenze;
4. Prüfung der Logs auf Geheimnislecks;
5. erfolgreichem Test von Backup, Wiederherstellung und Gerätewiderruf.

Bis dahin dürfen die Tabellen vorbereitet sein, aber kein Netzwerk-Listener für Mobile-Clients aktiviert werden.
