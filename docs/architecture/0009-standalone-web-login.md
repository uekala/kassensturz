# Architecture Decision Record 0009: Anmeldung an der Weboberfläche im eigenständigen Betrieb

- Status: Accepted
- Datum: 2026-11-25
- Geltungsbereich: Weboberfläche und ihre Verwaltungswege im eigenständigen Betrieb (Docker ohne Home Assistant)
- Bezug: ADR 0001 (Local-first), ADR 0002 (Mobile API security), ADR 0007 (Home Assistant Green)

## Ausgangslage

Als Home-Assistant-App meldet Home Assistant an: Die Weboberfläche ist nur über Ingress erreichbar. Im
eigenständigen Betrieb gibt es kein Ingress. Bisher war die Weboberfläche dort nur auf dem Server selbst
erreichbar, und jede Verbindung über Loopback galt als lokaler Zugriff ohne Anmeldung. Ein Reverse Proxy vor
dem Dienst hätte deshalb alles geöffnet und war untersagt.

## Entscheidung

Der eigenständige Dienst bekommt eine Anmeldung mit **einem Benutzernamen und einem Passwort (HTTP Basic)**,
ausschließlich über einen **vertrauenswürdigen HTTPS-Proxy auf demselben Server**. Der Listener bleibt auf
`127.0.0.1` beschränkt.

## Regeln

1. Die Anmeldung ist nur aktiv, wenn `KASSENSTURZ_WEB_PASSWORD` gesetzt ist und kein Supervisor-Token vorliegt.
   Als Home-Assistant-App bleibt alles unverändert.
2. Eine Anmeldung nimmt Kassensturz nur von einer Gegenstelle aus `KASSENSTURZ_TRUSTED_PROXIES` an, und nur,
   wenn der Proxy HTTPS zusichert (`X-Forwarded-Proto: https`). Ohne HTTPS antwortet der Dienst mit 426.
3. Mit eingerichteter Anmeldung ist ein Proxy, der über Loopback ankommt, kein lokaler Zugriff mehr. Trägt
   eine Loopback-Anfrage Weiterleitungs-Kopfzeilen, ohne dass der Proxy eingetragen ist, wird sie abgelehnt.
   Die Adresse des Home-Assistant-Ingress gilt ohne Supervisor nicht als lokal.
4. Nach fünf falschen Anmeldungen innerhalb von fünf Minuten ist die Adresse des Clients hinter dem Proxy
   gesperrt. Anfragen ohne Anmeldedaten zählen nicht.
5. Schreibende Anfragen müssen von der eigenen Seite kommen (`Origin` passt zu `Host` oder
   `X-Forwarded-Host`, `Sec-Fetch-Site` ist nicht fremd). Clients ohne Browser senden diese Kopfzeilen nicht
   und brauchen ohnehin das Passwort.
6. Die Verwaltungswege der Handy-Kopplung (`/api/mobile/pairings`, `/api/mobile/devices`) stehen dem
   angemeldeten Benutzer offen. Die Handy-API (`/api/v1`) bleibt bei ihren Geräte-Tokens.
7. `/healthz` bleibt für die Container-Prüfung direkt über Loopback ohne Anmeldung erreichbar und liefert
   keine Finanzdaten.
8. Das Änderungsprotokoll führt Änderungen über die Anmeldung unter dem Benutzernamen, Art `web`.

## Verworfen

- **Eigene Anmeldeseite mit Sitzung:** erlaubt Abmelden und mehrere Benutzer, verlangt aber Sitzungsverwaltung
  und einen Umbau der Oberfläche. Für einen Haushalt mit einem Benutzer nicht nötig.
- **Direkter Zugriff aus dem LAN:** Das Passwort ginge unverschlüsselt durchs Netz, und der Listener müsste
  die Loopback-Grenze verlassen.
- **Anmeldung ohne HTTPS als Option:** widerspricht ADR 0002.

## Folgen

- Das Passwort wird bei jeder Anfrage übertragen; deshalb gilt die HTTPS-Pflicht ohne Ausnahme.
- Abmelden heißt: Browser schließen oder die gespeicherten Zugangsdaten entfernen.
- Der Zahlungskalender für Home Assistant ist über den Proxy nicht abrufbar. Läuft Home Assistant auf einem
  anderen Rechner, entfällt er im eigenständigen Betrieb.
- Wer einen Proxy ohne `KASSENSTURZ_WEB_PASSWORD` davorschaltet, öffnet den Dienst weiterhin. Die Anleitung
  warnt davor.
