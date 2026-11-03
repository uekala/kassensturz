# Kassensturz

Kassensturz ist ein Haushaltsbuch für Home Assistant. Es sammelt die Umsätze deiner Konten, ordnet sie Kategorien zu,
erkennt Verträge und Abos und rechnet aus, wie viel bis zum nächsten Gehalt noch frei ist. Alle Daten bleiben auf deinem
Home-Assistant-Gerät.

## Erste Schritte

1. Add-on starten und **Kassensturz** in der Seitenleiste öffnen.
2. Entweder eine Kontoauszug-Datei importieren, einen Bankzugang per FinTS einrichten oder erst einmal die Beispieldaten laden.
3. Für Konten ohne Saldo in der Datei (zum Beispiel Kreditkarten) einmal den aktuellen Kontostand eintragen.

Nach etwa drei Monaten Umsätzen erkennt Kassensturz die meisten Verträge von selbst.

## Was die Übersicht zeigt

Oben steht die Rechnung, die dem Add-on den Namen gibt: Kontostand heute, minus feste Abbuchungen bis zum nächsten
Gehalt, ergibt den Betrag, der für den Alltag frei ist. Darunter der Verlauf der letzten 30 Tage mit Prognose für die nächsten
45 Tage. Die Prognose rechnet erkannte Verträge zum jeweiligen Termin ein und für alles andere deine typischen Alltagsausgaben
der letzten drei Monate.

In die Summe fließen alle Konten ein, bei denen „Zählt zum Kontostand und zur Prognose“ aktiv ist. Tagesgeldkonten sind
standardmäßig ausgenommen.

## Bankabruf per FinTS

FinTS (früher HBCI) ist die Schnittstelle, über die auch Programme wie StarMoney oder Hibiscus Umsätze abrufen.
Sparkassen, Volks- und Raiffeisenbanken, ING, DKB, comdirect und viele weitere bieten sie an.

