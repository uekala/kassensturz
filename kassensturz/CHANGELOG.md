# Änderungen

## 0.3.19

- Die Mobile-App kann Buchungen für die Steuererklärung markieren und Belege anhängen, ansehen und entfernen
  (ab App 0.3.14).

## 0.3.18

- Neues Zeichen: ein K mit Pfeil nach oben, in App-Icon, Logo, Kopfzeile und als Symbol im Browser-Tab.

## 0.3.17

- Buchungen lassen sich für die Steuererklärung markieren (Handwerkerleistung, haushaltsnahe Dienstleistung,
  Arbeitsmittel, Spende, Versicherung, Krankheitskosten, Kinderbetreuung, Sonstiges).
- Neue Übersicht unter *Einstellungen → Steuer*: Summen je Art und Jahr, Hinweis auf fehlende Belege, Export als CSV.
- Belege an Buchungen: Fotos und PDF bis 10 MB, zehn je Buchung. Der Dateityp wird am Inhalt geprüft.

## 0.3.16

- Neue Sensoren für Home Assistant: Vermögen mit seinen Teilen, Ersparnisse, Schulden, Rücklage für Jahreskosten
  und ein Sensor je Sparziel.
- Kontostand, Konten, Vermögen, Ersparnisse und Schulden führen eine Langzeitstatistik in Home Assistant.
- Ereignisse für Automationen: `kassensturz_neue_buchungen`, `kassensturz_gehalt_eingegangen`,
  `kassensturz_grosse_abbuchung` und `kassensturz_budget_schwelle` (80 % und 100 %, je einmal im Monat).
  Beispiele stehen in der Dokumentation.
- Neue Optionen `events` (Standard: an) und `large_transaction` (Standard: 500 €).

## 0.3.15

- Sparziele: Name, Zielbetrag, optional Datum und Konto. Mit Konto zählt dessen Stand als gespart, mehrere Ziele am
  selben Konto teilen ihn der Reihe nach; ohne Konto pflegst du den Betrag selbst. Mit Datum zeigt Kassensturz die
  nötige Monatsrate. Anlegen und ändern auf der Budgetseite.
- Jahreskosten: Viertel-, halb- und jährliche Verträge werden über ihren Abstand verteilt. Die Budgetseite zeigt, was
  dafür heute zurückgelegt sein sollte und was das im Monat ausmacht.
- Neue Einstellung „Rücklage … von frei verfügbar abziehen“ (Standard aus): zieht diesen Betrag von „frei verfügbar“ ab
  und wirkt damit auch auf „Kann ich mir das leisten?“.
- Der Monatsabschluss in Worten erscheint nur noch für abgeschlossene Monate.
- Mobile-Schnittstelle: Die Übersicht enthält `goals` und `forecast.reserve`; Fähigkeit `goals`.

## 0.3.14

- „Kann ich mir das leisten?“ auf der Übersicht: Betrag eingeben, Kassensturz sagt „Ja“, „Knapp“ oder „Nein“ und
  zeigt, was bis zum Gehalt pro Tag bleibt. Gerechnet wird mit Kontostand, festen Abbuchungen, dem üblichen
  Alltagsverbrauch und der Warnschwelle.
- Monatsabschluss in Worten auf der Budgetseite: gespart, Sparquote, Abweichung vom Schnitt der letzten drei Monate,
  auffällige Kategorien, größte Einzelausgabe.
- In der ersten Woche des Monats kommt der Abschluss des Vormonats als Benachrichtigung (abschaltbar mit
  `notify_month_review`).
- Mobile-Schnittstelle: `GET /api/v1/afford`, die Auswertung enthält den Monatsabschluss; Fähigkeiten `afford` und
  `review`.
- Budgetseite: Die Summenzeile „Überschuss“ steht wieder sauber in einer Zeile; dort erschien fälschlich „FREI VERFÜGBAR“.

## 0.3.13

- Selbsttest des Kontostands: Nach jedem Bankabruf prüft Kassensturz, ob sich der Stand der Bank genau um die neu
  abgerufenen Buchungen geändert hat. Bleibt über mindestens drei Tage ein Rest, erscheint der Hinweis „Kontostand …
  passt nicht“ mit dem Betrag, auch als Benachrichtigung. Vorgemerkte Umsätze gleichen sich beim Buchen aus und lösen
  nichts aus.
- Das betroffene Konto trägt die Marke „passt nicht“; im Konto lässt sich der Hinweis nach der Prüfung ausblenden.

## 0.3.12

- Neue Kontoarten: Sparkonto, Festgeld, VL / Bausparen, Immobilie und Kredit. Festgeld, VL, Immobilie und Kredit
  führst du wie das Depot über eingetragene Werte, jeder Eintrag bleibt erhalten. Alle zählen zum Vermögen, aber nicht
  zu „frei verfügbar“ und zur Prognose.
- Kredite: Du trägst die Restschuld ein, sie zählt im Vermögen als Minus. Die Kontenseite zeigt, um wie viel sie seit
  dem letzten Eintrag gesunken ist.
- Festgeld und Kredit mit Datum („Fällig am“, „Läuft bis“); 30 Tage vorher erscheint ein Hinweis, auch als
  Benachrichtigung.
- Vermögen nach Alltag, Rücklagen, Depots, Immobilien und Krediten, dazu eine Verlaufslinie über bis zu zwölf Monate.
  Der Verlauf beginnt erst, wenn für alle Konten Daten vorliegen, damit ein neu erfasstes Konto nicht wie ein Sprung
  aussieht.

## 0.3.11

- Kassensturz lernt aus Korrekturen: Änderst du bei einer Buchung die Kategorie, merkt es sich den Empfänger und ordnet
  alle ähnlichen Buchungen genauso zu, alte wie künftige. Eine neuere Korrektur ersetzt die ältere, Einnahmen und
  Ausgaben werden getrennt gelernt. Eigene Regeln haben Vorrang. Zahlungsdienste wie PayPal oder Klarna als Empfänger
  werden nicht gelernt, weil dahinter viele Händler stehen.
- Einstellungen → „Gelernt“ zeigt die gemerkten Empfänger; „Vergessen“ nimmt einen Eintrag zurück.
- Gilt auch für Änderungen aus der Mobile-App (Fähigkeit `categories.learn`); mit `learn: false` bleibt es bei der
  einen Buchung.

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
