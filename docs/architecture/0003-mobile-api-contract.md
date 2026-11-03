# Mobile API contract (v1)

- Status: Teilweise implementiert – Pairing-/Session-/Read-Routen vorhanden; zusätzliche Sicherheits- und Clientintegration bleibt offen
- Ziel: iOS- und Android-Clients einer einzelnen lokalen Kassensturz-Installation
- Sicherheit: siehe [Mobile API security requirements](0002-mobile-api-security.md) und [DTOs / Zustandsmodell](0004-mobile-api-dto-state-machine.md)

Dieser Vertrag beschreibt die Schnittstelle und ihre Sicherheitssemantik. Die Pairing-, Session-, Geräteverwaltungs- und Read-Endpunkte sind im Backend registriert; Flutter-Clientintegration, zusätzliche Sicherheitsprüfungen und eine breitere Netzfreigabe bleiben offen.

## 1. Deployment und Transport

- Mobile API und Pairing sind standardmäßig deaktiviert.
- Jeder Pairing- und authentifizierte Request benötigt HTTPS mit gültiger Zertifikatsprüfung auf dem Client.
- Für Remote-Zugriff wird ausschließlich ein vom Kunden verwaltetes VPN empfohlen.
- Keine direkte öffentliche Portfreigabe und kein Kassensturz-Relay.
- Der Client verbindet sich direkt mit der eigenen Serverinstallation.
- Klartext-HTTP darf außerhalb von Loopback nicht verwendet werden.
- Bei TLS-Terminierung vor FastAPI darf ein weitergeleiteter HTTPS-Header nur dann vertraut werden, wenn die direkte Gegenstelle zu einer explizit konfigurierten Proxy-Allowlist gehört. Von beliebigen Clients gelieferte `Forwarded`- oder `X-Forwarded-Proto`-Header sind nicht vertrauenswürdig.
- Proxy-Header für Host, Scheme oder Client-IP werden niemals allein aufgrund ihrer Anwesenheit akzeptiert.

Die Aktivierung eines Listeners ist eine separate Deployment-Entscheidung und darf nicht automatisch aus dem Vorhandensein der Datenbanktabellen folgen.

## 2. Kryptografische Formate

Alle Pairing-Secrets sowie Access- und Refresh-Tokens sind opaque Zufallswerte:

- Erzeugung mit einem kryptografisch sicheren Zufallszahlengenerator.
- 32 Zufallsbytes (256 Bit Entropie), URL-sicher Base64-kodiert ohne Padding.
- Keine JWTs und keine selbst interpretierbaren Claims im Client.
- Übertragung ausschließlich in HTTPS-Request-Bodies oder im Authorization-Header.
- Niemals in URL, Query-String, QR-URL, Logs, Analytics, Crash-Berichten oder Fehlermeldungen.

Zur Speicherung wird ausschließlich der Hash abgelegt. Für die hochentropischen Zufallswerte ist SHA-256 mit typbezogenem Domain-Prefix vorgesehen, zum Beispiel `SHA256("kassensturz:refresh:v1:" || token)`. Der Typ-Prefix verhindert eine Wiederverwendung desselben Hash-Namensraums für Pairing-, Access- und Refresh-Werte. Der rohe Zufallswert darf nach Ausgabe nicht erneut aus der Datenbank rekonstruierbar sein.

Alle Zeitstempel werden als UTC in einem einheitlichen ISO-8601-Format gespeichert und verglichen. Fristen werden ausschließlich serverseitig bestimmt.

## 3. Pairing-Lifecycle

1. Der Eigentümer öffnet die lokale Kassensturz-Administration.
2. Der Server erzeugt ein kryptografisch zufälliges Pairing-Secret.
3. Das Secret ist fünf Minuten gültig und wird genau einmal angezeigt, vorzugsweise als QR-Code.
4. Die mobile App sendet das Secret zusammen mit einem Gerätenamen im HTTPS-Body.
5. Der Server verbraucht das Secret atomar, erstellt eine Geräte-ID und stellt ein erstes Access-/Refresh-Token-Paar aus.
6. Das Gerät erscheint in der lokalen Geräteverwaltung und kann einzeln widerrufen werden.

