# Architecture Decision Record 0007: Home Assistant Green als erste Serverplattform

- Status: Accepted
- Datum: 2026-11-03
- Geltungsbereich: Erstdeployment der lokalen Kassensturz-Mobile-API
- Bezug: ADR 0001 (Local-first), ADR 0002 (Mobile API security), ADR 0003 (API contract), ADR 0006 (Flutter)

## Entscheidung

Der vorhandene **Home Assistant Green** wird zunächst als Kassensturz-Server verwendet. Es wird vorerst weder ein separater Mini-PC noch ein Cloudserver beschafft.

Kassensturz läuft als bestehende Home-Assistant-App (Add-on) auf dem Green. Die Mobile-API wird im bereits vorhandenen FastAPI-Prozess und in derselben lokalen Kassensturz-Installation betrieben. SQLite bleibt die Datenbank. Es entsteht weder eine zweite Datenhaltung noch ein zusätzlicher Synchronisationsdienst.

## Zielarchitektur

- **Host:** Home Assistant Green mit Home Assistant OS und Supervisor.
- **Anwendung:** bestehende Kassensturz-App / Add-on (slug: kassensturz).
- **Backend:** FastAPI im Add-on-Container.
- **Datenbank:** lokale SQLite-Datenbank im persistenten Add-on-Datenverzeichnis.
- **Mobile Client:** gemeinsame Flutter-App für iOS und Android.
- **Zugriff:** lokal im WLAN oder über das vom Nutzer verwaltete VPN.
- **Pairing:** QR-Code wird nur erzeugt, wenn die optionale Add-on-Option `mobile_server_url` eine gültige HTTPS-Origin enthält. Sie ist standardmäßig leer und wird erst nach Verifikation der Tailscale-Service-Adresse gepflegt.
- **Vertrauensmodell:** ein Haushalt, eine lokale Installation, kein Kassensturz-Cloudkonto, kein Relay und kein öffentlicher Port.

## Netz- und Freigabegrenzen

Die bestehende Home-Assistant-Ingress-Oberfläche bleibt der administrative Weg für die Kassensturz-Weboberfläche. Native Mobile-Clients erhalten einen separaten HTTPS-Zugriffsweg über einen Tailscale Service. Dieser Dienst hat einen eigenen Tailscale-Service-Namen und verändert die bestehende Home-Assistant-Adresse nicht.

Wichtige Grenzen:

1. Die neue Container-Portfreigabe für 8099/TCP ist in `config.yaml` mit `null` standardmäßig deaktiviert. `ingress_port: 8099` ist weiterhin nur der interne Ingress-Port.
2. Erst für den Tailscale-Service wird in der HA-App-Netzwerkverwaltung ein dedizierter Host-Port (vorgesehen: 18099) auf den Container-Port 8099 abgebildet.
3. Das Tailscale-Add-on veröffentlicht einen eigenen Service `svc:kassensturz`, der intern auf `http://127.0.0.1:18099` zeigt und nach außen HTTPS auf Port 443 bereitstellt. Das Tailscale-Add-on muss die `services`-Option unterstützen und im Host-Netzwerk laufen. Die aktuelle Add-on-Konfiguration beschränkt `target` ausdrücklich auf lokale Loopback-Adressen.

   Beispiel für die `services`-Option:

   ```yaml
   services:
     - name: svc:kassensturz
       target: http://127.0.0.1:18099
       protocol: https
       port: 443
       path: /
   ```
4. Der Tailscale-Knoten benötigt ein in der bestehenden Tailnet-Policy erlaubtes `advertise_tags`-Tag. Der Service muss auf der Services-Seite der Tailscale-Admin-Konsole definiert, der Home-Assistant-Knoten als Service-Host freigegeben und mit einer Grant-Regel ausschließlich für den eigenen Nutzer bzw. eine ausdrücklich ausgewählte Gruppe erreichbar gemacht werden. MagicDNS und HTTPS-Zertifikate müssen im Tailscale-DNS-Bereich aktiviert sein.
5. Die `trusted_proxies`-Option wird erst nach der Prüfung der tatsächlichen TCP-Gegenstelle des Tailscale-Services gesetzt (voraussichtlich `127.0.0.1/32`, am Green zu verifizieren). `mobile_client_networks` bleibt für diesen Proxy-Weg leer. Die Middleware verlangt bei einem vertrauenswürdigen Proxy zusätzlich exakt `X-Forwarded-Proto: https`; ob der Tailscale-Service diesen Header im konkreten Add-on-Build setzt, muss vor Freigabe geprüft werden. Keine pauschale Freigabe des Supervisor-Netzes.
6. Die App-Middleware verweigert direkte Requests von nicht freigegebenen LAN-/VPN-Peers. Die Portfreigabe wird von außen nicht am Router weitergeleitet und es wird kein Funnel für Kassensturz aktiviert.
7. Native Clients akzeptieren ausschließlich HTTPS mit gültiger Zertifikatsprüfung.
8. Die bestehende Ingress-Sitzung wird nicht als Ersatz für die Geräteauthentifizierung der Mobile-API verwendet.
9. `panel_admin: true` beschränkt den Home-Assistant-Ingress-Einstieg ausdrücklich auf Administratoren. Die Supervisor-Kennung `X-Remote-User-Id` muss bei Ingress-Aufrufen vorhanden sein; sie wird vom Supervisor gesetzt und von nicht vertrauenswürdigen Aufrufern entfernt. Fehlt sie, werden Pairing-Erzeugung, Geräteauflistung und -widerruf abgewiesen. Loopback bleibt ausschließlich für lokale Prozesse freigegeben.
10. Die lokale Geräteverwaltung (Pairing-Secret erzeugen, Geräte auflisten/widerrufen) bleibt dem authentifizierten Home-Assistant-Ingress-/Loopback-Administrationspfad vorbehalten.

