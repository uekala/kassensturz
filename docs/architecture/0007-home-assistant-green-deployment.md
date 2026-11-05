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
- **Tailscale-Host:** `tag:homeassistant` wurde am bestehenden Home-Assistant-Knoten gesetzt; die aktuelle Admin-Konsole zeigt den Knoten als verbunden.
- **Tailscale-Service:** `svc:kassensturz` wurde mit `tcp:443` definiert; der Service hat noch keinen beworbenen oder genehmigten Host.
- **Pairing:** QR-Code wird nur erzeugt, wenn die optionale Add-on-Option `mobile_server_url` eine gültige HTTPS-Origin enthält. Sie ist standardmäßig leer und wird erst nach Verifikation der Tailscale-Service-Adresse gepflegt.
- **Vertrauensmodell:** ein Haushalt, eine lokale Installation, kein Kassensturz-Cloudkonto, kein Relay und kein öffentlicher Port.

## Netz- und Freigabegrenzen

Die bestehende Home-Assistant-Ingress-Oberfläche bleibt der administrative Weg für die Kassensturz-Weboberfläche. Native Mobile-Clients erhalten einen separaten HTTPS-Zugriffsweg über einen Tailscale Service. Dieser Dienst hat einen eigenen Tailscale-Service-Namen und verändert die bestehende Home-Assistant-Adresse nicht.

Wichtige Grenzen:

1. Die Kassensturz-Container-Portfreigabe für 8099/TCP bleibt in `config.yaml` mit `null` standardmäßig deaktiviert. `ingress_port: 8099` ist weiterhin nur der interne Ingress-Port.
2. Für den Tailscale-Service wird in der Kassensturz-HA-App-Netzwerkverwaltung ein dedizierter Host-Port (vorgesehen: 18099) auf den Container-Port 8099 abgebildet. Die Anwendung lässt direkte Anfragen über diesen Port durch ihre Netzwerk-Middleware weiterhin nur von lokalen oder ausdrücklich vertrauenswürdigen Gegenstellen zu.
3. Das offizielle Home Assistant Community Tailscale Add-on läuft mit `host_network: true` und unterstützt die Optionen `advertise_tags` und `services`. Sein Service-Ziel muss eine lokale Loopback-Adresse sein. Es wird deshalb auf `http://127.0.0.1:18099` verwiesen.
   
   Die Service-Ressource `svc:kassensturz` ist bereits in der Tailscale-Admin-Konsole definiert. Ihr Endpunkt ist `tcp:443`; das Add-on konfiguriert dazu den HTTPS-Layer-7-Endpunkt und stellt intern eine HTTP-Verbindung zum Kassensturz-Backend her:

   ```yaml
   advertise_tags:
     - tag:homeassistant
   services:
     - name: svc:kassensturz
       target: http://127.0.0.1:18099
       protocol: https
       port: 443
       path: /
   ```

   Tailscale provisioniert das TLS-Zertifikat für `https://kassensturz.tail1966da.ts.net`. MagicDNS und HTTPS-Zertifikate müssen im Tailnet aktiviert sein. Funnel bleibt deaktiviert.
4. Der bestehende Home-Assistant-Tailscale-Knoten wechselt durch `advertise_tags: [tag:homeassistant]` von persönlicher Benutzeridentität zu einer tagbasierten Geräteidentität. Tailscale Services erfordern diese Identität; das ist keine rein zusätzliche Kennzeichnung. Daher werden vorher in der Policy `tagOwners` sowie automatische Genehmigungen für die bestehende Subnetzroute `192.168.50.0/24` und den Exit-Node vorbereitet. Die vorhandene `advertise_routes`-, `advertise_exit_node`-, SNAT- und TUN-Konfiguration bleibt erhalten. Die allgemeine Zugriffsregel wird während dieses Schritts nicht verändert.
5. Der Kassensturz-Service-Host wird zunächst **manuell** auf der Services-Seite freigegeben, nicht automatisch über `autoApprovers.services`. So bleibt die erste Aktivierung ein bewusster administrativer Schritt. Die Service-Definition ist bereits angelegt; der Host ist zum aktuellen Stand noch nicht advertised.
6. Die `trusted_proxies`-Option wird erst nach der Prüfung der tatsächlichen TCP-Gegenstelle und der vom Tailscale-Service gelieferten `X-Forwarded-Proto`-Header gesetzt. `mobile_client_networks` bleibt für diesen Proxy-Weg leer. Die Middleware verlangt von einem vertrauenswürdigen Proxy exakt `X-Forwarded-Proto: https`; keine pauschale Freigabe des Supervisor-Netzes.
7. Die App-Middleware verweigert direkte Requests von nicht freigegebenen LAN-/VPN-Peers. Die Portfreigabe wird nicht am Router weitergeleitet und es wird kein Funnel für Kassensturz aktiviert.
8. Native Clients akzeptieren ausschließlich HTTPS mit gültiger Zertifikatsprüfung.
9. Die bestehende Ingress-Sitzung wird nicht als Ersatz für die Geräteauthentifizierung der Mobile-API verwendet.
10. `panel_admin: true` beschränkt den Home-Assistant-Ingress-Einstieg ausdrücklich auf Administratoren. Die Supervisor-Kennung `X-Remote-User-Id` muss bei Ingress-Aufrufen vorhanden sein; fehlt sie, werden Pairing-Erzeugung, Geräteauflistung und -widerruf abgewiesen. Loopback bleibt ausschließlich für lokale Prozesse freigegeben.
11. Die lokale Geräteverwaltung bleibt dem authentifizierten Home-Assistant-Ingress-/Loopback-Administrationspfad vorbehalten.

