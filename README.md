# Kassensturz

Haushaltsbuch als Home-Assistant-Add-on: Umsätze per FinTS oder Datei-Import, automatische Kategorien, Vertrags- und
Abo-Erkennung mit Preiserhöhungs-Hinweis, Monatsbudgets, Kontostand-Prognose bis zum nächsten Gehalt und
Kündigungsschreiben auf Knopfdruck. Läuft vollständig lokal – ohne Cloud, ohne Werbung, ohne Vertragswechsel-Angebote.

![Kassensturz](kassensturz/logo.png)

## Installation

1. In Home Assistant *Einstellungen → Add-ons → Add-on Store* öffnen (in neueren Versionen „Apps“).
2. Oben rechts im Menü *Repositories* wählen und `https://github.com/uekala/kassensturz` hinzufügen.
3. **Kassensturz** installieren und starten. Das Add-on wird auf dem Gerät gebaut; das dauert beim ersten Mal einige Minuten.
4. Über die Seitenleiste öffnen.

Ohne GitHub geht es auch lokal: den Ordner `kassensturz/` per Samba oder SSH nach `/addons/kassensturz` kopieren, im
Add-on Store *Nach Updates suchen* und unter „Lokale Add-ons“ installieren.

Für den automatischen Bankabruf braucht es eine kostenlose FinTS-Produkt-ID. Alles Weitere steht in der
[Anleitung](kassensturz/DOCS.md).

## Was anders ist als bei den bekannten Finanz-Apps

- **Lokal:** Daten bleiben auf dem Home-Assistant-Gerät, Bankzugang direkt per FinTS ohne Zwischenanbieter.
- **Frei bis zum Gehalt:** Statt nur Kontostand zeigt die Übersicht die Rechnung Kontostand − feste Abbuchungen bis zum
  nächsten Gehaltseingang, dazu eine Tagesprognose.
- **Keine Doppelzählung:** PayPal-, Klarna- und Kreditkartenumsätze werden mit den Abbuchungen auf dem Girokonto verrechnet.
- **Nachvollziehbare Kategorien:** Jede Zuordnung zeigt, woher sie kommt; Korrekturen werden auf Wunsch zur Regel, mit
  Vorschau, wie viele Buchungen sie betrifft. Buchungen lassen sich aufteilen.
- **Verträge mit Gedächtnis:** Erkennung über Gläubiger-ID und Mandat, Hinweis bei Preiserhöhungen mit Mehrkosten pro Jahr,
  Erinnerung vor Ablauf der Kündigungsfrist, Kündigungsschreiben inklusive Mandatswiderruf.
- **Home Assistant:** Sensoren für Kontostand, frei verfügbaren Betrag, Prognose, Fixkosten und Budgets; Benachrichtigungen
  aufs Handy.
- **Offen:** Export aller Buchungen als CSV, kein Datensilo.

## Unterstützte Banken

FinTS: Sparkassen, Volks- und Raiffeisenbanken, ING, DKB, comdirect und alle weiteren Banken mit FinTS-PIN/TAN.
Datei-Import: zusätzlich N26, Revolut, PayPal, American Express, Klarna, Advanzia sowie CAMT.052/.053 und MT940.

## Entwicklung

```bash
cd kassensturz/app
pip install -r requirements.txt
KASSENSTURZ_DEV=1 KASSENSTURZ_DATA=/tmp/kassensturz python -m kassensturz
# Oberfläche: http://localhost:8099
```

Tests:

```bash
pip install pytest httpx
pytest tests
# optional mit der Test-Bank aus dem Quellcode von python-fints:
FINTS_TESTS_DIR=/pfad/zu/python-fints/tests pytest tests/test_fints_mock.py
```

Aufbau: FastAPI und SQLite im Backend (`kassensturz/app/kassensturz`), eine Oberfläche ohne Build-Schritt in `static/`.
FinTS übernimmt [python-fints](https://github.com/raphaelm/python-fints). Die Schrift Archivo steht unter der SIL Open Font License.
