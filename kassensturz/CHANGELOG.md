# Änderungen

## 0.3.61

- Laden mit Ladecockpit: Kassensturz liest Ladevorgänge aus dem Sensor von Ladecockpit und aus dessen CSV-Export und
  hängt kWh, Preis je kWh und Ort an die passende Abbuchung der Bank. Neue Buchungen entstehen dabei nicht.
- Übersicht: Abschnitt *Laden* mit diesem und dem vorigen Monat, unter *Alle Monate* jeder Monat mit kWh, Kosten und
  Preis je kWh, dazu Ladevorgänge ohne passende Abbuchung.
- Datenbank: neue Tabelle für Ladevorgänge (Schema 15); bestehende Daten bleiben unverändert.

## 0.3.60

- FinTS: Lehnt die Bank die Anmeldung ab (etwa Code 9900, falsche PIN, Zugang gesperrt), ruft Kassensturz für
  diesen Bankzugang nicht mehr von selbst ab, weder täglich noch über die App. Bisher hätte der tägliche Abruf es mit
  der gespeicherten PIN jeden Tag erneut versucht, und nach wenigen Fehlversuchen sperrt die Bank den Zugang.
  Weiter geht es mit einem Abruf in Home Assistant mit eingegebener PIN, die gespeichert wird, oder nach einer
  Änderung von Anmeldename, Bankleitzahl oder Server. Unter *Konten* steht dann „automatischer Abruf angehalten“.
- Code 9900 bekommt eine eigene Meldung: Die Produkt-ID hat die Bank dann angenommen, abgelehnt hat sie
  Anmeldename oder PIN.

## 0.3.59

- Bank verbinden: Der Hinweis unter der Bankliste nannte Advanzia als Beispiel für Luxemburg. Enable Banking führt
  Advanzia dort nicht; der Hinweis und die Dokumentation verweisen jetzt auf den Datei-Import.

## 0.3.58

- App (ab Version 0.3.39): Verlangt eine FinTS-Bank beim Abruf aus der App eine TAN, eine Freigabe in der
  Banking-App oder die Wahl des TAN-Verfahrens, zeigt die App die Rückfrage und gibt die Antwort zurück. Bisher
  endete der Abruf dann mit einem Hinweis auf Home Assistant.
- Die PIN kommt weiterhin nie vom Handy: Das geht nur für Bankzugänge, deren PIN in Home Assistant gespeichert ist.
  Kinderhandys sehen keine Rückfragen. Der Abstand von 30 Minuten zwischen Abrufen aus der App bleibt; der tägliche
  Abruf läuft unverändert ohne Rückfragen. Im Änderungsprotokoll steht, dass geantwortet wurde, nie die TAN.

## 0.3.57

- App (ab Version 0.3.37): Der heutige Wert von Depot, Festgeld, VL und Immobilie und die Restschuld eines Kredits
  lassen sich am Handy eintragen. Nur für Konten ohne Bankabruf, die die Person sieht; nicht für Kinderhandys. Der
  Eintrag steht im Änderungsprotokoll.

## 0.3.56

- App (ab Version 0.3.35): Eine Bankfreigabe über Enable Banking lässt sich am Handy erneuern, sobald sie in
  höchstens 14 Tagen abläuft oder abgelaufen ist. Über diesen Weg lässt sich nur eine bestehende Freigabe erneuern,
  keine neue Bank verbinden. Kinderhandys können das nicht. Das Erneuern löst keinen Bankabruf aus.

## 0.3.55

- Umsätze in Home Assistant: Buchungen ohne Kategorie lassen sich der Reihe nach zuordnen, wie in der App. Die
  größten zuerst, mit Vorschlag aus ähnlichen Buchungen, wenn es einen gibt; überspringen geht auch. Der Link
  steht über der Liste, solange es solche Buchungen gibt.

## 0.3.54

- Budgets in Home Assistant: neuer Abschnitt *Vorschläge*, wie in der App. Aus den Ausgaben der letzten vollen Monate,
  aufgerundet; einzeln oder alle auf einmal übernehmen. Gezählt werden die gemeinsamen Konten, wie bei den Budgets
  des Haushalts. Kategorien, deren Budget schon passt, erscheinen nicht.

## 0.3.53