### Verwaltung

| Methode | Pfad | Zweck | Autorisierung |
|---|---|---|---|
| POST | `/api/mobile/pairings` | Pairing-Secret erzeugen | lokale HA-Administration |
| GET | `/api/mobile/devices` | gekoppelte Geräte auflisten | lokale HA-Administration |
| DELETE | `/api/mobile/devices/{id}` | Gerät widerrufen | lokale HA-Administration |

Die Ausgabe des Pairing-Secrets erfolgt nur in der Antwort des Erzeugungsrequests. Ein erneuter GET darf das Secret nicht anzeigen. Alte und verbrauchte Pairing-Datensätze werden zeitnah bereinigt.

### Einlösung

`POST /api/v1/pair`

Anfrage:

```json
{
  "pairing_secret": "<one-time-secret>",
  "device_name": "iPhone"
}
```

Antwort:

```json
{
  "device": {"id": "<opaque-device-id>", "name": "iPhone"},
  "access_token": "<opaque-access-token>",
  "access_expires_in": 600,
  "refresh_token": "<opaque-refresh-token>",
  "refresh_expires_in": 2592000,
  "token_type": "Bearer"
}
```

Die Prüfung des Hashes, das Prüfen der Ablaufzeit, das Setzen von `consumed_at`, das Erstellen des Geräts und das Anlegen beider Token-Datensätze erfolgen in einer SQLite-Transaktion mit Schreibsperre (`BEGIN IMMEDIATE`). Zwei parallele Einlösungen desselben Secrets dürfen höchstens eine erfolgreiche Geräteanlage bewirken.

## 4. Sitzungs- und Token-Lifecycle

### Access Token

- Lebensdauer: 10 Minuten.
- Verwendung ausschließlich über `Authorization: Bearer <token>`.
- Speicherung auf dem Server nur als typgebundener SHA-256-Hash.
- Bei jedem Request: Hash-Lookup, Tokenablauf, Widerruf und aktiven Gerätestatus prüfen.
- Ein Gerätewiderruf muss sofort greifen und darf nicht auf das Access-Token-Ablaufdatum warten.

### Refresh Token

- Lebensdauer: 30 Tage.
- Jede erfolgreiche Erneuerung erzeugt ein neues Access- und Refresh-Token-Paar.
- Das alte Refresh-Token wird atomar als verbraucht markiert und über `replaced_by_hash` mit dem Nachfolger verbunden.
- Das alte Token ist ab diesem Commit dauerhaft ungültig.
- Wird ein bereits rotiertes Token erneut verwendet, gilt dies als möglicher Replay-/Diebstahlhinweis. Das gesamte Gerät und alle seine Token werden widerrufen.
- Ein Refresh-Request muss innerhalb einer Datenbanktransaktion serialisiert werden. Parallele Refresh-Aufrufe derselben App-Instanz müssen vom Client zusätzlich als Single-Flight ausgeführt werden.
- Ein gestohlener oder ungültiger Token führt nie dazu, dass eine neue Tokenkette ausgegeben wird.

`POST /api/v1/auth/refresh`

Anfrage:

```json
{"refresh_token": "<opaque-refresh-token>"}
```

Erfolgsantwort enthält die gleichen Tokenfelder wie die Pairing-Antwort, jedoch ohne ein neues Geräteobjekt.

### Logout

`POST /api/v1/auth/logout`

- Erfordert ein gültiges Access-Token.
- Widerruft alle Access- und Refresh-Token des aktuellen Geräts.
- Die Antwort enthält keine Credential-Informationen.
- Nach erfolgreichem Logout liefert jede geschützte Route für dieses Gerät `401`.

### Administration und Widerruf

`DELETE /api/mobile/devices/{id}`

- Nur durch die lokale Administration.
- Setzt den Gerätestatus auf widerrufen und widerruft alle zugehörigen Token in derselben Transaktion.
- Bereits ausgestellte Access-Token müssen beim nächsten Request abgewiesen werden.
- Ein erneutes Pairing erzeugt eine neue Geräteidentität; widerrufene Identitäten werden nicht reaktiviert.

