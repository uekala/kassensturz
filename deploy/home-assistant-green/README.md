# Kassensturz auf dem Home Assistant Green

Auf dem Green läuft genau eine Instanz: die lokale App `local_kassensturz` mit den echten Daten. Die frühere Testinstanz
`kassensturz-mobile-test` gibt es seit dem 11.11.2026 nicht mehr; ihr Paket und ihr CI-Job sind entfernt.

## Aktualisieren

1. Den Ordner `kassensturz/` aus diesem Repository nach `local_apps/kassensturz` auf dem Green legen (Samba). Den alten
   Inhalt ersetzen, nicht mischen. Die Daten liegen nicht in diesem Ordner.
2. In Home Assistant unter *Einstellungen → Apps* den Store neu laden; das Update wird angeboten, sobald die Version in
   `config.yaml` höher ist.
3. Update mit Backup starten. Home Assistant hält die App für das Backup kurz an (`backup: cold`) und baut das Image
   danach selbst.

Beim ersten Start einer neuen Version legt die App zusätzlich eine Kopie der bisherigen Datenbank in `/data/backups` ab.

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