- App (ab Version 0.3.33): Umsätze und Auswertung lassen sich auf „Ich“ (nur die eigenen Konten) oder „Gemeinsam“
  (nur die gemeinsamen) einschränken. Kinderhandys und Geräte ohne Person bekommen das nicht.

## 0.3.52

- Enable Banking: Gibt die Bank bei der Freigabe keine Konten frei, wird nichts gespeichert, und die Meldung sagt,
  woran es meist liegt und was zu tun ist. Bisher blieb eine leere Bankverbindung zurück. Beim Erneuern einer
  Freigabe bleibt die alte in dem Fall bestehen.

## 0.3.51

- Eigene Budgets warnen jetzt wie die gemeinsamen: Ist eines überschritten, kommt ein Hinweis an die Person, der es
  gehört (an ihren Benachrichtigungsdienst, sonst an den üblichen). Am Handy sieht ihn nur sie.
- Das Ereignis `kassensturz_budget_schwelle` kommt auch für eigene Budgets, bei 80 % und 100 %, und trägt dann
  `person` und `person_id`. Die Ereignisse der gemeinsamen Budgets bleiben, wie sie waren.

## 0.3.50

- App (ab Version 0.3.32): *Konten → Wer hat was geändert?* zeigt das Änderungsprotokoll. Jede Person sieht nur
  Einträge zu Konten, die sie sieht, und zum ganzen Haushalt; eigene Budgets anderer Personen stehen dort nicht.
- Der Eintrag „Konto gelöscht“ hängt jetzt am Konto und erscheint darum am Handy nicht mehr bei Personen, die das
  Konto nie gesehen haben.
- Zahlungskalender: Auf dem Home Assistant Green kommt Home Assistant mit derselben Adresse wie der Tailscale-Proxy.
  Der Kalender lehnte darum auch Home Assistant ab. Jetzt entscheidet, ob ein Proxy die Anfrage weitergereicht hat;
  übers Tailnet bleibt der Kalender gesperrt.

## 0.3.49

- App (ab Version 0.3.31): Projekte ansehen, mit Gesamtkosten, Rest im Rahmen, Kosten je Kategorie und Monat und den
  Buchungen; an einer Buchung das Projekt wählen.
- App: Tilgungsplan eines Kredits mit Restschuld, Enddatum, Zinsen, Plan je Jahr und Sondertilgung.
- Die App sieht in einem Projekt nur die Buchungen der Konten, die die Person sieht.

## 0.3.48

- App (ab Version 0.3.30): Hinweise lassen sich am Handy erledigen. Eine Auffälligkeit als geprüft ausblenden, eine
  geplante Ausgabe als bezahlt oder entfallen abhaken, einen erwarteten Eingang als angekommen.
- App: Geplante Ausgaben und erwartete Eingänge stehen auf der Startseite. Eine geplante Ausgabe lässt sich nach
  *Kann ich mir das leisten?* vormerken, an einer Ausgabe *Geld kommt zurück* anmerken.
- Abhaken und Anlegen geht nur für Konten und Buchungen, die die Person sieht; ein Kinderhandy liest nur.

## 0.3.47

- Nach einem Update lädt die Oberfläche sicher die neue Fassung. Bisher zeigten Skript und Stil seit 0.3.22 dieselbe
  Version in der Adresse; ein Browser konnte so eine alte Fassung behalten.
- Technik: Die Oberfläche ist in Module aufgeteilt, die Schnittstelle des Servers in Bereiche. An Funktionen und
  Adressen ändert sich nichts.

## 0.3.46

- Zahlungskalender: Kommende Abbuchungen, Eingänge, geplante Ausgaben, letzte Tage zum Kündigen, Fälligkeiten und das
  Ende der Bankfreigaben als Kalender in Home Assistant, ein Jahr im Voraus.
  - Unter *Einstellungen → Zahlungskalender* die Adresse erstellen und in Home Assistant mit der Integration
    *Remote Calendar* eintragen.
  - Der Kalender ist aus, bis du die Adresse erstellst. Die Adresse ist nur im internen Netz von Home Assistant
    erreichbar und lässt sich jederzeit ersetzen oder abschalten.

## 0.3.45

