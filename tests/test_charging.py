"""Ladevorgänge aus Ladecockpit – nur erfundene Daten."""
from kassensturz import charging, ha


def _giro(db):
    return db.insert("accounts", {"name": "KS-Testgiro", "kind": "giro"})


def _book(db, acc, day, cents, who):
    return db.insert("transactions", {"account_id": acc, "booking_date": day, "amount_cents": cents,
                                      "counterparty": who, "purpose": "Erfundener Zweck", "hash": f"ks-{day}-{cents}-{who}"})


EXPORT_DE = ("﻿Datum;Start;Ende;Standort;kWh;Preis pro kWh;Ladekosten;Blockiergebühr;Summe;Währung;Ø kW;Ladung-ID;Netz;"
             "Listenpreis pro kWh;Gutschrift;Netto;Betreiber;Adresse\r\n"
             "21.10.2026;18:18;18:47;Erfundenhausen;18,000;0,3700;6,66;0,00;6,66;EUR;37;ks-s1;Supercharger;0,4500;0,00;6,66;;\r\n"
             "02.11.2026;07:05;07:40;Musterstadt;30,500;0,4100;12,51;1,00;13,51;EUR;52;ks-s2;Supercharger;;0,00;13,51;;\r\n"
             "03.11.2026;12:00;12:30;Beispielort;10,000;0,5900;5,90;0,00;5,90;EUR;40;ks-s3;MultiPass;;;;Erfundene GmbH;\r\n"
             "kaputt;;;;;;;;;;;;;;;;;\r\n").encode("utf-8")


def test_export_is_read_and_matched_to_bank_bookings(db):
    acc = _giro(db)
    tesla = _book(db, acc, "2026-10-22", -666, "Tesla Germany GmbH")
    # Zwei Buchungen mit demselben Betrag: die mit „Tesla“ im Namen gewinnt.
    _book(db, acc, "2026-11-03", -1351, "Erfundener Laden")
    tesla2 = _book(db, acc, "2026-11-04", -1351, "TESLA SUPERCHARGER")
    # Zu spät für den dritten Ladevorgang (mehr als sieben Tage).
    _book(db, acc, "2026-11-20", -590, "Erfundene GmbH")

    res = charging.import_csv(db, EXPORT_DE)
    assert res == {"added": 3, "known": 0, "skipped": 1, "linked": 2}
    rows = {r["session_id"]: r for r in db.query("SELECT * FROM charging_sessions")}
    assert rows["ks-s1"]["tx_id"] == tesla and rows["ks-s2"]["tx_id"] == tesla2 and rows["ks-s3"]["tx_id"] is None
    assert (rows["ks-s2"]["kwh_wh"], rows["ks-s2"]["total_cents"], rows["ks-s2"]["idle_cents"]) == (30500, 1351, 100)
    assert rows["ks-s3"]["network"] == "multipass" and rows["ks-s1"]["started"] == "2026-10-21T18:18:00"
    # Es entsteht keine Buchung.
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 4

    again = charging.import_csv(db, EXPORT_DE)
    assert (again["added"], again["known"]) == (0, 3)

    s = charging.summary(db)
    nov = next(m for m in s["months"] if m["month"] == "2026-11")
    assert (nov["sessions"], nov["kwh"], nov["total_cents"]) == (2, 40.5, 1941)
    assert nov["price_per_kwh_cents"] == round(1941 * 1000 / 40500, 1)
    assert s["unlinked_count"] == 1 and s["unlinked"][0]["site"] == "Beispielort"
    assert charging.for_transactions(db, [tesla])[tesla]["kwh"] == 18.0


def test_english_export_and_wrong_files(db):
    import pytest
    english = ("Date,Start,End,Site,kWh,Price per kWh,Charging cost,Idle fee,Total,Currency,Avg kW,Session ID,Network\r\n"
               "2026-11-05,09:10,09:40,Testville,22.250,0.4000,8.90,0.00,8.90,EUR,45,ks-e1,Supercharger\r\n"
               "2026-11-06,09:10,09:40,Testville,22.250,0.4000,8.90,0.00,8.90,USD,45,ks-e2,Supercharger\r\n").encode()
    assert charging.import_csv(db, english)["added"] == 1
    with pytest.raises(charging.ImportError_, match="kein Export von Ladecockpit"):
        charging.import_csv(db, b"Buchungstag;Betrag;Empfaenger\r\n01.11.2026;-5,00;Erfunden\r\n")


