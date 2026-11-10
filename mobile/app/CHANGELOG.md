# Änderungen der Mobile-App

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
