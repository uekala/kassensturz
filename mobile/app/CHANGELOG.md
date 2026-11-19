# Änderungen der Mobile-App

## 0.3.42

- Tilgungsplan: Unter der Restschuld steht, ob seit dem Eintrag alle Raten gebucht sind. Fehlt eine, nennt die App den
  Monat und die Restschuld nach den gebuchten Raten (ab Server 0.3.68).

## 0.3.41

- *Auswertung → Jahresrückblick*: Einnahmen, Ausgaben und Saldo des Jahres, Einnahmen und Ausgaben je Monat,
  Kategorien mit Vergleich zum Vorjahr und die größten Einzelausgaben; Jahre zum Umschalten. Im laufenden Jahr wird
  bis zum selben Tag verglichen (ab Server 0.3.67).

## 0.3.40

- Laden mit Ladecockpit: An einer Supercharger-Abbuchung steht *Laden* mit kWh, Preis je kWh, Ort und Zeit. Die
  Auswertung zeigt für den Monat Ladevorgänge, kWh, Kosten und Preis je kWh (ab Server 0.3.61).

## 0.3.39

- Bankabruf: Fragt die Bank nach einer TAN, einer Freigabe in ihrer App oder dem TAN-Verfahren, erscheint die
  Rückfrage in der Karte *Bankabruf* und lässt sich dort beantworten oder abbrechen (ab Server 0.3.58).

## 0.3.38

- Nur Tests: Die Haushalt-Ansichten (Filter *Ich / Gemeinsam*, Konten mit Besitz, Kinderhandy, Ausgleich) und das
  Eintragen eines Werts sind jetzt durch Widget-Tests abgedeckt.

## 0.3.37

- Konten: Tipp auf Depot, Festgeld, VL oder Immobilie trägt den heutigen Wert ein. Beim Kredit steht *Restschuld
  eintragen* im Tilgungsplan (ab Server 0.3.57).

## 0.3.36

- Belege: PDF öffnet sich jetzt in der App, mit Blättern und Zoomen. Die Datei bleibt dabei in der App und wird
  nicht an eine andere weitergegeben.

## 0.3.35

- Bankabruf: Läuft eine Freigabe bald ab, steht dort *Freigabe für … erneuern*. Die Bank öffnet sich im Browser;
  danach fügst du die Adresse der letzten Seite ein (ab Server 0.3.56).

## 0.3.34

- Kinderhandy schlichter: kein Reiter *Planung*, auf *Heute* der Abschnitt Budgets nur, wenn es welche gibt, und
  unter *Konten* „Dein Geld“ statt Vermögen mit Alltag und Rücklagen.

## 0.3.33

- Umsätze und Auswertung: Umschalter *Alle / Ich / Gemeinsam*, wenn der Haushalt eigene Konten hat (ab Server 0.3.53).

## 0.3.32

- *Konten → Wer hat was geändert?*: das Änderungsprotokoll, neueste zuerst, mit Nachladen (ab Server 0.3.50).

## 0.3.31

- Planung → *Projekte*: was etwas insgesamt gekostet hat, mit Rahmen, Kategorien, Monaten und Buchungen (ab Server
  0.3.49).
- An einer Buchung lässt sich das Projekt wählen.
- Konten: Ein Tipp auf einen Kredit öffnet den Tilgungsplan mit Restschuld, Enddatum, Zinsen und Sondertilgung.

## 0.3.30

- Hinweise auf der Startseite haben Knöpfe: Auffälligkeit *Geprüft*, geplante Ausgabe *Bezahlt* oder *Entfällt*,
  erwarteter Eingang *Ist angekommen* oder *Kommt nicht mehr* (ab Server 0.3.48).
- Neuer Abschnitt *Geplant und erwartet* auf der Startseite; ein Tipp hakt ab.
- *Kann ich mir das leisten?*: Unter der Antwort lässt sich der Betrag als geplante Ausgabe vormerken.
- An einer Ausgabe: *Geld kommt zurück*, etwa nach einer Retoure.
- Der Knopf zum Speichern einer Buchung steht in der Schrift der App.

## 0.3.29

- Handy eines Kindes: Der Hinweis „Kassensturz in Home Assistant aktualisieren“ erscheint dort nicht mehr, das Plus
  zum Anlegen fehlt, und die Startseite zeigt „Dein Geld“ statt der Zahlen des Haushalts. Die Hinweise auf den Seiten
  Planung und Konten passen jetzt zu einem Kind.
- Knöpfe und Meldungen stehen in der Schrift der App statt in der Schrift des Systems.
- Die Gutschrift des Taschengelds heißt nicht mehr „Bankumsatz“; im Hinweis steht, dass Kassensturz sie angelegt hat.

## 0.3.28

- Haushalt: Taschengeld-Konten der Kinder erscheinen bei den Erwachsenen als „Taschengeld … für ein Kind“ und
  zählen nicht zum Vermögen. Ausgaben trägst du wie auf einem Bargeld-Konto ein (ab Server 0.3.35).
- Auf dem Handy eines Kindes zeigt die App nur dessen Taschengeld-Konto; Ändern ist dort ausgeblendet.

## 0.3.27

- Haushalt: Sparziele, die nur dir gehören, sind als „nur für dich“ gekennzeichnet (ab Server 0.3.34).

## 0.3.26

- Haushalt: Eigene Budgets. Unter Planung → Budgets gibt es den Abschnitt „Nur für dich“ mit Budgets, die nur
  Ausgaben von deinen eigenen Konten zählen. Die anderen Budgets gelten für den Haushalt und zählen die
  gemeinsamen Konten (ab Server 0.3.32).