Home Assistant unterstützt deaktivierte Port-Mappings mit `null`; die Tailscale-Addon-Dokumentation beschreibt den `services`-Mechanismus für weitere lokale Dienste. Siehe [Home Assistant App configuration](https://developers.home-assistant.io/docs/apps/configuration/) und [Tailscale-Addon services](https://github.com/hassio-addons/app-tailscale/blob/main/tailscale/DOCS.md#option-services).

## Datenhaltung und Backup

- Finanzdaten und Mobile-Geräte-/Token-Metadaten liegen in der lokalen SQLite-Datenbank der Kassensturz-Installation.
- Bankzugangsdaten und Open-Banking-Schlüssel bleiben auf dem Green und werden nicht an die Flutter-App übertragen.
- Der Mobile-Client erhält nur die explizit erlaubten API-DTO-Felder.
- Vor dem ersten produktiven Pairing werden Backup und Wiederherstellung der SQLite-Datenbank sowie das Verhalten widerrufener Geräte bei einer Wiederherstellung geprüft.
- Die bestehenden Ausschlüsse für Banking-Secrets (secrets.json und secrets.key) bleiben bestehen. Diese Geheimnisse benötigen weiterhin einen getrennten, geschützten Sicherungs- und Wiederherstellungsprozess.

## Ressourcen und Skalierung

Die erste Nutzung ist auf einen Haushalt und eine begrenzte Zahl persönlicher Geräte ausgelegt. Es wird kein GPU-Server benötigt. Die tatsächliche Last wird nach Verbindung des Flutter-Clients beobachtet. Ein separater Mini-PC wird erst dann erwogen, wenn Messwerte oder zusätzliche Anforderungen dies rechtfertigen.

Die derzeitige In-Memory-Rate-Limit-Implementierung ist nur für einen einzelnen App-Prozess geeignet. Die Mobile-API wird auf dem Green zunächst nur mit einem Prozess betrieben. Mehrprozessbetrieb benötigt vorher gemeinsamen, transaktionalen Rate-Limit-Zustand und gerätebezogene Limits.

## Umsetzungsreihenfolge

1. Backend-API und Sicherheitsprüfungen im separaten Feature-Branch fertigstellen.
2. Optionales Add-on-Port-Mapping und die Tailscale-Service-Definition vorbereiten, standardmäßig weiterhin deaktiviert lassen.
3. HA-App-Build für die Green-Architektur (aarch64) in CI verifizieren.
4. Pairing-Erzeugung in der Ingress-Oberfläche bereitstellen; `panel_admin: true` und `X-Remote-User-Id` serverseitig prüfen.
5. Flutter-Verbindungsassistent, Healthcheck, QR-Pairing und Secure Storage integrieren.
6. End-to-End-Tests auf dem realen Green mit iOS und Android ausführen.
7. Tailscale-Service und Proxy-Header auf dem realen Green prüfen; LAN-Direktzugriff muss mit 403 abgewiesen und der HTTPS-Service im Tailnet erfolgreich erreichbar sein.
8. Erst nach Backup-/Restore-, Widerrufs- und Netzwerktests den Zugriff für die persönliche Nutzung aktivieren.

## Konsequenzen

- Keine zusätzliche Hardwarebeschaffung für den Start.
- Home Assistant Green ist zunächst die einzige produktive Dateninstanz.
- Die Kassensturz-Web-App bleibt über Ingress nutzbar.
- Mobile-Zugriff ist noch nicht betriebsbereit, nur weil die API-Routen im Feature-Branch registriert sind.
- Kein Wechsel auf main und keine Installation auf dem realen Green im Rahmen dieser Architekturentscheidung.