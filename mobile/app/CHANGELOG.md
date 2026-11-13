# Änderungen der Mobile-App

## 0.3.8

- Update-Hinweis: Die App fragt beim Start bei GitHub nach einer neueren Version und bietet sie mit „Update laden“
  an. Abgerufen wird nur die öffentliche Release-Liste, ohne Zugangsdaten. Abschaltbar unter Einstellungen → App.
- App-Sperre: Auf Wunsch fragt die App beim Öffnen und nach einer Minute im Hintergrund nach Fingerabdruck, Gesicht
  oder der Gerätesperre. Einschalten unter Einstellungen → App; Ein- und Ausschalten verlangt selbst die Bestätigung.

## 0.3.7

- Verträge antippen (ab Server 0.3.10): Details, „Als Vertrag bestätigen“, „Neuen Preis übernehmen“, „Als gekündigt
  markieren“ und „Ist kein Vertrag – ausblenden“.
- Kündigungsschreiben in der App: fristgerecht, zum Termin oder als Sonderkündigung nach einer Preiserhöhung. Text,
  Betreff und E-Mail-Adresse des Anbieters lassen sich kopieren.
- Verträge mit Preiserhöhung tragen die Marke „teurer“, neu erkannte die Marke „neu“.

## 0.3.6

- Budgets in der App bearbeiten (ab Server 0.3.9): unter Planung auf ein Budget tippen, um den Betrag zu ändern oder
  es zu entfernen; „Budget anlegen“ für eine Ausgabenkategorie ohne Budget.

## 0.3.5

- Konten zeigen das Vermögen statt eines Gesamtsaldos, aufgeteilt in Alltag, Rücklagen und Depots.
- Depots mit Stand und Veränderung seit dem letzten eingetragenen Wert (ab Server 0.3.8).
- Kontoarten auf Deutsch („Girokonto“ statt „giro“).

## 0.3.4

- Neue Auswertung, erreichbar von „Heute“ (ab Server 0.3.3): Ausgaben eines Monats nach Kategorie mit Anteilen,
  Einnahmen und Ausgaben der letzten zwölf Monate, Verlauf des Kontostands mit Prognose und tiefstem erwarteten Stand.

## 0.3.3

- Umsätze durchsuchen: Empfänger, Verwendungszweck und Notiz (ab Server 0.3.2).
- Umsätze nach Einnahmen oder Ausgaben einschränken; Umbuchungen zwischen eigenen Konten zählen dabei nicht mit.

## 0.3.2

- Dunkelmodus: Die App folgt der Einstellung des Handys.
- Schriften eingebunden: Inter für Text, Space Grotesk für Überschriften und große Beträge.
- Umsatz anlegen und ändern neu aufgebaut: großer Betrag, Konto und Datum nebeneinander, breiter Speichern-Knopf.

## 0.3.1

- Aufgeräumt: Beispieldaten sowie die frühere Konten- und Budgetablage auf dem Gerät sind entfernt. Die App zeigt
  ausschließlich Daten des gekoppelten Servers. Dateien aus Versionen vor 0.2.0 bleiben unberührt und ungelesen.
- Kleinere Installationsdatei: nur noch für 64-Bit-ARM gebaut, ohne die nicht mehr benötigte Datenbankbibliothek.
- Strengere Codeprüfung mit `flutter_lints`.

## 0.3.0

- Neues Erscheinungsbild: weiße Flächen, dunkle Schrift, ein kräftiges Blau; Umrisse statt getönter Karten,
  große Beträge, dicke Balken für Budgets.
- Neue Aufteilung: vier Bereiche „Heute“, „Umsätze“, „Planung“ (Budgets und Verträge) und „Konten“.
  Die Einstellungen liegen hinter dem Symbol oben rechts.
- Der Plus-Knopf in der Leiste legt von jedem Bereich aus einen Umsatz an.
- Der Verbindungsstatus ist ein Punkt am Einstellungssymbol; ein Hinweis erscheint nur noch bei Problemen.
- Umsätze sind nach Tagen gegliedert.

## 0.2.0

- Alle Daten kommen vom gekoppelten Kassensturz-Server (ab Server 0.3.0): Übersicht, Konten, Budgets, Buchungen,
  Kategorien und Verträge. Ohne Verbindung zeigt die installierte App keine Beispiel- oder Gerätedaten mehr.
- Umsätze von Hand anlegen, ändern und löschen – auf Konten ohne Bankabruf. Bei Bankumsätzen lassen sich
  Kategorie und Notiz ändern.
- Kein doppeltes Buchen: Ein erneutes Speichern nach einem Verbindungsabbruch legt den Umsatz nicht zweimal an.
- Buchungsliste nach Konto und Kategorie filtern; Verträge als eigene Ansicht unter „Mehr“.
- Serververwaltung: Verbindungsstatus, letzte erfolgreiche Synchronisierung, Verbindung testen, Trennen.
- Verständliche Fehlermeldungen je Ursache (kein Tailscale, Zeitüberschreitung, Zertifikat, Server zu alt).
- Beim Zurückkehren in die App werden die Daten aktualisiert.
- Anmeldung: Bricht die Verbindung beim Erneuern ab, wiederholt die App den Versuch genau einmal sofort.
- Android: Internet-Berechtigung ausdrücklich gesetzt; App-Daten von Sicherung und Geräteumzug ausgeschlossen.

## 0.1.0

- Erste Testversion: Kopplung per QR-Code, Übersicht und Buchungen vom Server, Beispieldaten ohne Verbindung.
