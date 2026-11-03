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
- **Vertrauensmodell:** ein Haushalt, eine lokale Installation, kein Kassensturz-Cloudkonto, kein Relay und kein öffentlicher Port.

## Netz- und Freigabegrenzen

Die bestehende Home-Assistant-Ingress-Oberfläche bleibt der administrative Weg für die Kassensturz-Weboberfläche. Native Mobile-Clients erhalten später einen eigenen HTTPS-Zugriffsweg auf die versionierte Mobile-API.

Wichtige Grenzen:

1. Die Add-on-Portfreigabe bleibt standardmäßig deaktiviert. ingress_port ist der interne Port des Add-ons und allein keine Freigabe für LAN- oder VPN-Clients.
2. KASSENSTURZ_MOBILE_CLIENT_NETWORKS bleibt leer, bis die tatsächliche VPN-/LAN-Topologie bekannt und der Zugriff gezielt eingerichtet ist.
3. Es wird kein Router-Portforwarding und kein öffentlich erreichbarer Kassensturz-Port eingerichtet.
4. Native Clients akzeptieren ausschließlich HTTPS mit gültiger Zertifikatsprüfung.
5. Für HTTPS-Terminierung vor dem Add-on wird ein explizit vertrauenswürdiger Proxy benötigt. Dessen unmittelbare Peer-IP muss in KASSENSTURZ_TRUSTED_PROXIES stehen. Weitergeleitete Header von nicht vertrauenswürdigen Gegenstellen sind nicht zulässig.
6. Die bestehende Ingress-Sitzung wird nicht als Ersatz für die Geräteauthentifizierung der Mobile-API verwendet.
7. Die lokale Geräteverwaltung (Pairing-Secret erzeugen, Geräte auflisten/widerrufen) bleibt dem authentifizierten Home-Assistant-Ingress-/Loopback-Administrationspfad vorbehalten.

Die Home-Assistant-App-Konfiguration unterstützt explizite Container-Port-Mappings; ein Mapping kann deaktiviert bleiben. Die genaue Netzwerk- und TLS-Integration wird vor der Freigabe für native Clients separat umgesetzt und getestet. Siehe [Home Assistant App configuration](https://developers.home-assistant.io/docs/apps/configuration/).

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
2. Sicheren, dedizierten HTTPS-Zugriffsweg über das bestehende VPN entwerfen; keine Portfreigabe standardmäßig aktivieren.
3. HA-App-Build für die Green-Architektur (aarch64) in CI verifizieren.
4. Pairing-Erzeugung ausschließlich für Home-Assistant-Administratoren in der Ingress-Oberfläche bereitstellen.
5. Flutter-Verbindungsassistent, Healthcheck, QR-Pairing und Secure Storage integrieren.
6. End-to-End-Tests auf dem realen Green mit iOS und Android ausführen.
7. Erst nach Backup-/Restore-, Widerrufs- und Netzwerktests den Zugriff für die persönliche Nutzung aktivieren.

## Konsequenzen

- Keine zusätzliche Hardwarebeschaffung für den Start.
- Home Assistant Green ist zunächst die einzige produktive Dateninstanz.
- Die Kassensturz-Web-App bleibt über Ingress nutzbar.
- Mobile-Zugriff ist noch nicht betriebsbereit, nur weil die API-Routen im Feature-Branch registriert sind.
- Kein Wechsel auf main und keine Installation auf dem realen Green im Rahmen dieser Architekturentscheidung.