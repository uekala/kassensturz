# Kassensturz auf dem Home Assistant Green

Auf dem Green läuft genau eine Instanz mit den echten Daten. Sie wird über GitHub installiert und aktualisiert:
Home Assistant liest dieses Repository als App-Quelle und bietet neue Versionen von selbst an.

## Installieren

1. *Einstellungen → Apps → App Store*, im Menü *Repositories* die Adresse `https://github.com/uekala/kassensturz`
   hinzufügen.
2. **Kassensturz** installieren. Home Assistant baut das Image auf dem Gerät.

## Aktualisieren

Sobald auf `main` eine höhere Version in `kassensturz/config.yaml` steht, bietet Home Assistant das Update an
(spätestens nach *Nach Updates suchen* im App Store). Update mit Backup starten: Home Assistant hält die App für das
Backup kurz an (`backup: cold`) und baut das Image danach selbst.

Beim ersten Start einer neuen Version legt die App zusätzlich eine Kopie der bisherigen Datenbank in `/data/backups` ab.

Was sich geändert hat, steht im [Änderungsprotokoll](../../kassensturz/CHANGELOG.md) und bei den
[Releases](https://github.com/uekala/kassensturz/releases).

## Umstieg von der lokalen App

Wer Kassensturz bisher als lokale App (`local_kassensturz`, Ordner `local_apps/kassensturz`) betrieben hat, bekommt mit
der Installation über GitHub eine zweite, leere App. Die Daten ziehen ab Server 0.3.6 so um, wie es in der
[Anleitung unter „Umzug in eine andere Installation“](../../kassensturz/DOCS.md) steht: Datenbank in der alten App
herunterladen, alte App stoppen, Datei in den Eingangsordner legen, neue App starten. Die Optionen aus der Tabelle unten,
PINs und der Enable-Banking-Schlüssel werden in der neuen App neu eingetragen. Erst wenn dort alles stimmt, die lokale
App und den Ordner `local_apps/kassensturz` entfernen.

Der lokale Weg bleibt als Ausweichlösung möglich: den Ordner `kassensturz/` nach `local_apps/kassensturz` legen und
den Store neu laden.

## Zugriff für die Mobile-App

| Einstellung | Wert |
|---|---|
| Netzwerk `8099/tcp` | Host-Port 18099 |
| `trusted_proxies` | `172.30.32.1/32` |
| `mobile_server_url` | HTTPS-Adresse des Tailscale-Service |
| Watchdog | eingeschaltet |

Der Tailscale-Service zeigt auf `http://127.0.0.1:18099`. Es gibt keine Portfreigabe am Router und keinen Funnel für
Kassensturz. Direkter Zugriff aus dem LAN wird abgewiesen; ohne HTTPS antwortet die Mobile-Schnittstelle mit 426.

Gekoppelt wird das Handy über den QR-Code in den Kassensturz-Einstellungen.