- Änderungsprotokoll: Unter *Einstellungen → Änderungen* steht, wer im Haushalt wann was geändert hat, in Home
  Assistant oder am Handy.
  - Bei Buchungen, Budgets, Konten und Ausgleichszahlungen mit den Einzelheiten, sonst mit einem kurzen Satz.
  - Filter nach Person oder Gerät.
  - Hintergrundläufe und Inhalte von Formularen (PINs, Schlüssel, TANs) stehen nie darin. Einträge bleiben gut ein
    Jahr.

## 0.3.44

- Kredite mit Tilgungsplan: Am Konto der Art *Kredit* lassen sich Sollzins und Monatsrate eintragen.
  - Der Tilgungsplan zeigt die geschätzte Restschuld heute, den Monat der letzten Rate, die restlichen Zinsen und
    den Plan je Jahr.
  - Sondertilgung: Betrag eintragen und sehen, wie viel früher der Kredit fertig ist und wie viel Zinsen das spart.
  - Die geschätzte Restschuld ändert das Vermögen erst, wenn du sie übernimmst.

## 0.3.43

- Projekte: Buchungen quer zu Kategorien bündeln und sehen, was etwas insgesamt gekostet hat.
  - Unter *Budgets → Projekte* anlegen, auf Wunsch mit einem Rahmen in Euro.
  - Zuordnen an der Buchung, oder in den Umsätzen suchen und *Alle Treffer einem Projekt zuordnen*. So wird aus
    einem Tag aus Finanzguru ein Projekt.
  - Das Projekt zeigt Gesamtkosten, Rest im Rahmen, Ausgaben je Kategorie, Kosten je Monat und die Buchungen. Die
    Umsätze lassen sich nach Projekt filtern.
- Bankabruf per FinTS: Kennt die Bank die Produkt-ID noch nicht (Code 9078), erklärt die Meldung die Wartezeit.

## 0.3.42

- 1822direkt per FinTS: Kassensturz meldet sich jetzt so an, wie die Bank es erwartet.
  - Steht im Bankzugang die Bankleitzahl aus der IBAN (50050201), nimmt Kassensturz die der 1822direkt für FinTS
    (50050222).
  - Der Anmeldename geht in Großbuchstaben an die Bank; ein Eintrag im Feld Kunden-ID wird für diese Bank nicht
    mitgeschickt. Beides führte zu „Benutzer für Kunden nicht bevollmächtigt“ (Code 9210).
- Meldet eine Bank Code 9210, sagt Kassensturz, was im Bankzugang zu prüfen ist. Das Feld „Kundennummer, falls
  abweichend“ heißt jetzt „Kunden-ID (fast immer leer lassen)“.

## 0.3.41

- Bankabruf per FinTS: Nimmt die Bank die Anmeldung nicht an, steht jetzt ihr Grund in der Meldung (Text und Code der
  Bank). Bisher hieß es nur „Could not find system_id“. Die Antworten der Bank stehen auch im Protokoll der App.

## 0.3.40

- Geplante Ausgaben: Eine einmalige Ausgabe, die schon feststeht, zählt in der Prognose mit.
  - In der Übersicht mit Bezeichnung, Betrag, Tag und Konto eintragen, oder nach *Kann ich mir das leisten?* vormerken.
  - Bis sie bezahlt ist, mindert sie „frei verfügbar“ und den Verlauf der Prognose ab dem geplanten Tag. Sie steht
    unter *Als Nächstes*, auch in der App.
  - Kommt genau eine Abbuchung über genau den Betrag, hakt Kassensturz sie von selbst ab. Was nicht eindeutig ist,
    steht zur Auswahl. Ist der Tag vorbei und nichts gebucht, fragt Kassensturz einmal nach.
  - Eine abgehakte Ausgabe hebt die übliche Tagesrate für den Alltag nicht.
- Behoben: Das Ergebnis von *Kann ich mir das leisten?* brach auf schmalen Bildschirmen nach jedem Wort um.

## 0.3.39

- Erwartete Eingänge: Geld, das zurückkommen soll, bleibt offen, bis es da ist.
  - An einer Ausgabe mit *Geld kommt zurück* anmerken, etwa bei einer Retoure. Oder für sich allein anlegen, etwa
    für Auslagen.
  - Die Übersicht zeigt, was aussteht. Nach drei Wochen erinnert Kassensturz einmal.
  - Geht derselbe Betrag vom selben Absender auf demselben Konto ein, hakt Kassensturz den Eingang von selbst ab und
    meldet „Geld ist da“. Was nicht eindeutig ist, steht zur Auswahl.

