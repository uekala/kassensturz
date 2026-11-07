# 0008 – Intelligenter Kündigungsassistent

## Status

Entwurf / Implementierungsgrundlage. Dieses Modul erweitert die bestehende Vertrags- und Kündigungsvorlage. Es ersetzt weder die Vertragsverwaltung noch den bestehenden E-Mail-/PDF-Export.

## Ziel

Aus einem erkannten oder manuell angelegten Vertrag heraus soll Kassensturz den passenden offiziellen Kündigungsweg des Anbieters ermitteln, die Fundstellen nachvollziehbar speichern und eine personalisierte Kündigung zur Nutzerprüfung vorbereiten.

## Bestehende Bausteine

- `contracts`: erkannte und manuelle Verträge einschließlich Anbietername, Kundennummer, Anbieter-E-Mail und Anschrift.
- `letters.build_letter`: erstellt bereits fristgerechte, terminierte und außerordentliche Kündigungsschreiben.
- `POST /api/letter`: liefert Schreiben, Betreff, Nachrichtentext und optional einen `mailto:`-Link.
- Vertragsansicht: bietet bereits „Kündigung schreiben“ und editierbare Anbieter-Kontaktdaten.

## MVP-Architektur

### 1. Anbieter-Kontaktrecherche

Eigenständiger Backend-Service, der Anbietername und optional Vertragsart als Suchkontext erhält. Die Recherche priorisiert nachweisbar offizielle Quellen des Anbieters: Kündigungsseite, Kontaktseite, Impressum und Vertrags-/AGB-Seiten.

Das Ergebnis ist kein unstrukturierter KI-Text, sondern ein validiertes Kontaktobjekt mit:
- Kontaktweg: E-Mail, Webformular, Kundenportal oder Post
- Empfängeradresse bzw. URL, soweit gefunden
- Anbieter-/Rechtsträger-Bezeichnung
- Quell-URL und Seitentitel
- Abrufzeitpunkt
- Prüfstatus und Vertrauensstufe
- Hinweise, wenn Quellen widersprüchlich oder nicht eindeutig sind

Es werden keine Kontaktdaten erfunden. Bei fehlendem belastbarem Nachweis wird ausdrücklich „nicht verifiziert“ ausgegeben. Recherche darf nicht versuchen, Login-Schranken, CAPTCHAs oder andere Zugriffskontrollen zu umgehen.

### 2. Persistenz

Kontaktinformationen werden getrennt von den persönlichen Vertragsdaten gespeichert. Recherchebelege bleiben mit Zeitstempel erhalten. Wiederverwendung ist möglich, aber alte Ergebnisse müssen als veraltet markiert und erneut überprüft werden können.

Vorgesehene Tabellen:
- `provider_contacts`: Anbieter-/Kontaktweg-Datensatz und aktueller Prüfstatus.
- `provider_contact_sources`: einzelne Belege (URL, Titel, Abrufzeit, extrahierter relevanter Ausschnitt/Notiz).
- `cancellation_events`: vorbereitete Kündigungen, gewählter Kontaktweg, Zeitpunkt der Übergabe an eine Mail-App und vom Nutzer bestätigter Versandstatus.

Keine Bankzugangsdaten, TANs oder vollständigen Kontobewegungen an einen externen Rechercheanbieter übertragen. Für die Suche genügen Anbietername und nötigenfalls Vertragsart.

### 3. Nutzerablauf

1. Nutzer öffnet einen laufenden Vertrag und tippt auf „Kündigung vorbereiten“.
2. Kassensturz recherchiert im Hintergrund und zeigt Fortschritt/Ergebnis.
3. Nutzer sieht Kontaktweg, Empfänger, Quellen, Zeitstempel und Vertrauensstatus.
4. Nutzer prüft und kann Angaben korrigieren.
5. Kassensturz erstellt den Brieftext mit den vorhandenen Vertragsdaten.
6. Nutzer prüft den vollständigen Text und übergibt ihn an die installierte E-Mail-App. PDF bleibt optional.
7. Die App dokumentiert nur die Übergabe. Der Nutzer kann anschließend ausdrücklich bestätigen, dass er tatsächlich gesendet hat.

### 4. Versand und Status

MVP nutzt `mailto:`/System-Mail-App. Das Öffnen der Mail-App ist keine Versandbestätigung. Statuswerte müssen unterscheiden zwischen:
- Entwurf
- geprüft
- an Mail-App übergeben
- vom Nutzer als versendet bestätigt
- Bestätigung erhalten

Kein automatischer Versand und kein SMTP-Konto im MVP. Eine spätere SMTP-Integration ist optional und erfordert explizite Einrichtung sowie eine letzte Nutzerfreigabe je Kündigung.

## Sicherheit und Datenschutz

