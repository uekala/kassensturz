# Lokale Verschlüsselung gespeicherter Banking-Geheimnisse

- Status: Implementierungsbeschreibung
- Verfahren: AES-256-GCM (authenticated encryption)
- Geltungsbereich: FinTS-PINs und Open-Banking-Private-Key in `secrets.json`

## 1. Format und Ablauf

Neue Geheimnisse werden nicht mehr als Klartext-JSON gespeichert. Die Datei `secrets.json` enthält einen versionierten Envelope mit:

- Formatkennung und Formatversion;
- zufälliger 96-Bit-Nonce je Schreibvorgang;
- AES-GCM-Ciphertext einschließlich Authentifizierungstag.

Die Anwendung nutzt AES-256-GCM aus der bereits vorhandenen `cryptography`-Abhängigkeit. Der feste Additional-Authenticated-Data-Wert bindet den Ciphertext an das Kassensturz-Format und die Version. Eine Änderung des Ciphertexts, der Nonce oder des Schlüssels führt zu einem Entschlüsselungsfehler.

## 2. Installationsschlüssel

Standardmäßig wird bei der ersten Speicherung ein kryptografisch zufälliger 256-Bit-Schlüssel in `secrets.key` im Datenverzeichnis angelegt. Die Datei wird mit Modus `0600` erstellt und beim Lesen als reguläre Datei ohne Symlink-Following geöffnet.

Optional kann ein externer Schlüssel über die Umgebungsvariable `KASSENSTURZ_MASTER_KEY` übergeben werden. Der Wert muss genau 64 Hex-Zeichen (32 Bytes) enthalten. Ist die Variable gesetzt, hat sie Vorrang vor `secrets.key`. Ein falsch gesetzter oder abweichender Schlüssel führt zu einem harten Fehler – die Anwendung darf die Datei nicht als leer interpretieren oder überschreiben.

Der Schlüssel wird nicht an einen Kassensturz-Cloud-Dienst übertragen. Es gibt weder Schlüssel-Escrow noch automatische Schlüsselrotation.

## 3. Migration vorhandener Installationen

Eine gültige bisherige Klartextdatei wird beim ersten Lesezugriff erkannt und atomar in das verschlüsselte Format migriert. Der erste erfolgreiche Lesezugriff liefert denselben Inhalt wie vorher; der neue Dateistand enthält nur noch den AES-GCM-Envelope.

Ungültige JSON-Daten, unbekannte Formate, fehlende Schlüssel und Authentifizierungsfehler werden nicht verschluckt. Die Anwendung wirft einen eindeutigen Fehler und lässt die vorhandene Datei unverändert. Dadurch wird verhindert, dass ein Schreibvorgang nach einem fehlgeschlagenen Entschlüsseln vorhandene PINs oder Schlüssel durch eine leere Datei ersetzt.

## 4. Dateirechte und Backups

- `secrets.json`: Modus `0600`.
- `secrets.key`: Modus `0600`.
- Datenverzeichnis: Modus `0700`.
- Home-Assistant-Backups schließen beide Dateien aus.
- Bei Standalone-Installationen muss der Schlüssel getrennt von der regulären Datensicherung aufbewahrt werden, beispielsweise in einem administrativen Secret-Manager oder auf einem getrennten, verschlüsselten Offline-Medium.

Für eine Wiederherstellung der gespeicherten Banking-Zugangsdaten werden sowohl der verschlüsselte Inhalt als auch der dazugehörige Schlüssel benötigt. Der Schlüssel darf nicht zusammen mit der verschlüsselten Datei in demselben ungeschützten Backup liegen. Wird der Schlüssel verloren, sind die gespeicherten PINs und der Open-Banking-Private-Key nicht wiederherstellbar; sie müssen anschließend bei den jeweiligen Bankzugängen neu eingegeben werden. Die SQLite-Finanzdatenbank ist davon nicht betroffen.

## 5. Sicherheitsgrenzen

Diese Implementierung schützt gespeicherte Banking-Geheimnisse gegen das isolierte Offenlegen oder Kopieren der verschlüsselten Datei. Sie schützt **nicht** gegen:

- einen Angreifer mit Leserechten auf das gesamte laufende Datenverzeichnis, wenn dort auch `secrets.key` liegt;
- Root-/Administratorzugriff auf den laufenden Host oder Container;
- Malware im Kassensturz-Prozess oder Speicherabbilder während der Entschlüsselung;
- unverschlüsselte Betriebssystem-Swaps, Crash-Dumps oder kompromittierte Backups;
- Verlust oder absichtliches Löschen des Installationsschlüssels.

Für höhere Schutzanforderungen soll ein extern verwalteter `KASSENSTURZ_MASTER_KEY` über einen geschützten Secret-Mechanismus bereitgestellt werden. Die Umgebungsvariable ist nur für vertrauenswürdige Deployment-Administratoren bestimmt und darf nicht in Shell-History, Compose-Dateien, Logs oder Tickets dokumentiert werden.

## 6. Tests und Freigabekriterien

Die Testabdeckung umfasst:

- Verschlüsselung ohne Klartext-Geheimnisse in der gespeicherten Datei;
- Dateirechte für Daten- und Schlüsseldatei;
- Migration des bisherigen Klartextformats beim ersten Zugriff;
- Ablehnung ungültiger Master-Keys;
- Fail-closed-Verhalten bei falschem Schlüssel;
- Erkennung manipulierter Ciphertexte;
- Sicherstellung, dass ein Entschlüsselungsfehler keine bestehende Geheimnisdatei überschreibt.

Die Verschlüsselung dieser lokalen Geheimnisse ersetzt weder die noch ausstehende Mobile-API-Authentifizierung noch HTTPS, Gerätewiderruf oder die Prüfung der Open-Banking-Berechtigung für kommerzielle Drittanbieter-Nutzung.