Home Assistant unterstützt deaktivierte Port-Mappings mit `null`; die Tailscale-Addon-Dokumentation beschreibt den `services`-Mechanismus für weitere lokale Dienste.

Der Tailscale-Knoten zeigt inzwischen `tag:homeassistant` als ACL-Tag und `Connected` als Gerätestatus. Die zuletzt bereitgestellten Tailscale-Protokolle bestätigen `tags=tag:homeassistant` sowie die weiter geladenen Routen `0.0.0.0/0`, `::/0` und `192.168.50.0/24`. Der anfängliche Startfehler wurde durch Deaktivieren der separaten `share_homeassistant`-Serve/Funnel-Freigabe behoben. Die Tailscale-Service-Ressource wurde in der Admin-Konsole bereits als `svc:kassensturz` mit `tcp:443` angelegt. Der aktuelle Status zeigt noch keine Service-Hosts. Die Community-App-Dokumentation beschreibt die `services`-Option, die Loopback-Zieladresse und die Pflicht einer tagbasierten Identität; die Host-Freigabe erfolgt nach dem Advertise manuell. Siehe [Home Assistant App configuration](https://developers.home-assistant.io/docs/apps/configuration/) und [Tailscale-Addon services](https://github.com/hassio-addons/app-tailscale/blob/main/tailscale/DOCS.md#option-services).

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
2. ARM64-Build für die Green-Architektur in CI verifizieren.
3. Einen zweiten lokalen Test-Add-on-Slug `kassensturz-mobile-test` mit eigener Supervisor-Datenablage erzeugen; Produktions-App und -Daten bleiben unverändert.
4. Test-Add-on manuell installieren und starten; keine Banking-Secrets übernehmen, Hintergrund-Scheduler und Sensoren deaktivieren, keine Host-Portfreigabe setzen.
5. Mit synthetischen Beispieldaten die Ingress-Oberfläche, Mobile-API und Geräteverwaltung prüfen.
6. Optionales Add-on-Port-Mapping und Tailscale-Service vorbereiten, standardmäßig weiterhin deaktiviert lassen.
7. Tailscale-Service und Proxy-Header auf dem realen Green prüfen; LAN-Direktzugriff muss mit 403 abgewiesen und der HTTPS-Service im Tailnet erfolgreich erreichbar sein.
8. Flutter-Verbindungsassistent, Healthcheck, QR-Pairing und Secure Storage mit iOS und Android end-to-end testen.
9. Erst nach Backup-/Restore-, Widerrufs- und Netzwerktests entscheiden, ob die Mobile-API in die bestehende Produktionsinstanz übernommen wird.

## Isolierter Green-Test-Rollout

Für den ersten realen Test wird ein separates lokales Add-on unter dem Slug `kassensturz-mobile-test` verwendet. Das Paket wird im CI aus demselben Backend-Quellcode gebaut und als GitHub Actions Artifact bereitgestellt. Die Test-App ist `boot: manual`, nur für `aarch64`, hat eigene Supervisor-Datenhaltung, deaktivierte Sensoren und keinen automatischen Hintergrundabruf. `trusted_proxies`, `mobile_client_networks` und `mobile_server_url` bleiben leer; `8099/tcp` ist nicht auf einen Host-Port gemappt. Die Installation erfolgt neben der bestehenden App über `/addons/local/kassensturz-mobile-test/`. Siehe [Green-Test-Installationsanleitung](../../deploy/home-assistant-green/README.md).

## Konsequenzen

- Keine zusätzliche Hardwarebeschaffung für den Start.
- Home Assistant Green ist zunächst die einzige produktive Dateninstanz.
- Die Kassensturz-Web-App bleibt über Ingress nutzbar.
- Mobile-Zugriff ist noch nicht betriebsbereit, nur weil die API-Routen im Feature-Branch registriert sind.
- Kein Wechsel auf main und keine Installation auf dem realen Green im Rahmen dieser Architekturentscheidung.