## 0.3.38

- Auffälligkeiten: Kassensturz weist auf Buchungen der letzten zwei Wochen hin, die einen zweiten Blick lohnen.
  - Doppelt abgebucht: derselbe Empfänger, derselbe Betrag, höchstens drei Tage auseinander.
  - Erste Lastschrift eines Gläubigers, mit dem letzten Tag, an dem du sie bei der Bank zurückgeben kannst.
  - Ungewöhnlich hoher Betrag: mindestens dreimal so viel wie je zuvor bei diesem Empfänger.
- Die Hinweise stehen in der Übersicht und in der App und kommen einmal als Benachrichtigung. In der Übersicht lässt
  sich eine Buchung als geprüft ausblenden.
- Neues Ereignis `kassensturz_auffaelligkeit` für Automationen.

## 0.3.37

- Umstieg von Finanzguru, Nachtrag nach einem Blick auf die Kopfzeile eines echten Exports:
  - Notizen aus Finanzguru stehen als Notiz an der Buchung; Tags hängen als Text daran („Tags: …“).
  - Aufgeteilte Buchungen zählen nicht mehr doppelt. Finanzguru schreibt die Buchung („Original“) und darunter ihre
    Teile („Teilbuchung“, „Restbetrag“); übernommen wird nur die Buchung selbst. Ergeben die Teile genau ihren
    Betrag, bleibt sie aufgeteilt, sonst kommt sie ohne Aufteilung.
- Haushalt: Das Handy eines Kindes bekommt die Budgets des Haushalts nicht mehr. Bisher standen dort die Limits und
  was davon ausgegeben ist.

## 0.3.36

- Umstieg von Finanzguru: Der Excel- oder CSV-Export lässt sich unter *Konten → Datei importieren* übernehmen.
  - Ein Dialog ordnet die Konten des Exports zu: vorhandenes Konto, neues Konto oder nicht übernehmen.
  - Hat ein Konto schon Buchungen aus Bankabruf oder Datei, füllt der Export nur die Zeit davor auf. So entsteht
    nichts doppelt.
  - Kategorien aus Finanzguru lassen sich einer Kategorie von Kassensturz zuordnen oder neu anlegen. Zugeordnete
    Buchungen behalten ihre Kategorie; Umbuchungen bleiben Umbuchungen.
  - Auf Wunsch lernt Kassensturz daraus: Empfänger, die in Finanzguru verlässlich in einer Kategorie lagen, gelten
    auch für vorhandene und künftige Buchungen. Eigene Korrekturen haben Vorrang.
- Der Selbsttest des Kontostands zählt nachgetragene alte Buchungen nicht als neu.
- Excel-Dateien werden nur als Finanzguru-Export gelesen; der Eingangsordner zeigt einen solchen Export zum Zuordnen an.

## 0.3.35

- Haushalt, vierte Stufe: Kinder und Taschengeld.
  - Eine Person lässt sich unter *Einstellungen → Haushalt* als Kind kennzeichnen. Ein Kind trägt von geteilten
    Ausgaben zunächst nichts.
  - Neue Kontoart „Taschengeld": Du legst Betrag und Rhythmus fest (jede Woche oder jeden Monat) und wem das Konto
    gehört. Kassensturz schreibt das Taschengeld von selbst gut; Ausgaben trägst du von Hand ein.
  - Alle Erwachsenen sehen die Taschengeld-Konten in der App und können dort Ausgaben eintragen.
  - Ein Kind kann sein eigenes Handy koppeln. Es sieht nur sein Taschengeld-Konto und kann nichts ändern.
- Taschengeld ist eine Abmachung, kein Bankguthaben: Das Konto zählt nicht zum Vermögen, nicht zur Prognose und
  nicht zur Auswertung des Haushalts. Die Gutschrift ist als Umbuchung markiert.

## 0.3.34

- Haushalt: Sparziele je Person. Im Sparziel wählst du unter „Gehört" eine Person oder „Allen gemeinsam".
  Ein eigenes Ziel sieht in der App nur diese Person, gemeinsame sehen alle.