## 5. Endpunkte und Datenverträge

| Methode | Pfad | Zweck | Autorisierung |
|---|---|---|---|
| POST | `/api/v1/pair` | Pairing einlösen | gültiges One-Time-Secret |
| POST | `/api/v1/auth/refresh` | Tokens rotieren | gültiges Refresh-Token |
| POST | `/api/v1/auth/logout` | Gerät abmelden | gültiges Access-Token |
| GET | `/api/v1/me` | Geräteidentität und Serverstatus | gültiges Access-Token |
| GET | `/api/v1/overview` | Finanzübersicht | gültiges Access-Token |
| GET | `/api/v1/transactions` | paginierte Buchungen | gültiges Access-Token |

- Alle mobilen Finanzantworten sind explizite DTOs, niemals rohe SQLite-Zeilen.
- Geldbeträge sind ganzzahlige Minor Units plus ISO-Währungscode.
- Listen sind paginiert; Standardlimit 50, Mindestlimit 1, Höchstlimit 100.
- Offsets dürfen nicht negativ sein; Filterfelder werden serverseitig validiert.
- Vollständige IBANs, Bankzugangsdaten, Import-Hashes, interne Provider-IDs und rohe Providerfehler werden nicht an die App ausgeliefert.
- Unbekannte mobile Pfade und Methoden sind standardmäßig nicht freigegeben.

## 6. Fehlerformat

