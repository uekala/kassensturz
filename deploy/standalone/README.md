# Eigenständiger Betrieb mit Docker (Linux)

Diese Deployment-Variante betreibt Kassensturz ohne Home Assistant auf einem Linux-Server. Sie ist für den lokalen Zugriff auf dem Server vorgesehen und **nicht** für den Zugriff aus dem LAN oder über das Internet freigeschaltet.

## Sicherheitsgrenze

Die bestehende Anwendung besitzt noch keine produktive Mobile-Authentifizierung. Die aktuellen HTTP-Routen sind für Home-Assistant-Ingress entwickelt; die Middleware akzeptiert außerdem Loopback-Verbindungen. Deshalb bindet diese Compose-Datei den Prozess über Host-Networking ausschließlich an `127.0.0.1:8099`.

- Es gibt absichtlich kein `ports:`-Mapping.
- `KASSENSTURZ_HOST` muss `127.0.0.1` bleiben.
- Nicht auf `0.0.0.0` umstellen und keinen Reverse Proxy oder Port-Forwarding davorschalten.
- Smartphone-, LAN- und VPN-Zugriff sind in diesem Deployment noch nicht freigegeben.
- Die geplanten Pairing- und Token-Endpunkte sind noch nicht implementiert.

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

Der Datenordner enthält Finanzdaten und Zugangsdaten. Er muss durch Dateisystemrechte geschützt und in verschlüsselte, zugriffsbeschränkte Backups aufgenommen werden. Die aktuelle Speicherung der Bankgeheimnisse ist noch nicht anwendungsseitig verschlüsselt. Die Compose-Härtung ersetzt keine Verschlüsselung der Daten oder Backups.

Für ein konsistentes Dateisystem-Backup den Dienst zuerst anhalten:

```bash
docker compose stop
# ./data und ./imports jetzt mit einem geeigneten Backup-Werkzeug sichern
docker compose start
```

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

Bis dahin bleibt der Listener auf Loopback beschränkt.