- Hängen ein eigenes und ein gemeinsames Ziel am selben Konto, wird dessen Stand weiter der Reihe nach verteilt,
  egal wer zuschaut.

## 0.3.33

- Haushalt: Geteilte Ausgaben zählen anteilig. In der Auswertung und in den eigenen Budgets einer Person zählt
  von einer geteilten Ausgabe nur ihr Teil – beim Zahler der eigene, bei den anderen ihrer.
- Das gilt für die Zahlen je Person: Auswertung und Monatsabschluss in der App, eigene Budgets, und die Ansicht
  einer Person unter *Budgets* in Home Assistant.
- Unverändert bleibt, was wirklich vom Konto abging: Buchungen, Kontostände, Prognose und die Zahlen des Haushalts.

## 0.3.32

- Haushalt: eigene Budgets je Person neben den gemeinsamen.
  - Die bisherigen Budgets gelten für den Haushalt. Gibt es eigene Konten, zählen sie nur noch die Ausgaben von
    den gemeinsamen Konten.
  - Jede Person kann zusätzlich eigene Budgets setzen. Sie zählen nur die Ausgaben von ihren eigenen Konten.
  - In Home Assistant wählst du unter *Budgets* zwischen „Haushalt" und den Personen. In der Mobile-App stehen die
    eigenen Budgets ab 0.3.26 unter „Nur für dich".
- Warnungen und Ereignisse zu Budgets beziehen sich weiter auf die Budgets des Haushalts.
- Ohne eigene Konten ändert sich nichts.

## 0.3.31

- Haushalt: Benachrichtigungen je Person. Unter *Einstellungen → Haushalt* trägst du bei jeder Person ihren
  Benachrichtigungsdienst ein, zum Beispiel `notify.mobile_app_handy`.
  - Neue Buchungen auf einem eigenen Konto gehen nur an die Person, der es gehört.
  - Neue Buchungen auf gemeinsamen Konten gehen an alle.
  - Hat eine Person keinen eigenen Dienst, gilt für ihre Konten weiter der Dienst aus der Konfiguration.
- Warnungen, Monatsabschluss, Sensoren und Ereignisse gelten weiter für den ganzen Haushalt und gehen an den Dienst
  aus der Konfiguration.

## 0.3.30

- Haushalt, zweite Stufe: Ausgaben teilen und ausgleichen.
  - Hat jemand etwas für den Haushalt vom eigenen Konto bezahlt, öffnest du die Buchung und wählst „Mit dem Haushalt
    teilen". Die anderen schulden dem Zahler dann ihren Anteil.
  - Geteilt wird zu gleichen Teilen oder nach dem Anteil, den du je Person unter *Einstellungen → Haushalt*
    einstellst, zum Beispiel 60 und 40. Mit 0 trägt eine Person nichts mit.
  - Unter *Einstellungen → Haushalt → Ausgleich* steht, wer wem wie viel schuldet. Eine Überweisung oder Barzahlung
    trägst du dort als Zahlung ein.
  - Die Mobile-App zeigt ab 0.3.23, was zwischen dir und den anderen offen ist.
- Von einer geteilten Buchung sehen die anderen Datum, Empfänger, Betrag und ihren Teil, sonst nichts vom Konto.
- Kassensturz bucht beim Teilen und Ausgleichen nichts um. Kontostände, Auswertung und Budgets bleiben, wie sie sind.

## 0.3.29

- Haushalt: Die Übersicht für die App nennt je Konto, ob es ein eigenes oder ein gemeinsames ist, und wer angemeldet
  ist. Die Mobile-App zeigt das ab 0.3.22 auf der Kontenseite.

## 0.3.28

- Haushalt für Paare und Familien, erste Stufe:
  - Unter *Einstellungen → Haushalt* legst du an, wer mitmacht.
  - Jedes Konto gehört einer Person oder allen gemeinsam. Das stellst du im Konto unter „Gehört" ein.
  - Jedes Handy wird beim Koppeln einer Person zugeordnet; bei schon gekoppelten Handys geht das nachträglich
    unter *Mobile Geräte*.
  - In der App sieht jede Person ihre eigenen Konten und die gemeinsamen – mit allem, was daran hängt: Buchungen,
    Belege, Verträge, Sparziele, Auswertung, Prognose und Vermögen. Fremde Konten lassen sich von dort auch nicht
    ändern.
  - Ein Bargeld-Konto, das jemand in der App anlegt, gehört dieser Person.