Einheitliches Fehlerobjekt:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Anmeldung erforderlich."
  }
}
```

| Status | Bedeutung |
|---|---|
| 400 | syntaktisch ungültige Eingabe |
| 401 | fehlende, ungültige, abgelaufene oder widerrufene Credentials |
| 403 | gültige Identität ohne erforderliche Berechtigung |
| 404 | Ressource nicht vorhanden oder für dieses Gerät nicht zugänglich |
| 409 | Pairing-Konflikt oder bereits verbrauchtes Secret, ohne vertrauliche Zustandsdetails |
| 429 | Rate-Limit überschritten; angemessener `Retry-After`-Header |
| 5xx | generische Meldung und Korrelations-ID; keine Stacktraces und keine Provider-Rohantwort |

Ungültige, abgelaufene und widerrufene Tokens dürfen nicht durch unterschiedliche Fehlermeldungen oder Response-Felder unterscheidbar gemacht werden.

## 7. Rate-Limits und Missbrauchsschutz

Aktueller Implementierungsbaseline für das Netzwerk-Limit (pro ermittelter Client-IP):

| Aktion | Limit | Zeitfenster |
|---|---:|---:|
| Pairing einlösen | 10 | 5 Minuten |
| Refresh | 30 | 1 Minute |
| Logout | 20 | 1 Minute |
| Geräte-/Status-/Übersicht-/Buchungs-Lesezugriff | 120 | 1 Minute |
| Pairing erzeugen | 5 | 15 Minuten |
| Gerät widerrufen | 10 | 5 Minuten |

Die Werte sind konservative Startwerte und müssen anhand realer Nutzung überprüft werden. Die aktuelle Implementierung ist ein begrenzter In-Memory-Sliding-Window-Limiter für einen einzelnen Prozess. Vor Mehrprozessbetrieb muss ein gemeinsamer, transaktionaler Rate-Limit-Speicher eingesetzt werden. Zusätzlich sind bei Refresh und Pairing gerätebezogene bzw. installationsbezogene Limits vorzusehen. Die Netzwerkidentität wird aus dem Socket-Peer oder – ausschließlich bei einem explizit vertrauenswürdigen Proxy – aus einer validierten `X-Forwarded-For`-Kette abgeleitet.

- Pairing-Erzeugung: begrenzte Anzahl aktiver Pairing-Secrets je Installation.
- Pairing-Einlösung: begrenzte Fehlversuche pro tatsächlicher Netzwerk-Gegenstelle und Zeitfenster.
- Refresh: begrenzte Anfragen pro Geräteidentität.
- Limits gelten serverseitig; vom Client gelieferte IP-Header dürfen den Rate-Limit-Schlüssel nicht bestimmen. Forwarding-Header werden nur akzeptiert, wenn die unmittelbare Gegenstelle in `KASSENSTURZ_TRUSTED_PROXIES` konfiguriert ist.
- Bei Überschreitung erfolgt `429` mit `Retry-After`.
- Rate-Limit-Daten dürfen keine Pairing-Secrets oder Token im Klartext enthalten.
- Fehlversuche und Sicherheitsereignisse werden protokolliert, niemals aber die Credentials selbst.

Die konkreten Schwellwerte sind vor Implementierung zu konfigurieren und im Test auf legitime Wiederholungen sowie Missbrauch zu prüfen.

## 8. Versionierung und Kompatibilität

- Alle neuen mobilen Endpunkte liegen unter `/api/v1`.
- Bestehende `/api/*`-Routen bleiben für die Home-Assistant-Oberfläche kompatibel.
- Ein API-Major-Upgrade erhält einen neuen Prefix.
- Mobile Clients müssen nicht auf interne Tabellen- oder Domain-Änderungen reagieren.
- Das Vorhandensein vorbereiteter Mobile-Datenbanktabellen aktiviert keinen Listener.

## 9. Implementierungsstand (03.11.2026)

Folgende Routen sind im Backend registriert:

| Methode | Pfad | Implementierung |
|---|---|---|
| POST | `/api/mobile/pairings` | Pairing-Secret erzeugen; nur Ingress/Loopback |
| GET | `/api/mobile/devices` | Geräte-Metadaten auflisten; nur Ingress/Loopback |
| DELETE | `/api/mobile/devices/{id}` | Gerät und alle Token widerrufen; nur Ingress/Loopback |
| POST | `/api/v1/pair` | Einmaliges Pairing einlösen, Token ausgeben |
| POST | `/api/v1/auth/refresh` | Refresh-Token rotieren |
| POST | `/api/v1/auth/logout` | Aktuelles Gerät abmelden |
| GET | `/api/v1/me` | Geräteidentität und Serverfähigkeiten |
| GET | `/api/v1/overview` | Allowlist-Dashboard-DTO |
| GET | `/api/v1/transactions` | Allowlist-Buchungs-DTO mit Pagination/Filtern |

Die Routen sind durch `tests/test_mobile_api.py` und `tests/test_network_boundary.py` abgedeckt. Die Flutter-App ruft diese Endpunkte noch nicht auf. Die Standard-Netz-Allowlist ist leer; die Standalone-Compose-Variante bleibt auf `127.0.0.1` gebunden. Die In-Memory-Rate-Limits sind nur für einen Prozess vorgesehen und müssen vor Mehrprozessbetrieb durch gemeinsamen transaktionalen Zustand ersetzt werden.

## 10. Verbindliche Freigabekriterien

Eine breitere Freigabe für LAN-/VPN-Clients bleibt deaktiviert, bis:

- Pairing-Secrets zufällig, kurzlebig, einmalig und atomar konsumiert werden;
- Token opaque, hochentropisch, gehasht, ablaufend, rotierend und widerrufbar sind;
- Refresh-Reuse das betroffene Gerät vollständig widerruft;
- alle Finanzdatenrouten Authentifizierung und DTO-Allowlisting erzwingen;
- HTTPS und die Proxy-Vertrauensgrenze technisch erzwungen sind;
- Rate-Limits und Missbrauchsschutz getestet sind;
- Replay-, Parallelitäts-, Ablauf-, Widerrufs- und Regressionstests im CI bestehen;
- Backup und Wiederherstellung die Wiederherstellung der lokalen Geräteverwaltung sicher berücksichtigen.

Die Routen sind bereits registriert, werden aber standardmäßig nicht für entfernte Client-Netze freigegeben. Die Standalone-Compose-Variante bleibt an Loopback gebunden; es gibt keinen öffentlichen Port und keinen Kassensturz-Relay.
