"""Zahlungskalender – nur erfundene Daten."""
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from kassensturz import calendar_feed, main

TODAY = date.today()


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def setup(db):
    giro = db.insert("accounts", {"name": "KS-Girokonto", "kind": "giro", "in_forecast": 1})
    db.insert("contracts", {"key": "ks-strom", "name": "KS-Stromanbieter", "counterparty": "KS-Strom", "interval": "monatlich",
                            "amount_cents": -8900, "account_id": giro, "manual": 1, "active": 1, "status": "confirmed",
                            "next_due": d(3), "contract_end": d(200), "notice_months": 1})
    db.insert("contracts", {"key": "ks-gehalt", "name": "KS-Arbeitgeber", "counterparty": "KS-AG", "interval": "monatlich",
                            "kind": "income", "amount_cents": 345012, "account_id": giro, "manual": 1, "active": 1,
                            "status": "confirmed", "next_due": d(10)})
    db.insert("contracts", {"key": "ks-weg", "name": "KS-Ignoriert", "counterparty": "KS-X", "interval": "monatlich",
                            "amount_cents": -100, "account_id": giro, "manual": 1, "active": 1, "status": "ignored",
                            "next_due": d(2), "contract_end": d(100), "notice_months": 1})
    db.insert("planned_expenses", {"label": "KS-Handwerker", "cents": 85000, "due_date": d(5), "account_id": giro,
                                   "status": "open", "since": d(0)})
    db.insert("planned_expenses", {"label": "KS-Erledigt", "cents": 100, "due_date": d(6), "account_id": giro,
                                   "status": "paid", "since": d(0)})
    db.insert("expected_incomes", {"label": "KS-Retoure", "cents": 7990, "account_id": giro, "since": d(-3),
                                   "due_date": d(18), "status": "open"})
    db.insert("accounts", {"name": "KS-Festgeld", "kind": "festgeld", "matures_on": d(90)})
    db.insert("accounts", {"name": "KS-Altkredit", "kind": "kredit", "matures_on": d(-5)})
    db.insert("goals", {"name": "KS-Urlaub", "target_cents": 200000, "due_date": d(120)})
    db.insert("eb_sessions", {"aspsp_name": "KS-Bank", "aspsp_country": "DE", "valid_until": d(40) + "T10:00:00+00:00",
                              "status": "active"})
    return giro


def test_events_cover_payments_deadlines_and_reminders(db):
    setup(db)
    items = calendar_feed.events(db)
    summaries = [(e["date"].isoformat(), e["summary"]) for e in items]
    assert (d(3), "KS-Stromanbieter: −89,00 €") in summaries
    assert (d(10), "KS-Arbeitgeber: +3.450,12 €") in summaries
    assert (d(5), "Geplant: KS-Handwerker −850,00 €") in summaries
    assert (d(18), "Geld steht aus: KS-Retoure +79,90 €") in summaries
    assert (d(90), "Festgeld fällig: KS-Festgeld") in summaries
    assert (d(120), "Sparziel: KS-Urlaub") in summaries
    assert (d(40), "Bankfreigabe läuft ab: KS-Bank") in summaries
    deadline = next(e for e in items if e["summary"].startswith("Letzter Tag zum Kündigen"))
    assert deadline["summary"] == "Letzter Tag zum Kündigen: KS-Stromanbieter" and "1 Monate" in deadline["description"]
    text = " ".join(s for _, s in summaries)
    assert "KS-Ignoriert" not in text and "KS-Erledigt" not in text and "KS-Altkredit" not in text
    assert sum(1 for _, s in summaries if s.startswith("KS-Stromanbieter")) >= 12
    assert [e["date"] for e in items] == sorted(e["date"] for e in items)
    assert all(TODAY <= e["date"] <= TODAY + timedelta(days=calendar_feed.AHEAD_DAYS) for e in items)
    assert len({e["uid"] for e in items}) == len(items)