- Serverseitige Recherche mit begrenzten Timeouts, Antwortgrößen und erlaubten HTTP(S)-Zielen.
- SSRF-Schutz: keine Loopback-, privaten, Link-Local- oder HA-internen Ziele; DNS-Auflösung und Redirects erneut prüfen.
- Nur HTTPS-Quellen akzeptieren, Redirect-Ziele validieren.
- Keine Zugangsdaten, IBANs, Kontobewegungen oder Kunden-/Vertragsnummern an Suchdienste senden.
- HTML als nicht vertrauenswürdige Eingabe behandeln; kein aktives Skript ausführen.
- Quellen und extrahierte Daten als untrusted content behandeln; Seiteninhalte dürfen keine System-/App-Anweisungen auslösen.
- Rechercheergebnis ist eine Hilfe, keine Rechtsberatung und keine Garantie für wirksame Zustellung.
- Vor Übergabe an Mail-App Empfänger und Inhalt vollständig anzeigen; keine stillen Sendungen.

## Recherche-Strategie

Für die erste lauffähige Ausbaustufe ist ein austauschbarer Recherche-Adapter vorzusehen. Die erste Implementierung soll ohne kostenpflichtige KI-Abhängigkeit auskommen und offizielle Anbieterquellen bevorzugen. Falls eine zuverlässige automatische Websuche nicht verfügbar ist, muss der Nutzer eine offizielle URL oder Kontaktangabe manuell hinterlegen können. Keine Abhängigkeit von fragilen HTML-Selektoren als alleiniger Wahrheitsquelle.

## Akzeptanzkriterien

- Kündigung ist aus einem bestehenden Vertrag erreichbar.
- Anbietername wird automatisch aus dem Vertrag übernommen.
- Jeder gefundene Kontaktweg zeigt Quelle, Zeitpunkt und Prüfstatus.
- Nicht verifizierte oder widersprüchliche Daten werden klar gekennzeichnet.
- Bestehende manuelle Anbieter-E-Mail/Adresse bleiben nutzbar und werden nicht überschrieben, ohne den Nutzer zu fragen.
- Vor Übergabe kann der Nutzer Empfänger, Betreff und kompletten Text prüfen und bearbeiten.
- `mailto:`-Übergabe ist als „an Mail-App übergeben“, nicht als „versendet“, dokumentiert.
- Bestehende Brief-/PDF-Funktion bleibt verfügbar.
- Tests decken Quellenvalidierung, SSRF-Schutz, veraltete Kontakte, Konflikte und Versandstatus ab.

## Geplante Umsetzungsschritte

1. Datenmodell und API-Verträge für Kontaktquellen und Kündigungsereignisse.
2. Recherche-Adapter und sichere URL-/Quellenvalidierung.
3. Vertragsansicht mit Rechercheergebnis und Quellenbelegen.
4. Überarbeiteter Kündigungsdialog mit editierbarer Vorschau und Mail-App-Übergabe.
5. Tests, Migration und Dokumentation.

## Verknüpfung

