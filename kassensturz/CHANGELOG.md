# Änderungen

## 0.3.10

- Verträge aus der Mobile-App ändern: `PATCH /api/v1/contracts/{schlüssel}` mit `status` (erkannt, bestätigt,
  gekündigt, ausgeblendet) oder `price_change_ack: true`. Beim Status „gekündigt“ wird das Datum gesetzt.
- Kündigungsschreiben für die App: `POST /api/v1/contracts/{schlüssel}/letter` mit `mode` (`ordentlich`, `sonder`,
  `termin` mit Datum). Es ist dasselbe Schreiben wie in der Web-Oberfläche, mit Name und Anschrift aus den
  Einstellungen; gespeichert oder verschickt wird nichts.
- Die Vertragsliste der Mobile-Schnittstelle enthält die Preisänderung und ob der Vertrag von Hand angelegt ist,
  weiterhin ohne Kundennummer, Anschrift und Notizen. Neue Fähigkeit `contracts.write`, höchstens 30 Änderungen pro
  Minute.

## 0.3.9

- Budgets aus der Mobile-App setzen, ändern und entfernen: `PUT /api/v1/budgets/{kategorie}` mit `limit_cents`
  (0,01 € bis 100.000 €, `null` entfernt). Nur für Ausgabenkategorien, nur mit gekoppeltem Gerät, höchstens 60
  Änderungen pro Minute. Neue Fähigkeit `budgets.write`.
- Kategorienliste der Mobile-Schnittstelle enthält das Budget je Kategorie.

## 0.3.8

- Depot als Kontoart: Du trägst den Gesamtwert ein, jeder Eintrag bleibt erhalten (einer je Tag). Die Kontenseite zeigt
  Wert, Stand und Veränderung seit dem letzten Eintrag. Depots zählen nicht zu „frei verfügbar“ und zur Prognose.
- Kontenseite mit „Vermögen“: alle Konten mit bekanntem Stand, aufgeteilt in Alltag, Rücklagen und Depots.
- Neue Konten werden hinten einsortiert; Tagesgeld und Depot starten außerhalb der Prognose.
- Mobile-Schnittstelle: Konten melden zusätzlich `in_forecast` und beim Depot den vorherigen Wert.

## 0.3.7

- Mitteilung bei neuen Buchungen: Was der tägliche Abruf (FinTS, Open Banking) oder der Eingangsordner neu bringt,
  meldet Kassensturz über Home Assistant, eine Meldung je Abruf mit bis zu fünf Buchungen. Selbst importierte oder
  angelegte Buchungen werden nicht gemeldet, ebenso wenig der Bestand beim ersten Start. Abschaltbar mit
  `notify_new_transactions`.
- Beispieldaten: Die Netflix-Preiserhöhung wird jetzt an jedem Tag des Monats erkannt, bisher nur bis zum 11.

## 0.3.6

- Umzug in eine andere Installation, etwa von der lokalen App zur Installation über GitHub: *Einstellungen → Daten →
  Datenbank für Umzug* lädt eine vollständige Kopie herunter. Eine neue Installation ohne Konten und Umsätze übernimmt
  sie beim Start aus dem Eingangsordner (`umzug/kassensturz-umzug.sqlite`) und löscht die Datei danach. Eine
  Installation mit Daten wird nie überschrieben. PINs und der Enable-Banking-Schlüssel ziehen nicht mit um.

## 0.3.5

- Web-Oberfläche im selben Stil wie die Mobile-App („Klar“): Weiß, Tinte, ein Blau, keine grauen Flächen und keine
  Schatten. Schriften Inter und Space Grotesk statt Archivo. Hell und dunkel. Aufbau und Verhalten sind unverändert.
- Reiterleiste am Handy als flache Leiste am unteren Rand.

## 0.3.4

- Beim Beenden meldet die App jetzt den Rückgabewert 0. Bisher schloss sie zwar sauber, endete aber mit 143, und
  Home Assistant schrieb bei jedem Stopp „SIGTERM nicht behandelt“ ins Protokoll.
- Web-Oberfläche am Handy: Kopfzeile mit Schriftzug und Einstellungen ist wieder sichtbar, die Reiterleiste sitzt
  unten. Bisher lag die Leiste oben über der Kopfzeile, die Einstellungen waren am Handy nicht erreichbar.
  Der Zugang zu den Einstellungen ist dort jetzt beschriftet.
- Wird ein Konto gelöscht, verschwinden jetzt auch seine erkannten Verträge, selbst wenn sie bestätigt oder mit
  einer Notiz versehen waren. Bisher blieben sie ohne Konto stehen und ließen sich nicht entfernen. Von Hand
  angelegte Verträge bleiben erhalten.
- Bankvorlage für 1822direkt (eigene BLZ 50050222 für FinTS).
- Übersicht: kein doppelter Punkt mehr hinter dem Gehaltsdatum.

## 0.3.3

- Mobile App: neue Schnittstelle für die Auswertung – Ausgaben eines Monats nach Kategorie, Einnahmen und Ausgaben
  der letzten zwölf Monate und der Verlauf des Kontostands mit Prognose. Es verlassen nur Namen und Beträge den Server.

## 0.3.2

- Mobile App: Umsätze lassen sich durchsuchen (Empfänger, Verwendungszweck, Notiz) und auf Einnahmen oder Ausgaben
  einschränken. Umbuchungen zwischen eigenen Konten zählen dabei wie in der Web-Oberfläche nicht mit.