def test_ics_is_valid_folded_and_escaped():
    items = [{"uid": "x-1@kassensturz", "date": date(2027, 1, 31), "summary": "KS; Komma, Strich\\ und Umlaute äöü " * 4,
              "description": "Zeile 1\nZeile 2"}]
    text = calendar_feed.ics(items, now=datetime(2027, 1, 1, 12, tzinfo=UTC))
    lines = text.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR" and lines[-1] == ""
    assert "DTSTART;VALUE=DATE:20270131" in lines and "DTEND;VALUE=DATE:20270201" in lines and "DTSTAMP:20270101T120000Z" in lines
    assert all(len(line.encode()) <= 75 for line in lines)
    unfolded = text.replace("\r\n ", "")
    assert r"SUMMARY:KS\; Komma\, Strich\\ und Umlaute äöü" in unfolded
    assert "DESCRIPTION:Zeile 1\\nZeile 2" in unfolded


def test_feed_is_off_until_switched_on_and_a_new_address_kills_the_old(client, db):
    setup(db)
    assert client.get("/api/calendar").json()["enabled"] is False
    assert client.get("/calendar/irgendwas.ics").status_code == 404
    on = client.post("/api/calendar", json={"action": "on"}).json()
    assert on["enabled"] and on["url"].startswith("http://") and on["url"].endswith(".ics") and ":8099/calendar/" in on["url"]
    assert on["count"] > 10 and on["next"][0]["date"] == d(3)
    path = "/calendar/" + on["url"].rsplit("/", 1)[1]
    got = client.get(path)
    assert got.status_code == 200 and got.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:KS-Stromanbieter: −89\\,00 €" in got.text.replace("\r\n ", "")
    assert client.post("/api/calendar", json={"action": "on"}).json()["url"] == on["url"]     # bleibt
    renewed = client.post("/api/calendar", json={"action": "renew"}).json()
    assert renewed["url"] != on["url"] and client.get(path).status_code == 404
    assert client.get(path.replace(".ics", "")).status_code == 404
    assert client.post("/api/calendar", json={"action": "off"}).json() == {**client.get("/api/calendar").json(), "enabled": False}
    assert client.get("/calendar/" + renewed["url"].rsplit("/", 1)[1]).status_code == 404
    assert client.post("/api/calendar", json={"action": "weg"}).status_code == 400
    assert [r["text"] for r in db.query("SELECT text FROM audit_log ORDER BY id")] == [
        "Zahlungskalender: eingeschaltet", "Zahlungskalender: eingeschaltet",
        "Zahlungskalender: neue Adresse, die alte gilt nicht mehr", "Zahlungskalender: ausgeschaltet"]


def test_only_home_assistant_inside_reaches_the_feed(db, monkeypatch):
    with TestClient(main.app, client=("127.0.0.1", 50123)) as local:
        url = local.post("/api/calendar", json={"action": "on"}).json()["url"]
        path = "/calendar/" + url.rsplit("/", 1)[1]
        for peer, status in (("172.30.32.1", 200), ("172.30.33.7", 200), ("172.30.32.2", 200),
                             ("192.168.1.20", 403), ("100.64.0.5", 403), ("203.0.113.9", 403)):
            # Ohne „with“: Der zweite Client soll die Datenbank des ersten nicht schließen.
            assert TestClient(main.app, client=(peer, 40000)).get(path).status_code == status, peer
        # Auf dem Green teilen sich Core und der Tailscale-Proxy die Adresse 172.30.32.1; der Proxy ist
        # vertrauenswürdig eingetragen. Ohne Weiterleitungs-Kopfzeilen ist es Core: erlaubt.
        monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", main.parse_trusted_proxy_networks("172.30.32.1/32"))
        assert TestClient(main.app, client=("172.30.32.1", 40000)).get(path).status_code == 200
        for header in ({"X-Forwarded-For": "100.64.0.9"}, {"X-Forwarded-Proto": "https"},
                       {"Forwarded": "for=100.64.0.9"}, {"Tailscale-User-Login": "x@example.invalid"}):
            got = TestClient(main.app, client=("172.30.32.1", 40000)).get(path, headers=header)
            assert got.status_code == 403, header
        # Schreiben und alle anderen Adressen bleiben für das interne Netz gesperrt.
        core = TestClient(main.app, client=("172.30.32.1", 40000))
        if True:
            assert core.get("/api/calendar").status_code == 403
            assert core.post(path).status_code == 403
            assert core.get("/api/transactions").status_code == 403


def test_peer_check():
    assert calendar_feed.peer_allowed("172.30.32.1") and calendar_feed.peer_allowed("127.0.0.1")
    assert not calendar_feed.peer_allowed("172.30.34.1") and not calendar_feed.peer_allowed("") and not calendar_feed.peer_allowed(None)