**Produkt-ID:** Seit 2019 akzeptieren Banken nur registrierte Programme. Die Registrierung bei der Deutschen Kreditwirtschaft
ist kostenlos (Formular auf [fints.org](https://www.fints.org/de/hersteller/produktregistrierung)); die Zuteilung kann bis zu
zwei Wochen dauern. Die erhaltene ID trägst du in den Add-on-Einstellungen unter `fints_product_id` ein.

**Bankzugang anlegen:** Unter *Konten → Bankzugang hinzufügen*. Du brauchst die Bankleitzahl (Stelle 5 bis 12 deiner IBAN),
deinen Anmeldenamen aus dem Online-Banking und die FinTS-Serveradresse deiner Bank. Für ING, DKB, comdirect und die
Volksbanken ist die Adresse vorbelegt. Sparkassen nennen sie auf ihrer Website unter „HBCI“ oder „FinTS“.

**TAN:** Beim ersten Abruf fragt Kassensturz nach deinem TAN-Verfahren. Bei App-Verfahren (pushTAN, SecureGo plus,
Banking to go, DKB-App, photoTAN-Push) bestätigst du einfach in der App; Kassensturz wartet darauf. chipTAN mit Flickercode
und photoTAN-Grafiken werden direkt angezeigt.

**Automatischer Abruf:** Wenn du beim Abruf „PIN speichern“ wählst, ruft Kassensturz täglich zur eingestellten Uhrzeit ab.
Die PIN liegt dann in `/data/secrets.json` auf dem Gerät – nicht verschlüsselt, aber von Home-Assistant-Backups ausgenommen.
Die meisten Banken verlangen alle 90 bis 180 Tage eine neue TAN-Freigabe; dann meldet sich Kassensturz per Benachrichtigung
und du startest den Abruf einmal von Hand.

## Datei-Import

Für Konten ohne FinTS – N26, Revolut, PayPal, American Express, Klarna, Advanzia – und als Alternative für alle anderen.
Erkannt werden:

| Bank | Format | Wo zu finden (meist) |
|---|---|---|
| Sparkasse | CSV-CAMT, CSV-MT940, CAMT (XML/ZIP), MT940 | Umsätze → Export |
| Volksbank / Raiffeisenbank | CSV | Umsätze → Export |
| ING | CSV | Umsätze → Download |
| DKB | CSV | Umsätze → Export |
| comdirect | CSV | Umsätze → Export |
| N26 | CSV | Web-App → Downloads |
| Revolut | CSV | Konto → Kontoauszug → Excel/CSV |
| PayPal | CSV | Aktivitäten → Kontoauszüge → Benutzerdefiniert |
| American Express | CSV | Umsätze → Herunterladen |
| alle anderen | CSV mit Datum und Betrag | Spalten lassen sich im Import zuordnen |

Kassensturz merkt sich die Spaltenzuordnung je Dateiformat. Überlappende Zeiträume sind kein Problem: Pro Tag und Betrag wird nur
übernommen, was noch fehlt – auch wenn dasselbe Konto mal per Datei und mal per FinTS gefüllt wird.

Bei Kreditkarten stehen Ausgaben in manchen Exporten ohne Minus. Kassensturz weist darauf hin; die Option
„Vorzeichen umkehren“ steht in der Spaltenzuordnung.

## Umbuchungen und doppelte Ausgaben

Ein Einkauf über PayPal taucht zweimal auf: als Abbuchung „PayPal Europe“ auf dem Girokonto und als Zahlung an den Händler im
PayPal-Konto. Kassensturz wertet die Abbuchung als Umbuchung, sobald du das PayPal-Konto ebenfalls importierst. Gleiches gilt
für Kreditkartenabrechnungen, Klarna und Überweisungen zwischen eigenen Konten (erkannt an der IBAN). Steuern lässt sich das je
Konto über das Feld „Abbuchungen auf anderen Konten, die dieses Konto ausgleichen“.

## Kategorien und Regeln

Gut 500 Suchbegriffe für deutsche Händler, Versicherer, Energie- und Telefonanbieter sind eingebaut. Wenn du bei einer Buchung
die Kategorie änderst, schlägt Kassensturz eine Regel vor („Auch künftig so zuordnen, wenn … vorkommt“) und zeigt, wie viele
Buchungen sie betrifft. Eigene Regeln gehen den eingebauten vor und stehen unter *Einstellungen*. Buchungen lassen sich auf
mehrere Kategorien aufteilen.

## Verträge und Kündigungen

Wiederkehrende Zahlungen werden über Gläubiger-ID und Mandatsreferenz erkannt, sonst über Name und Rhythmus (wöchentlich bis
jährlich). Steigt der Betrag, erscheint ein Hinweis mit den Mehrkosten pro Jahr. Zu jedem Vertrag kannst du Kundennummer,
Vertragsende und Kündigungsfrist hinterlegen; Kassensturz erinnert dann rechtzeitig vor Fristende.

„Kündigung schreiben“ erzeugt ein Kündigungsschreiben (fristgerecht, zu einem Datum oder als Sonderkündigung bei
Preiserhöhung) inklusive Widerruf des SEPA-Mandats. Es lässt sich als E-Mail öffnen, kopieren oder als PDF drucken.
Dafür einmal unter *Einstellungen* Name und Anschrift eintragen. Die Schreiben sind Vorlagen, keine Rechtsberatung.

## Home Assistant

Mit `sensors: true` legt Kassensturz diese Sensoren an und aktualisiert sie alle 15 Minuten sowie nach jedem Import:

| Sensor | Inhalt |
|---|---|
| `sensor.kassensturz_kontostand` | Summe der Konten in der Prognose, Einzelstände als Attribut |
| `sensor.kassensturz_frei_verfuegbar` | frei bis zum nächsten Gehalt, Attribute `bis` und `pro_tag` |
| `sensor.kassensturz_prognose_monatsende` | erwarteter Stand am Monatsende |
| `sensor.kassensturz_tiefster_stand` | tiefster erwarteter Stand der nächsten 45 Tage, Attribut `datum` |
| `sensor.kassensturz_fixkosten_monat` | Summe aller laufenden Verträge pro Monat |
| `sensor.kassensturz_ausgaben_monat` | Ausgaben im laufenden Monat |
| `sensor.kassensturz_naechste_zahlung` | nächste feste Abbuchung, Attribute `empfaenger` und `datum` |
| `sensor.kassensturz_konto_*` | ein Sensor je Konto |
| `sensor.kassensturz_budget_*` | Restbudget je Kategorie mit Budget |

Benachrichtigungen gibt es, wenn die Prognose unter `warn_threshold` fällt, ein Vertrag teurer wird, eine Kündigungsfrist naht,
ein Budget überschritten ist oder der tägliche Abruf eine TAN braucht. Ohne `notify_service` landen sie als persistente
Benachrichtigung in Home Assistant, mit zum Beispiel `notify.mobile_app_pixel` direkt auf dem Handy.

Beispiel für eine Dashboard-Karte:

```yaml
type: entities
title: Finanzen
entities:
  - entity: sensor.kassensturz_frei_verfuegbar
    name: Frei bis zum Gehalt
  - entity: sensor.kassensturz_kontostand
    name: Kontostand
  - entity: sensor.kassensturz_prognose_monatsende
    name: Prognose Monatsende
  - entity: sensor.kassensturz_naechste_zahlung
    name: Nächste Abbuchung
```

Die Sensoren werden über die API gesetzt und haben deshalb keine eindeutige ID; Name und Symbol lassen sich in der
Oberfläche nicht ändern. Nach einem Neustart von Home Assistant sind sie spätestens nach 15 Minuten wieder da.

## Optionen

| Option | Bedeutung |
|---|---|
| `fints_product_id` | Produkt-ID für den Bankabruf |
| `sync_time` | Uhrzeit des täglichen Abrufs (HH:MM) |
| `sensors` | Sensoren in Home Assistant anlegen |
| `notify_service` | z. B. `notify.mobile_app_pixel`, leer für persistente Benachrichtigungen |
| `warn_threshold` | Warnung, wenn die Prognose unter diesen Betrag in Euro fällt |

## Datenschutz

- Die Oberfläche ist nur über Home Assistant (Ingress) erreichbar, es wird kein Port nach außen geöffnet.
- Es gibt keine Verbindungen zu Diensten außer zu deiner Bank (FinTS) und zu Home Assistant selbst. Die Schrift ist
  eingebettet, es werden keine externen Ressourcen geladen.
- Daten liegen in `/data/kassensturz.sqlite` und sind Teil der Home-Assistant-Backups; gespeicherte PINs nicht.
- *Einstellungen → Alle Buchungen als CSV* exportiert alles in einer Datei.