## 0.3.25

- Haushalt: Neue Seite „Geteilte Ausgaben und Ausgleich“, erreichbar von der Kontenseite. Sie zeigt, was zwischen
  dir und den anderen offen ist, die zuletzt geteilten Ausgaben und die eingetragenen Zahlungen.
- Hast du jemandem deinen Anteil überwiesen oder bar gegeben, trägst du die Zahlung dort ein (ab Server 0.3.30).

## 0.3.24

- Haushalt: Eine Ausgabe von deinem eigenen Konto teilst du jetzt direkt in der Buchung mit dem Haushalt und nimmst
  das dort auch zurück (ab Server 0.3.30).

## 0.3.23

- Haushalt: Die Kontenseite zeigt, was aus geteilten Ausgaben zwischen dir und den anderen offen ist (ab Server
  0.3.30). Geteilt und ausgeglichen wird vorerst in Kassensturz in Home Assistant.

## 0.3.22

- Haushalt: Nutzt ihr Kassensturz zu mehreren, zeigt die Kontenseite, wer angemeldet ist und welche Konten nur für
  dich und welche gemeinsam sind (ab Server 0.3.29).

## 0.3.21

- Zuordnen mit Vorschlag: Erkennt der Server einen Hinweis aus deinen bisherigen Zuordnungen, steht die Kategorie
  als Knopf oben. Ein Tipp genügt (ab Server 0.3.27).

## 0.3.20

- Vermögensverlauf auf der Kontenseite: Kurve der letzten Monate und die Veränderung in Euro (ab Server 0.3.26).

## 0.3.19

- „Seit deinem letzten Besuch“ auf der Startseite: wie viele Buchungen neu sind, was sie zusammen ausmachen und die
  drei größten. Bleibt stehen, bis du „Gelesen“ tippst (ab Server 0.3.25).
- Neue Seite „Steuer und Garantien“: Summen je Steuerart und Jahr, laufende und kürzlich abgelaufene Garantien.
- Die Umsatzliste zeigt, an welchen Buchungen ein Beleg hängt.

## 0.3.18

- Zuordnen im Stapel: Unter Planung → Budgets steht, wie viele Buchungen noch keine richtige Kategorie haben. Die App
  zeigt sie nacheinander, die größten zuerst; ein Tipp auf die Kategorie genügt. Ähnliche Buchungen gehen gleich
  mit (ab Server 0.3.24).
- Budgets vorschlagen: aus den Ausgaben der letzten vollen Monate, einzeln oder alle auf einmal zu übernehmen.

## 0.3.17

- Die Startseite zeigt, von wann die Bankdaten sind und wann der nächste Abruf von selbst läuft (ab Server 0.3.23).
- „Jetzt abrufen“ holt neue Buchungen bei den Banken, höchstens alle 30 Minuten. Herunterziehen lädt weiterhin nur
  den Stand vom Server neu.
- Braucht eine Bank Aufmerksamkeit, steht das dabei: Freigabe abgelaufen oder bald fällig, keine Konten verknüpft,
  letzter Abruf fehlgeschlagen.

## 0.3.16

- Das Plus führt nicht mehr in eine Sackgasse: Gibt es noch kein Konto ohne Bankabruf, bietet die App an, eines für
  Bargeld anzulegen, und öffnet danach gleich den neuen Umsatz (ab Server 0.3.21).

## 0.3.15

- Garantie an Käufen: In jeder Ausgabe gibt es „Garantie bis“, mit 2, 3 oder 5 Jahren ab Kauf oder einem eigenen
  Datum (ab Server 0.3.20). Der Server erinnert 30 Tage vor dem Ende.

## 0.3.14

- Buchungen für die Steuererklärung markieren: In jeder Buchung gibt es „Für die Steuererklärung“ mit acht Arten
  (ab Server 0.3.19).
- Belege an Buchungen: Rechnung fotografieren oder ein Foto aus der Galerie wählen, ansehen und wieder entfernen.
  Die Fotos werden verkleinert übertragen und liegen nur auf dem Server. PDF-Belege aus Home Assistant erscheinen
  in der Liste, lassen sich in der App aber noch nicht öffnen.

## 0.3.13

- Neues App-Icon: ein K mit Pfeil nach oben auf Blau statt des grünen Kassenzettels. Ab Android 13 passt es sich
  auf Wunsch den thematischen Symbolen an.

## 0.3.12

- Planung zeigt Sparziele mit Fortschritt und nötiger Monatsrate sowie die Jahreskosten mit der Rücklage, die dafür
  heute da sein sollte (ab Server 0.3.15). Angelegt und geändert wird beides in Kassensturz in Home Assistant.

## 0.3.11

- „Kann ich mir das leisten?“ unter Heute: Betrag eingeben, Antwort mit dem, was bis zum Gehalt bleibt
  (ab Server 0.3.14).
- Auswertung mit Monatsabschluss in Worten: gespart, Sparquote, Abweichung vom Üblichen, Auffälliges.

## 0.3.10

- Vermögen mit allen Teilen: Alltag, Rücklagen, Depots, Immobilien und Kredite (ab Server 0.3.12).
- Sparkonto, Festgeld, VL / Bausparen, Immobilie und Kredit mit Stand, Veränderung und Fälligkeit bzw. Laufzeitende.

## 0.3.9

- Nach einer Kategorieänderung zeigt die App, wie viele weitere Buchungen der Server genauso zugeordnet hat
  (ab Server 0.3.11).

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
