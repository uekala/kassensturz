# Eigenständiger Betrieb mit Docker (Linux)

Diese Deployment-Variante betreibt Kassensturz ohne Home Assistant auf einem Linux-Server. Sie ist für den lokalen Zugriff auf dem Server vorgesehen und **nicht** für den Zugriff aus dem LAN oder über das Internet freigeschaltet.

## Sicherheitsgrenze

Die bestehende Anwendung besitzt noch keine produktive Mobile-Authentifizierung. Die aktuellen HTTP-Routen sind für Home-Assistant-Ingress entwickelt; die Middleware akzeptiert außerdem Loopback-Verbindungen. Deshalb bindet diese Compose-Datei den Prozess über Host-Networking ausschließlich an `127.0.0.1:8099`.

- Es gibt absichtlich kein `ports:`-Mapping.
- `KASSENSTURZ_HOST` muss `127.0.0.1` bleiben.
- Nicht auf `0.0.0.0` umstellen und keinen Reverse Proxy oder Port-Forwarding davorschalten.
- Smartphone-, LAN- und VPN-Zugriff sind in diesem Deployment noch nicht freigegeben.
- Die geplanten Pairing- und Token-Endpunkte sind noch nicht implementiert.
- `KASSENSTURZ_TRUSTED_PROXIES` und `KASSENSTURZ_MOBILE_CLIENT_NETWORKS` sind lediglich vorbereitete Allowlist-Konfigurationen. Leere Standardwerte, Loopback-Bindung und fehlende Mobile-Routen halten den Zugriff weiterhin geschlossen. Füge aktuell keinen Reverse Proxy hinzu.

Host-Networking wird hier bewusst für Linux verwendet, damit der Prozess direkt an die Loopback-Schnittstelle des Hosts binden kann. Docker Desktop auf Windows/macOS ist für diese Compose-Datei nicht das unterstützte Ziel.

## Voraussetzungen

- Linux-Server
- Docker Engine und Docker Compose v2
- Freier lokaler TCP-Port 8099

## Installation

Im Repository-Verzeichnis:

```bash
cd deploy/standalone
cp .env.example .env
```

Passe bei Bedarf `PUID` und `PGID` in `.env` an die UID und GID des Linux-Benutzers an, der die Daten verwalten soll. Anschließend Verzeichnisse anlegen und Berechtigungen setzen:

```bash
mkdir -p data imports
sudo chown -R "$(id -u):$(id -g)" data imports
```

Image bauen und starten:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f kassensturz
```

Die Oberfläche ist anschließend **auf dem Server selbst** unter [http://127.0.0.1:8099](http://127.0.0.1:8099) erreichbar. Für einen administrativen Zugriff von einem anderen Rechner kann ein SSH-Lokal-Tunnel verwendet werden:

```bash
ssh -L 8099:127.0.0.1:8099 <benutzer>@<server>
```

Danach im lokalen Browser [http://127.0.0.1:8099](http://127.0.0.1:8099) öffnen. Der Tunnel ist kein Ersatz für die noch ausstehende native Mobile-Authentifizierung und sollte nur von vertrauenswürdigen Administrationsgeräten genutzt werden.

## Daten und Importe

- SQLite-Datenbank und lokale Geheimnisse: `./data`
- Import-Eingangsordner: `./imports`

Der Datenordner enthält die SQLite-Datenbank sowie die Banking-Geheimnisse:

- `secrets.json`: AES-256-GCM-verschlüsselte FinTS-PINs und der Enable-Banking-Private-Key.
- `secrets.key`: zufälliger 256-Bit-Installationsschlüssel, Modus `0600`.
- `kassensturz.sqlite`: Finanzdatenbank, Modus `0600`; das Datenverzeichnis ist auf `0700` beschränkt.

Beim ersten Speichern wird `secrets.key` automatisch angelegt. Alternativ kann in der lokalen, von Git ignorierten `.env` ein externer Schlüssel mit genau 64 Hex-Zeichen als `KASSENSTURZ_MASTER_KEY` gesetzt werden. Ein externer Schlüssel hat Vorrang vor `secrets.key`; wechselt er, kann die bisherige Geheimnisdatei nicht mehr entschlüsselt werden.

**Wichtig für Backups:** Verschlüsselte Geheimnisdatei und Schlüssel dürfen nicht gemeinsam in einem ungeschützten Backup liegen. Lege eine Sicherung des Schlüssels getrennt ab, zum Beispiel in einem administrativen Secret-Manager oder auf einem getrennten verschlüsselten Offline-Medium. Verliert man den Schlüssel, können gespeicherte PINs und der private Open-Banking-Schlüssel nicht rekonstruiert werden; sie müssen bei den Banken erneut eingerichtet werden. Die Finanztransaktionen in SQLite bleiben davon unberührt.

Für ein konsistentes Dateisystem-Backup den Dienst zuerst anhalten. Sichere Datenbank, Importe und verschlüsselte Geheimnisdatei mit deinem Backup-Werkzeug; bewahre den Schlüssel separat und geschützt auf:

```bash
docker compose stop
# ./data und ./imports jetzt mit einem geeigneten Backup-Werkzeug sichern.
# secrets.key separat in einem sicheren, getrennten Schlüssel-Backup aufbewahren.
docker compose start
```

Bei einer Wiederherstellung muss der passende Schlüssel vor dem ersten Start wieder unter `./data/secrets.key` liegen – außer du nutzt stattdessen dieselbe `KASSENSTURZ_MASTER_KEY` aus der geschützten `.env`.

## Aktualisieren

```bash
git pull
docker compose up -d --build
```

Vor Updates immer ein geprüftes Backup von `data` anlegen.

## Aktueller Funktionsumfang und offene Freigaben

Diese Variante verwendet dieselbe FastAPI-/SQLite-Anwendung wie das Home-Assistant-Add-on. Sie stellt keine neue Benutzerverwaltung und keinen Multi-Tenant-Betrieb bereit. Es handelt sich weiterhin um eine Installation für genau einen Haushalt.

Vor einer Freigabe für LAN, VPN oder mobile Apps müssen mindestens umgesetzt und getestet sein:

1. Pairing über einen kurzlebigen Einmalcode und individuelle Geräteverwaltung.
2. Gehashte, rotierende und widerrufbare Refresh-Tokens sowie kurzlebige Access-Tokens.
3. Authentifizierung und Autorisierung auf jeder Finanzdaten-Route.
4. Erzwungenes HTTPS mit dokumentierter Proxy-Vertrauensgrenze oder direktem TLS.
5. Rate-Limits, Sicherheits- und Regressionstests sowie ein dokumentierter Wiederherstellungsprozess.

Bis dahin bleibt der Listener auf Loopback beschränkt. Die optionale private Netzwerk-Allowlist aktiviert für sich allein weder einen Listener noch Mobile-HTTP-Endpunkte.