## 0.3.1

- **Überwachung:** Antwortet die App nicht mehr oder steht der Zeitplan für Abruf und Eingangsordner länger als
  15 Minuten, startet Home Assistant sie neu (Watchdog über `/healthz`, nur lokal erreichbar, ohne Finanzdaten).
- **Eigene Sicherungskopien:** Einmal am Tag und vor dem ersten Start einer neuen Version legt die App eine in sich
  stimmige Kopie der Datenbank in `/data/backups` ab. Aufbewahrt werden die letzten 7 Tageskopien und die letzten
  3 Kopien vor einem Versionswechsel.
- **Konsistente Home-Assistant-Backups:** Home Assistant hält die App während einer Sicherung kurz an (`backup: cold`).
  Vorher wurde die SQLite-Datenbank im laufenden Betrieb gesichert; im WAL-Modus konnten Datenbankdatei und
  Schreibprotokoll dabei zu unterschiedlichen Zeitpunkten kopiert werden.
- Beim Beenden schreibt die App das Schreibprotokoll in die Datenbank und schließt sie. Offene Anfragen bekommen dafür
  höchstens 5 Sekunden, weniger als die 10 Sekunden, nach denen Home Assistant eine App hart beendet.
- Getestet mit Python 3.15, der Version im Add-on-Image.

## 0.3.0

- Mobile App: Konten, Kategorien und Verträge direkt vom Server; die App führt keine eigenen Bestände mehr.
- Mobile App: Umsätze von Hand anlegen, ändern und löschen – auf Konten ohne Bankabruf (zum Beispiel Bargeld).
  Bei Bankumsätzen lassen sich Kategorie und Notiz ändern; löschen lassen sie sich nicht.
- Kein doppeltes Buchen: Wird eine Anfrage nach einem Verbindungsabbruch wiederholt, legt der Server den Umsatz
  nur einmal an. Ein späterer Datei-Import desselben Umsatzes erkennt die von Hand angelegte Buchung als vorhanden.
- Mobile App: Geht die Antwort beim Erneuern der Anmeldung durch einen Verbindungsabbruch verloren, darf das Gerät
  es genau einmal wiederholen – höchstens zehn Minuten nach dem ersten Versuch – und bleibt gekoppelt.
- Sicherheit: Jede weitere Wiederverwendung eines ersetzten Anmelde-Tokens sperrt das Gerät und entwertet alle
  seine Tokens. Das gilt auch, wenn ein durch die Wiederholung ungültig gewordenes Token vorgelegt wird. Ein
  gesperrtes Gerät wird in den Einstellungen unter „Mobile Geräte“ neu gekoppelt.
- Abgelaufene Anmelde-Tokens werden einen Tag nach Ablauf aus der Datenbank gelöscht.
- Mobile App: verständliche Fehlermeldung, wenn die Anfrage aus einem nicht freigegebenen Netz kommt.
- Datenbank: eine zusätzliche Spalte für die Anfragekennung; bestehende Buchungen bleiben unverändert.
- Einstellungen der App: Beschreibungen für die drei Optionen der Mobile-Verbindung ergänzt.

## 0.2.1

- Kündigungsassistent: Anbieter-Kontakt suchen und nach Prüfung übernehmen, Kündigungs-E-Mail vor dem Versand
  bearbeiten, Versand und Anbieterbestätigung ausdrücklich bestätigen, Verlauf je Vertrag, Kündigung abbrechen.
- Kündigungsfristen: anstehende Fristen in der Vertragsübersicht, gestaffelte Erinnerungen in Home Assistant mit
  einstellbaren Abständen, Erinnerung an nicht bestätigte Kündigungen und zentrale Liste offener Kündigungen.
- Mobile App koppeln: Einmal-QR-Code in den Einstellungen für die konfigurierte HTTPS-Adresse, Geräteverwaltung und
  lesender Zugriff auf Übersicht und Buchungen.
- CSV-Export enthält aufgeteilte Buchungen und ist gegen Tabellen-Formeln abgesichert.
- Vertragserkennung fasst Zahlungen vom selben Tag nicht mehr zusammen; exakte Zuordnung beim Import korrigiert.
- Oberfläche überarbeitet: neues Farbschema und besseres Layout auf breiten Bildschirmen.
- Sicherheit: Upload- und ZIP-Grenzen, Secret-Dateien mit eingeschränkten Rechten, Prüfung des Open-Banking-Rückrufs.

## 0.2.0

- Open Banking über Enable Banking: Banken ohne FinTS (zum Beispiel N26) automatisch abrufen, täglich und von Hand,
  mit Erinnerung vor Ablauf der Freigabe und Erneuern ohne neue Konten.
- Eingangsordner `/share/kassensturz`: Kontoauszug-Dateien werden automatisch erkannt, dem richtigen Konto zugeordnet und
  importiert; unklare Dateien lassen sich in der Oberfläche zuordnen.
- „Bank verbinden“ führt jetzt zur Wahl zwischen Open Banking und FinTS.
- Begriffe an Home Assistant angepasst (App statt Add-on).

## 0.1.0

- Erste Version: FinTS-Abruf mit TAN-Dialog, Datei-Import (CSV, CAMT, MT940), Kategorien und Regeln, Aufteilen von
  Buchungen, Vertragserkennung, Budgets, Prognose, Kündigungsschreiben, Sensoren und Benachrichtigungen in Home Assistant.