GitHub Issue: [#14 – Intelligenter Kündigungsassistent mit Anbieterrecherche](https://github.com/uekala/kassensturz/issues/14)


## Implementierter erster Recherche-Schritt

- Die App kann über einen Suchadapter öffentliche Web-Suchergebnisse anhand des Anbieternamens abrufen.
- Die Suche übermittelt ausschließlich den Anbieternamen und allgemeine Begriffe wie „Kündigung“, „Kontakt“ und „Impressum“. Kunden-, Vertrags- und Bankdaten werden nicht in die Suchanfrage aufgenommen.
- Ergebnisse werden als **ungeprüfte Kandidaten** angezeigt. Sie werden erst nach bewusster Aktion als Quellenhinweis gespeichert; sie gelten dadurch ausdrücklich noch nicht als verifizierte Kontaktadresse.
- Es gibt bewusst noch kein automatisches Auslesen oder Übernehmen von E-Mail-Adressen aus beliebigen Webseiten. Der Nutzer kann die Quelle öffnen und die Kontaktdaten prüfen.
- Die Suchanfrage ist auf wenige Treffer, kurze Timeouts und eine begrenzte Antwortgröße beschränkt. HTTP-, Zugangsdaten- und lokale Ziel-URLs werden als Kandidaten verworfen.
- Die Suchfunktion benötigt ausgehenden Internetzugriff der Kassensturz-Instanz. Der Suchanbieter kann seine HTML-Antwort oder Verfügbarkeit ändern; ein Fehler wird als nicht verfügbare Suche gemeldet, nicht als „keine Kontaktdaten“ ausgegeben.

Nächste Schritte: offizielle Domains besser erkennen, eine sichere und begrenzte Inhaltsprüfung offizieller Webseiten ergänzen, anschließend die geprüften Kontaktdaten in die bestehende Kündigungsvorlage und die Mail-App-Übergabe integrieren.


## Ergänzung: SSRF-Vorprüfung für Quellen-URLs

- Neue API: `POST /api/contracts/{key}/cancellation-source-check` mit einer Quellen-URL.
- Akzeptiert werden ausschließlich HTTPS-URLs auf Port 443 ohne Zugangsdaten.
- IP-Literale sowie lokale Hostnamen werden abgewiesen.
- Der Hostname wird aufgelöst und **jede** zurückgelieferte Adresse muss global routbar sein. Gemischte öffentliche/private DNS-Antworten werden vollständig abgelehnt.
- Der Endpunkt ruft die Zielseite ausdrücklich noch nicht ab und meldet daher nur `public_host_only`, niemals `verified`.
- Das ist eine Vorprüfung gegen offensichtliche SSRF-Ziele, aber noch keine vollständige Absicherung eines späteren HTTP-Abrufs: Ein zukünftiger Abruf muss die tatsächlich verwendete Ziel-IP beim Verbindungsaufbau pinnen bzw. Redirects und DNS-Auflösung für jeden Hop erneut prüfen.


## Ergänzung: begrenzter Abruf öffentlicher Seiten

- Neue API: `POST /api/contracts/{key}/cancellation-page-evidence`.
- Die URL durchläuft zuerst dieselbe öffentliche DNS-Vorprüfung. Der HTTP-Client verbindet sich anschließend direkt mit einer der geprüften IP-Adressen (DNS-Pinning); TLS prüft weiterhin den ursprünglichen Hostnamen.
- Es werden ausschließlich HTTPS/Port 443, GET und HTML-Antworten akzeptiert. Zugangsdaten, IP-Literale, lokale/private Ziele und Weiterleitungen werden abgelehnt.
- Timeout und Antwortgröße sind begrenzt; es werden nur Seitentitel und einfache `mailto:`-Hinweise extrahiert.
- Es werden keine Formulare abgesendet, keine Skripte ausgeführt und keine Login-/CAPTCHA-Schranken umgangen.
- Der Rückgabestatus ist stets `page_fetched_unverified`. Seitentitel und E-Mail-Adressen sind untrusted evidence und werden nicht automatisch als Kontakt gespeichert oder in Kündigungen eingesetzt.
- Diese Prüfung bestätigt weder, dass die Domain dem Anbieter gehört, noch dass eine E-Mail-Adresse für Kündigungen zuständig ist. Dafür braucht es einen separaten, nachvollziehbaren Nutzer-Prüfschritt.


## Ergänzung: explizit bestätigte Kontaktübernahme

- Neue API: `POST /api/contracts/{key}/cancellation-contact/confirm`.
- Die Oberfläche zeigt Kontaktfelder erst im Recherchebereich und verlangt eine ausdrückliche Bestätigung, dass der Nutzer die Angaben selbst auf der ausgewählten Quelle geprüft hat.
- Die ausgewählte URL muss zuvor als Recherchequelle für genau diesen Anbieter gespeichert sein.
- Die Übernahme protokolliert die Quelle als `user_confirmed` und den Kontaktstatus als `verified`; das bedeutet hier ausdrücklich: vom Nutzer selbst geprüft und bestätigt, nicht unabhängig durch Kassensturz zertifiziert.
- Vorhandene manuelle Anbieter-E-Mail und Anschrift im Vertrag werden nicht überschrieben. Bei abweichenden Werten antwortet die API mit HTTP 409 und verlangt eine manuelle Konfliktklärung.
- Leere Vertragsfelder werden erst nach Bestätigung mit den eingegebenen Werten befüllt. Dadurch verwendet die vorhandene Kündigungsvorlage die bestätigte E-Mail für ihren `mailto:`-Link, ohne den bestehenden Briefgenerator zu verändern.
- Der Button öffnet weiterhin keine Mail-App und versendet nichts.


### 5. Editierbare E-Mail vor Übergabe

Vor dem Öffnen der System-Mail-App zeigt Kassensturz Empfänger, Betreff und Nachrichtentext als bearbeitbare Felder. Die App übergibt exakt diese vom Nutzer geprüften Werte per `mailto:`. Eine leere oder ungültige Empfängeradresse sowie ein leerer Betreff/Text verhindern die Übergabe. Bei einer Kündigung zu einem bestimmten Datum wird dieses Datum als Notiz im Kündigungsverlauf gespeichert.


### 6. Eingangsbestätigung des Anbieters

Nach eigener Versandbestätigung kann der Nutzer zusätzlich dokumentieren, dass eine Eingangs- oder Kündigungsbestätigung des Anbieters eingegangen ist. Dieser Status wird ausschließlich durch eine ausdrückliche Nutzeraktion gesetzt und mit Zeitstempel gespeichert. Er wird nicht automatisch aus dem E-Mail-Versand abgeleitet und ändert den Vertragsstatus nicht.


### 7. Kündigungsfristen-Monitor (erste Ausbaustufe)

- Die Vertragsübersicht zeigt laufende Ausgabenverträge mit berechenbarer Kündigungsfrist zusätzlich im Abschnitt „Kündigungsfristen“.
- Angezeigt werden überfällige Fristen sowie Fristen innerhalb der nächsten 90 Tage; die Liste ist nach Dringlichkeit sortiert.
- Die Vertragszeile kennzeichnet Fristen bis 45 Tage als kritisch und Fristen zwischen 46 und 90 Tagen als Warnung.
- Die Berechnung nutzt ausschließlich das gespeicherte Vertragsende und die Kündigungsfrist. Fehlen Angaben, wird keine Frist geraten.
- Diese Ausbaustufe zeigt Hinweise innerhalb der App. Es gibt noch keine Hintergrundjobs, Push-/E-Mail-Erinnerungen oder automatische Kündigungen.