- Die Oberfläche in Home Assistant bleibt die Verwaltung des Haushalts und zeigt alles. Sensoren und
  Benachrichtigungen gelten weiter für den ganzen Haushalt.
- Solange kein Konto einer Person gehört, ändert sich nichts.

## 0.3.27

- Kassensturz ordnet mehr Buchungen von selbst zu:
  - Das Wörterbuch kennt gut 400 weitere Händler und Begriffe des Alltags, von Bäckerei über Krankenkasse bis
    Fahrschule.
  - Gelernt wird nicht mehr nur am Namen, sondern auch an Gläubiger-ID und IBAN. Wer unter wechselnden Namen
    abbucht, wird trotzdem wiedererkannt.
  - Steht nur PayPal, Klarna oder SumUp als Empfänger da, zählt der Händler aus dem Verwendungszweck. Damit lassen
    sich auch diese Buchungen lernen.
- Vorschläge beim Zuordnen: Kommt ein Wort bei mindestens drei verschiedenen Empfängern vor und gehört fast immer
  zur selben Kategorie, schlägt Kassensturz sie für neue Empfänger mit diesem Wort vor (in der Mobile-App ab 0.3.21).
- Nach dem Update werden alle nicht von Hand gesetzten Buchungen einmal neu zugeordnet.

## 0.3.26

- Die Erinnerung an eine ablaufende Bankfreigabe kommt früher und dreimal: 14, 7 und 2 Tage vorher, jeweils in der
  Übersicht und als Mitteilung.
- Für die Mobile-App (ab 0.3.20): Vermögensverlauf der letzten Monate.

## 0.3.25

- Für die Mobile-App (ab 0.3.19): neue Buchungen seit dem letzten Besuch je Gerät, dazu die Steuerübersicht und die
  Garantien zum Ansehen.

## 0.3.24

- Für die Mobile-App (ab 0.3.18): Liste der Buchungen ohne richtige Kategorie, die größten zuerst, und
  Budget-Vorschläge aus den Ausgaben der letzten vollen Monate.

## 0.3.23

- Die Mobile-App zeigt den Stand des Bankabrufs und kann ihn anstoßen (ab App 0.3.17): Enable Banking mit laufender
  Freigabe und FinTS-Zugänge mit gespeicherter PIN, höchstens alle 30 Minuten. Braucht eine Bank eine TAN, bleibt
  der Abruf der Oberfläche in Home Assistant vorbehalten.

## 0.3.22

- Vollständige Sicherung: *Einstellungen → Daten → Vollständige Sicherung* lädt Datenbank und Belege als eine
  ZIP-Datei, mit Prüfsumme für jede Datei. Eine leere Installation übernimmt sie beim Start aus dem Eingangsordner.
- Neuer Abschnitt *Einstellungen → Zustand*: Datenbank, Sicherungskopien und Belege auf einen Blick. „Jüngste
  Sicherung prüfen“ öffnet die Kopie und kontrolliert sie vollständig.
- Die Datenbank wird bei jedem Start geprüft. Ein Fehler erscheint als Hinweis in der Übersicht und als Mitteilung.
- Die Datenbank trägt jetzt eine Versionsnummer ihres Aufbaus. Eine ältere App warnt, wenn die Daten von einer
  neueren stammen.
- Hinweis, wenn zu einem Beleg die Datei fehlt.

## 0.3.21

- Die Mobile-App kann ein Konto für Bargeld anlegen (ab App 0.3.16). Andere Kontoarten bleiben der Oberfläche in
  Home Assistant vorbehalten.
- Neue Kontoart „Bargeld“.

## 0.3.20

- Garantie an Käufen: In jeder Ausgabe lässt sich „Garantie bis“ setzen, mit 2, 3 oder 5 Jahren ab Kauf oder einem
  eigenen Datum. Auch in der Mobile-App (ab 0.3.15).
- Neue Übersicht unter *Einstellungen → Garantien*: laufende Garantien nach Ablauf sortiert, dazu die zuletzt
  abgelaufenen.
- Erinnerung 30 Tage vor dem Ende, in der Übersicht und als Mitteilung, mit Hinweis, wenn der Beleg fehlt.

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