def test_new_sessions_come_from_the_sensor(db, monkeypatch):
    acc = _giro(db)
    tx = _book(db, acc, "2026-11-10", -720, "Tesla")
    sensor = {"state": "7.2", "attributes": {"unit_of_measurement": "EUR", "session_id": "ks-h1", "start": "2026-11-09T20:01:00+01:00",
                                             "energy_kwh": 16.0, "site": "Erfundenhausen", "network": "supercharger", "idle_fee": 0}}
    asked = []
    monkeypatch.setattr(ha, "available", lambda: True)
    monkeypatch.setattr(ha, "state", lambda entity: asked.append(entity) or sensor)
    assert charging.poll(db, force=True) is True
    assert asked == ["sensor.ladecockpit_last_charge"]
    assert db.scalar("SELECT tx_id FROM charging_sessions WHERE session_id = 'ks-h1'") == tx
    # Derselbe Ladevorgang ein zweites Mal ändert nichts, und ohne force wird höchstens alle fünf Minuten gefragt.
    assert charging.poll(db, force=True) is False
    assert charging.poll(db) is False and len(asked) == 2
    # Unbrauchbare Zustände werden übergangen.
    for bad in (None, {"state": "unknown", "attributes": {}}, {"state": "5", "attributes": {"session_id": "x", "start": "?", "energy_kwh": 1}},
                {"state": "5", "attributes": {"session_id": "x", "start": "2026-11-01", "energy_kwh": 1, "unit_of_measurement": "USD"}}):
        assert charging.from_sensor(bad) is None


def test_web_routes(client, db):
    acc = _giro(db)
    _book(db, acc, "2026-10-22", -666, "Tesla")
    got = client.post("/api/charging/import", files={"file": ("ladecockpit.csv", EXPORT_DE, "text/csv")})
    assert got.status_code == 200 and got.json()["added"] == 3
    assert client.get("/api/charging").json()["count"] == 3
    items = client.get("/api/transactions").json()["items"]
    assert items[0]["charging"]["site"] == "Erfundenhausen"
    bad = client.post("/api/charging/import", files={"file": ("x.csv", b"a;b\r\n1;2\r\n", "text/csv")})
    assert bad.status_code == 400
    assert db.scalar("SELECT text FROM audit_log ORDER BY id DESC LIMIT 1").startswith("Ladevorgänge aus Ladecockpit übernommen")


