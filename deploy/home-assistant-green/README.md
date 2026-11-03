# Home Assistant Green – isolierter Mobile-Test

Dieser Rollout installiert eine **zweite, getrennte Kassensturz-Instanz** mit dem Slug
`kassensturz-mobile-test`. Sie ersetzt oder aktualisiert die vorhandene
Kassensturz-Installation nicht.

## Sicherheitsgrenzen

- Eigener Add-on-Slug und damit eigenes persistentes Supervisor-Datenverzeichnis.
- Keine Kopie der Produktions-SQLite-Datenbank.
- Keine Bankzugangsdaten, FinTS-Produktkennung oder Open-Banking-Secrets.
- Hintergrundabrufe und Scheduler sind über `KASSENSTURZ_NO_BACKGROUND=1` deaktiviert.
- Home-Assistant-Sensoren sind deaktiviert.
- `trusted_proxies`, `mobile_client_networks` und `mobile_server_url` bleiben leer.
- Der Container-Port `8099/tcp` ist standardmäßig nicht auf einen Host-Port abgebildet.
- Kein Tailscale-Service-Host, kein Router-Portforwarding und kein Funnel werden durch dieses Paket aktiviert.
- Die Add-on-App startet nur manuell (`boot: manual`).

## 1. Paket aus GitHub Actions laden

Auf dem Branch `architecture/local-first-mobile` den Workflow **Tests** öffnen.
Nach erfolgreichem Job `home-assistant-green-test-addon` das Artifact
`kassensturz-mobile-test-addon` herunterladen.

Workflow:
https://github.com/uekala/kassensturz/actions/workflows/tests.yml

Das Artifact enthält die vollständige lokale Add-on-Struktur:
`config.yaml`, `Dockerfile`, `app/` und `TEST-INSTANCE.txt`.

## 2. In Home Assistant als lokales Add-on ablegen

Das Home-Assistant-Samba-Share stellt den Ordner `addons` bereit. Falls Samba
Share noch nicht installiert ist, kann es über den Home-Assistant-App-Store
installiert werden. Alternativ kann ein bereits eingerichteter SSH-Zugang den
lokalen Add-on-Pfad verwenden.

Im Samba-Share den Ordner `local_apps` öffnen (der ältere Freigabename
`addons` zeigt auf denselben Bereich). Darin einen Ordner
`kassensturz-mobile-test` anlegen:

```text
local_apps/
└── kassensturz-mobile-test/
    ├── config.yaml
    ├── Dockerfile
    ├── TEST-INSTANCE.txt
    └── app/
        ├── requirements.txt
        └── kassensturz/
            └── ...
```

Die ZIP-Datei öffnen und ihren **Inhalt** (also `config.yaml`, `Dockerfile`,
`TEST-INSTANCE.txt` und `app/`) nach
`local_apps/kassensturz-mobile-test/` kopieren. Falls der ZIP-Entpacker einen
zusätzlichen übergeordneten Ordner anlegt, nicht diesen Ordner als App-Ordner
verwenden: `config.yaml` muss direkt im Ordner
`local_apps/kassensturz-mobile-test/` liegen.

Nicht in den bestehenden Produktionsordner `local_apps/kassensturz/` kopieren
und dort keine Dateien überschreiben.

Home Assistant sucht lokale Apps direkt unter `/addons/<app-slug>`; die
Samba-Freigabe `local_apps` stellt genau diesen Bereich bereit. Danach im
App-Store über das Drei-Punkte-Menü **Apps neu laden / Check for updates**
ausführen. Es sollte eine eigene Sektion **Lokale Apps** erscheinen.

Dokumentation:
https://www.home-assistant.io/common-tasks/os/

## 3. Test-App installieren

1. Im Home-Assistant-App-Store unter **Lokale Apps** die
   **Kassensturz Mobile Test**-App öffnen.
2. Vor der Installation die Konfiguration prüfen. Die Optionen
   `mobile_server_url`, `trusted_proxies` und `mobile_client_networks`
   müssen leer sein.
3. **Installieren**, aber nicht den automatischen Start aktivieren.
4. Die App manuell starten und warten, bis sie als laufend angezeigt wird.
5. Über den Ingress-Link **Kassensturz Test** öffnen.

Die bestehende App **Kassensturz** bleibt unverändert und kann weiter verwendet
werden.

## 4. Ausschließlich synthetische Daten verwenden

Beim ersten Öffnen kann über **Mit Beispieldaten ausprobieren** der vorhandene
Demo-Datensatz geladen werden. Dieser enthält erfundene Konten und Buchungen
und kann über die Funktion **Beispieldaten entfernen** wieder gelöscht werden.

Keine echten Bankverbindungen einrichten und keine Produktionsdaten importieren.
Der Zweck dieser Instanz ist zunächst, die getrennte App, die Mobile-API und den
Pairing-Ablauf zu prüfen.

## 5. Noch keine Fernfreigabe

Die lokale Test-App ist noch nicht über Tailscale erreichbar. Das ist beabsichtigt.

Erst nach Prüfung des Testcontainers werden wir separat:

1. den Host-Port `18099` auf Container-Port `8099` abbilden;
2. den Tailscale-Service `svc:kassensturz` auf
   `http://127.0.0.1:18099` konfigurieren;
3. Peer-Adresse und `X-Forwarded-Proto` des Tailscale-Service nachweisen;
4. danach erst `trusted_proxies` und `mobile_server_url` gezielt konfigurieren;
5. LAN-Direktzugriff und den HTTPS-Healthcheck testen, bevor ein Smartphone
   gekoppelt wird.

Es wird kein Router-Port geöffnet und kein Funnel eingeschaltet.

## Rollback

- Die bestehende Produktions-App nicht stoppen, aktualisieren oder entfernen.
- Zum Deaktivieren ausschließlich **Kassensturz Mobile Test** stoppen.
- Da die Test-App einen eigenen Slug hat, verwendet sie ein eigenes
  Supervisor-Datenverzeichnis. Die Produktionsdatenbank wird nicht berührt.
- Das lokale Verzeichnis
  `addons/local/kassensturz-mobile-test/` kann nach dem Stoppen archiviert
  oder entfernt werden. Vor einer Deinstallation/Testdatenbereinigung bei
  Bedarf die Testdaten separat exportieren.
- Die vorhandene Tailscale-Policy und der bereits vergebene
  `tag:homeassistant`-Tag bleiben unverändert.

## Freigabekriterien

Der Test-Rollout gilt erst als bereit für die private Tailscale-Anbindung, wenn:

- die Test-App unabhängig von der Produktions-App startet;
- Demo-Daten ausschließlich in der Testinstanz sichtbar sind;
- `GET /api/v1/health` über den vorgesehenen HTTPS-Service funktioniert;
- untrusted LAN-Peers weiterhin abgewiesen werden;
- die lokale HA-Geräteverwaltung nicht über den Tailscale-Service erreichbar ist;
- Pairing, Refresh, Logout und Gerätewiderruf mit einem Testgerät erfolgreich
  geprüft wurden.
