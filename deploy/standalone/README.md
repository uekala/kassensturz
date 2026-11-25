# Eigenständiger Betrieb mit Docker (Linux)

Diese Deployment-Variante betreibt Kassensturz ohne Home Assistant auf einem Linux-Server. Der Dienst lauscht nur auf dem Server selbst. Von anderen Geräten aus ist er ausschließlich über einen HTTPS-Proxy auf demselben Server erreichbar, mit Benutzername und Passwort; ein direkter Zugriff aus dem LAN oder eine Freigabe ins Internet ist nicht vorgesehen.

## Sicherheitsgrenze

Die Compose-Datei bindet den Prozess über Host-Networking ausschließlich an `127.0.0.1:8099`. Daran ändert sich
nichts, und `check-config.sh` prüft es.

- Es gibt absichtlich kein `ports:`-Mapping.
- `KASSENSTURZ_HOST` muss `127.0.0.1` bleiben. Nicht auf `0.0.0.0` umstellen, kein Port-Forwarding, keine
  Freigabe am Router.
- Ohne weitere Einstellungen ist die Weboberfläche nur auf dem Server selbst erreichbar. Kassensturz hält dann
  jede Verbindung über Loopback für einen lokalen Zugriff und fragt nicht nach einer Anmeldung.
- **Deshalb nie einen Reverse Proxy ohne `KASSENSTURZ_WEB_PASSWORD` davorschalten.** Ohne Passwort wäre über
  den Proxy alles offen.
- Für den Zugriff von anderen Geräten gibt es genau einen vorgesehenen Weg: ein HTTPS-Proxy auf demselben
  Server zusammen mit der Anmeldung, siehe [Zugriff über einen HTTPS-Proxy](#zugriff-über-einen-https-proxy).

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

## Zugriff über einen HTTPS-Proxy

So erreichst du die Weboberfläche von anderen Geräten, ohne den Dienst im Netz zu öffnen. Der Proxy läuft auf
demselben Server, stellt das Zertifikat bereit und zeigt auf `http://127.0.0.1:8099`; ein Beispiel ist
Tailscale Serve.

1. In der Datei `.env` setzen:

   ```
   KASSENSTURZ_WEB_PASSWORD=ein-langes-eigenes-passwort
   KASSENSTURZ_TRUSTED_PROXIES=127.0.0.1/32
   ```

   Der Benutzername ist `kassensturz`, solange `KASSENSTURZ_WEB_USER` nichts anderes vorgibt. Die Datei mit
   `chmod 600 .env` schützen.
2. Den Proxy einrichten. Er muss `X-Forwarded-Proto` und `X-Forwarded-For` selbst setzen und Werte, die ein
   Client mitschickt, überschreiben.
3. Den Dienst neu starten (`docker compose up -d`) und die HTTPS-Adresse des Proxys öffnen. Der Browser fragt
   nach Benutzername und Passwort.

Was dann gilt:

- Anmelden geht nur über den eingetragenen Proxy und nur, wenn die Verbindung zum Proxy HTTPS war.
- Auch eine direkte Verbindung über Loopback zählt nicht mehr als lokaler Zugriff, ein SSH-Tunnel also auch
  nicht. Die Container-Prüfung (`/healthz`, ohne Finanzdaten) bleibt davon ausgenommen.
- Steht der Proxy nicht in `KASSENSTURZ_TRUSTED_PROXIES`, lehnt Kassensturz seine Anfragen ab.
- Nach fünf falschen Anmeldungen ist die Adresse des Geräts fünf Minuten gesperrt.
- Schreibende Anfragen nimmt Kassensturz nur von der eigenen Seite an, nicht von fremden Webseiten im selben
  Browser.
- Das Änderungsprotokoll nennt bei Änderungen über die Weboberfläche den Benutzernamen.
- Die Handy-App läuft über denselben Proxy und bleibt bei ihren Geräte-Tokens. Gekoppelt wird sie in der
  angemeldeten Weboberfläche; dafür muss `mobile_server_url` in `data/options.json` die HTTPS-Adresse nennen.
- Der Zahlungskalender für Home Assistant ist über den Proxy nicht abrufbar. Läuft Home Assistant auf einem
  anderen Rechner, entfällt er in dieser Variante.

### Home Assistant anbinden

Sensoren, Benachrichtigungen und Events gehen an Home Assistant, wenn beide Werte in `.env` gesetzt sind:

```
KASSENSTURZ_HA_API=http://192.168.1.20:8123/api
KASSENSTURZ_HA_TOKEN=langlebiges-zugriffstoken
```

Das Token legst du in Home Assistant unter *Profil → Sicherheit* an. Die übrigen Einstellungen der
Home-Assistant-App (zum Beispiel `sync_time`, `notify_service`, `mobile_server_url`) stehen im eigenständigen
Betrieb in `data/options.json`, mit denselben Namen wie in der App.

## Daten und Importe## Daten und Importe

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

## Funktionsumfang und Grenzen

Diese Variante verwendet dieselbe FastAPI-/SQLite-Anwendung wie das Home-Assistant-Add-on. Sie stellt keine Benutzerverwaltung und keinen Multi-Tenant-Betrieb bereit. Es handelt sich weiterhin um eine Installation für genau einen Haushalt.

- Die Weboberfläche kennt außerhalb von Home Assistant genau einen Benutzer (Benutzername und Passwort über
  HTTPS, siehe [ADR 0009](../../docs/architecture/0009-standalone-web-login.md)).
- Die Handy-App koppelt sich mit einem kurzlebigen Einmalcode und bekommt ein eigenes, widerrufbares Token.
- Nicht vorgesehen sind: ein direkter Zugriff aus dem LAN ohne Proxy, eine Portfreigabe ins Internet und
  mehrere Benutzer der Weboberfläche.

Ein fertiges Image liegt unter `ghcr.io/uekala/kassensturz` (amd64 und arm64). Wer es statt des eigenen Builds
nutzen will, trägt es in der Compose-Datei bei `image:` ein und entfernt den Abschnitt `build:`.
