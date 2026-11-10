# Änderungen

## 0.2.2

- **Konsistente Home-Assistant-Backups:** Home Assistant hält die App während einer Sicherung kurz an (`backup: cold`).
  Vorher wurde die SQLite-Datenbank im laufenden Betrieb gesichert; im WAL-Modus konnten Datenbankdatei und
  Schreibprotokoll dabei zu unterschiedlichen Zeitpunkten kopiert werden.
- Beim Beenden schreibt die App das Schreibprotokoll in die Datenbank und schließt sie. Offene Anfragen bekommen dafür
  höchstens 5 Sekunden, weniger als die 10 Sekunden, nach denen Home Assistant eine App hart beendet.
- Getestet mit Python 3.15, der Version im Add-on-Image.

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
