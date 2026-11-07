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