def test_mobile_routes(db, monkeypatch):
    from kassensturz import household
    from test_mobile_write import https_client, paired_headers, reset_mobile_guards
    reset_mobile_guards(monkeypatch)
    acc = _giro(db)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    own = db.insert("accounts", {"name": "KS-Annas Konto", "kind": "giro", "owner_person_id": anna})
    shared_tx = _book(db, acc, "2026-10-22", -666, "Tesla")
    annas_tx = _book(db, own, "2026-11-04", -1351, "Tesla")
    charging.import_csv(db, EXPORT_DE)
    with https_client() as client:
        assert client.get("/api/v1/charging").status_code == 401
        headers = paired_headers(client)
        assert "charging" in client.get("/api/v1/me", headers=headers).json()["capabilities"]
        months = client.get("/api/v1/charging", headers=headers).json()
        # Ein Gerät ohne Person sieht Annas eigenes Konto nicht, also auch nicht ihren Ladevorgang.
        assert months["count"] == 2 and set(months["months"][0]) == {
            "month", "sessions", "kwh", "total_cents", "idle_cents", "price_per_kwh_cents"}
        got = client.get(f"/api/v1/transactions/{shared_tx}/charging", headers=headers).json()["charging"]
        assert got["site"] == "Erfundenhausen" and got["kwh"] == 18.0 and "tx_id" not in got and "id" not in got
        assert client.get("/api/v1/transactions/999/charging", headers=headers).status_code == 404

        def pair(person):
            secret = client.post("/api/mobile/pairings", json={"person_id": person}).json()["pairing_secret"]
            token = client.post("/api/v1/pair", json={"pairing_secret": secret, "device_name": "KS-Handy"}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        annas = pair(anna)
        assert client.get("/api/v1/charging", headers=annas).json()["count"] == 3
        assert client.get(f"/api/v1/transactions/{annas_tx}/charging", headers=annas).json()["charging"]["kwh"] == 30.5
        # Ben sieht Annas Konto nicht: weder die Buchung noch ihren Ladevorgang in den Monaten.
        bens = pair(household.create_person(db, {"name": "Ben"})["id"])
        assert client.get(f"/api/v1/transactions/{annas_tx}/charging", headers=bens).status_code == 404
        assert client.get("/api/v1/charging", headers=bens).json()["count"] == 2


def test_total_with_vat_is_matched_and_reimport_fixes_old_amounts(db):
    acc = _giro(db)
    tx = _book(db, acc, "2026-10-25", -1215, "Tesla")
    # Summe 12,15 € wird abgebucht; Netto 10,21 € ist ohne Mehrwertsteuer.
    export = ("\ufeffDatum;Start;Ende;Standort;kWh;Preis pro kWh;Ladekosten;Blockiergebühr;Summe;Währung;Ø kW;Ladung-ID;Netz;"
              "Listenpreis pro kWh;Gutschrift;Netto;Betreiber;Adresse\r\n"
              "24.10.2026;19:40;20:11;Erfundenhausen;41,800;0,2907;12,15;0,00;12,15;EUR;81;ks-n1;Supercharger;0,5300;10,00;10,21;;\r\n")
    # So hatte 0.3.62 den Ladevorgang gespeichert: mit dem Nettobetrag.
    db.insert("charging_sessions", {"session_id": "ks-n1", "started": "2026-10-24T19:40:00", "site": "Erfundenhausen",
                                    "network": "supercharger", "kwh_wh": 41800, "total_cents": 1021, "idle_cents": 0,
                                    "source": "csv"})
    res = charging.import_csv(db, export.encode())
    assert (res["added"], res["known"], res["linked"]) == (0, 1, 1)
    row = db.one("SELECT total_cents, tx_id FROM charging_sessions WHERE session_id = 'ks-n1'")
    assert (row["total_cents"], row["tx_id"]) == (1215, tx)


def test_analyze_recognises_export_and_web_pages(client, db):
    got = client.post("/api/import/analyze", files={"file": ("ladecockpit-sessions.csv", EXPORT_DE, "text/csv")})
    assert got.json() == {"kind": "ladecockpit"}
    assert db.scalar("SELECT COUNT(*) FROM charging_sessions") == 0
    for page in (b"<!DOCTYPE html><html><body>Anmelden</body></html>", b'{"detail":"Unauthorized"}'):
        bad = client.post("/api/import/analyze", files={"file": ("ladecockpit-sessions.csv", page, "text/csv")})
        assert bad.status_code == 400 and "Webseite" in bad.json()["detail"]


def test_inbox_takes_the_export(db, tmp_path, monkeypatch):
    import os
    import time as _time
    from kassensturz import inbox
    monkeypatch.setattr(inbox, "ensure_folder", lambda: tmp_path)
    f = tmp_path / "ladecockpit-sessions.csv"
    f.write_bytes(EXPORT_DE)
    old = _time.time() - 60
    os.utime(f, (old, old))
    inbox.scan(db)
    assert db.scalar("SELECT COUNT(*) FROM charging_sessions") == 3
    assert not f.exists()


def _session(db, sid, started, cents, wh=20000):
    db.insert("charging_sessions", {"session_id": sid, "started": started, "site": "Erfundenhausen", "network": "supercharger",
                                    "kwh_wh": wh, "total_cents": cents, "idle_cents": 0, "source": "test"})


def test_late_card_booking_and_grouped_billing(db):
    acc = _giro(db)
    # Kreditkarte bucht 20 Tage später; ohne „Tesla“ im Text würde das nicht zugeordnet.
    late = _book(db, acc, "2026-10-21", -1500, "TESLA MOTORS")
    _book(db, acc, "2026-10-21", -1700, "Erfundener Laden")
    _session(db, "ks-g0", "2026-10-01T10:00:00", 1500)
    _session(db, "ks-g9", "2026-10-01T11:00:00", 1700)
    # Drei Ladevorgänge, eine Abbuchung über die Summe
    for n, (day, cents) in enumerate([("2026-11-02", 1000), ("2026-11-09", 1234), ("2026-11-16", 2266)]):
        _session(db, f"ks-g{n + 1}", f"{day}T18:00:00", cents)
    sum_tx = _book(db, acc, "2026-11-30", -4500, "Tesla Germany")
    linked = charging.match(db)
    got = {r["session_id"]: r["tx_id"] for r in db.query("SELECT session_id, tx_id FROM charging_sessions")}
    assert got["ks-g0"] == late and got["ks-g9"] is None
    assert [got[f"ks-g{n}"] for n in (1, 2, 3)] == [sum_tx] * 3 and linked == 4
    line = charging.for_transactions(db, [sum_tx])[sum_tx]
    assert (line["count"], line["site"], line["total_cents"], line["kwh"]) == (3, "3 Ladevorgänge", 4500, 60.0)
    assert charging.summary(db)["free_tesla_bookings"] == 0


def test_manual_link_with_suggestions(client, db):
    acc = _giro(db)
    _session(db, "ks-m1", "2026-11-05T18:00:00", 2000)
    other = _book(db, acc, "2026-11-06", -2100, "PayPal *Tesla")
    _book(db, acc, "2026-11-06", -999, "Erfundener Bäcker")
    sid = db.scalar("SELECT id FROM charging_sessions WHERE session_id = 'ks-m1'")
    assert charging.summary(db)["free_tesla_bookings"] == 1
    items = client.get(f"/api/charging/{sid}/suggestions").json()["items"]
    assert [i["id"] for i in items] == [other]
    assert client.post(f"/api/charging/{sid}/link", json={"tx_id": "x"}).status_code == 400
    assert client.post(f"/api/charging/{sid}/link", json={"tx_id": 9999}).status_code == 404
    got = client.post(f"/api/charging/{sid}/link", json={"tx_id": other})
    assert got.status_code == 200 and got.json()["unlinked_count"] == 0
    assert db.scalar("SELECT text FROM audit_log ORDER BY id DESC LIMIT 1").startswith("Ladevorgang einer Buchung zugeordnet")
    client.post(f"/api/charging/{sid}/link", json={"tx_id": None})
    assert db.scalar("SELECT tx_id FROM charging_sessions WHERE id = ?", (sid,)) is None
