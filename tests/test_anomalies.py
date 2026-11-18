"""Auffälligkeiten – nur erfundene Daten."""
from datetime import date, timedelta

import pytest

from kassensturz import anomalies, household, ledger, services

TODAY = date.today()
CREDITOR = "DE98ZZZ09999999999"


def day(back: int) -> str:
    return (TODAY - timedelta(days=back)).isoformat()


def account(db, name="KS-Testkonto", **extra):
    return db.insert("accounts", {"name": name, "kind": "giro", **extra})


def book(db, acc, back, cents, who, source="openbanking", **extra):
    ledger.import_rows(db, acc, [{"booking_date": day(back), "amount_cents": cents, "counterparty": who,
                                  "purpose": f"Beleg {back} {cents}", **extra}], source)
    return db.scalar("SELECT MAX(id) FROM transactions")


def kinds(db):
    return [(a["kind"], a["tx_id"]) for a in anomalies.find(db, TODAY)]


@pytest.fixture()
def settled(db):
    """Ein Konto, das schon lange Buchungen hat."""
    acc = account(db)
    book(db, acc, 200, -1234, "Erfundener Altbestand")
    return acc


# --- Doppelt abgebucht --------------------------------------------------------------------

def test_same_payee_and_amount_within_three_days_is_a_double(db, settled):
    first = book(db, settled, 5, -4999, "Erfundener Onlineshop GmbH")
    second = book(db, settled, 3, -4999, "ERFUNDENER ONLINESHOP GMBH 4711")
    found = anomalies.find(db, TODAY)
    assert [(a["kind"], a["tx_id"], a["other_tx_id"]) for a in found] == [("double", second, first)]
    assert found[0]["title"] == "Doppelt abgebucht? ERFUNDENER ONLINESHOP GMBH 4711"
    assert "49,99 €" in found[0]["text"] and "KS-Testkonto" in found[0]["text"]
    assert f"am {(TODAY - timedelta(days=5)).strftime('%d.%m.')} und am" in found[0]["text"]


def test_two_on_the_same_day_are_named_as_such(db, settled):
    # Beide kommen mit demselben Abruf, wie von der Bank.
    ledger.import_rows(db, settled, [
        {"booking_date": day(2), "amount_cents": -2500, "counterparty": "Erfundenes Kino", "purpose": "Karte 1"},
        {"booking_date": day(2), "amount_cents": -2500, "counterparty": "Erfundenes Kino", "purpose": "Karte 2"},
    ], "openbanking")
    only = anomalies.find(db, TODAY)[0]
    assert only["kind"] == "double" and "zweimal am" in only["text"]


def test_what_is_not_a_double(db, settled):
    other = account(db, "KS-Zweitkonto")
    book(db, settled, 6, -500, "Erfundener Bäcker")        # Kleinbeträge wiederholen sich
    book(db, settled, 5, -500, "Erfundener Bäcker")
    book(db, settled, 9, -4000, "Erfundener Friseur")      # zu weit auseinander
    book(db, settled, 4, -4000, "Erfundener Friseur")
    book(db, settled, 3, -3000, "Erfundene Tankstelle")    # anderes Konto
    book(db, other, 3, -3000, "Erfundene Tankstelle")
    book(db, settled, 3, -2000, "Erfundener Markt")        # anderer Betrag
    book(db, settled, 2, -2100, "Erfundener Markt")
    book(db, settled, 3, -6000, "Erfundener Flohmarkt", source="manual")  # selbst eingetragen
    book(db, settled, 2, -6000, "Erfundener Flohmarkt", source="manual")
    book(db, settled, 3, 7000, "Erfundene Erstattung")     # Eingänge
    book(db, settled, 2, 7000, "Erfundene Erstattung")
    assert kinds(db) == []


def test_only_the_last_two_weeks_count(db, settled):
    book(db, settled, 20, -4999, "Erfundener Onlineshop")
    book(db, settled, 19, -4999, "Erfundener Onlineshop")
    assert kinds(db) == []
    # Die frühere Buchung darf knapp vor dem Zeitraum liegen, die spätere muss darin sein.
    book(db, settled, 16, -8800, "Erfundene Werkstatt")
    late = book(db, settled, 14, -8800, "Erfundene Werkstatt")
    assert kinds(db) == [("double", late)]


# --- Erste Lastschrift --------------------------------------------------------------------

def test_first_direct_debit_of_a_creditor_names_the_last_day_to_return_it(db, settled):
    tx = book(db, settled, 4, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR, mandate_ref="M-1")
    only = anomalies.find(db, TODAY)[0]
    until = TODAY - timedelta(days=4) + timedelta(days=56)
    assert (only["kind"], only["tx_id"], only["return_until"]) == ("debit", tx, until.isoformat())
    assert only["title"] == "Erste Lastschrift von Erfundenes Abo Ltd"
    assert f"bis {until.strftime('%d.%m.%Y')} bei deiner Bank zurückgeben" in only["text"]
    assert (only["creditor_id"], only["mandate_ref"]) == (CREDITOR, "M-1")


def test_known_creditor_is_not_new_even_under_another_name(db, settled):
    book(db, settled, 90, -2990, "Erfundenes Abo Ltd", creditor_id="DE98 ZZZ 0999 9999 999")
    book(db, settled, 4, -2990, "ERF. ABO LIMITED LONDON", creditor_id=CREDITOR)
    assert kinds(db) == []


def test_history_from_finanzguru_makes_a_creditor_known(db, settled):
    book(db, settled, 400, -2990, "Erfundenes Abo Ltd", source="finanzguru", creditor_id=CREDITOR)
    book(db, settled, 4, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR)
    assert kinds(db) == []


def test_debit_without_creditor_id_is_recognised_by_its_booking_text(db, settled):
    tx = book(db, settled, 2, -1500, "Erfundener Verein", booking_text="SEPA-Lastschrift")
    assert kinds(db) == [("debit", tx)]
    # Eine Kartenzahlung beim selben neuen Händler ist keine Lastschrift.
    book(db, settled, 1, -1500, "Erfundener Kiosk", booking_text="Kartenzahlung")
    assert kinds(db) == [("debit", tx)]


def test_new_account_and_handled_debits_stay_quiet(db, settled):
    fresh = account(db, "KS-Neues Konto")
    book(db, fresh, 30, -100, "Erfundener Start")
    book(db, fresh, 3, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR)
    assert kinds(db) == []  # auf einem neuen Konto ist jede Lastschrift die erste
    tx = book(db, settled, 3, -1990, "Erfundene Zeitung", creditor_id="DE11ZZZ00000000001")
    assert kinds(db) == [("debit", tx)]
    db.execute("UPDATE transactions SET category_locked = 1 WHERE id = ?", (tx,))
    assert kinds(db) == []  # wer die Kategorie gesetzt hat, kennt die Buchung


# --- Ungewöhnlich hoher Betrag ------------------------------------------------------------

def _usual(db, acc, who="Erfundener Händler"):
    for back, cents in ((200, -4000), (150, -5200), (100, -4500), (50, -7900)):
        book(db, acc, back, cents, who)


def test_three_times_the_highest_amount_so_far_stands_out(db, settled):
    _usual(db, settled)
    tx = book(db, settled, 2, -48000, "Erfundener Händler")
    only = anomalies.find(db, TODAY)[0]
    assert (only["kind"], only["tx_id"], only["usual_max_cents"]) == ("high", tx, 7900)
    assert "480,00 €" in only["text"] and "höchstens 79,00 €" in only["text"]


def test_what_is_not_unusually_high(db, settled):
    _usual(db, settled)
    book(db, settled, 2, -20000, "Erfundener Händler")                      # nicht das Dreifache
    for back, cents in ((120, -500), (90, -600), (60, -700), (30, -800)):
        book(db, settled, back, cents, "Erfundener Bäcker")
    book(db, settled, 2, -2600, "Erfundener Bäcker")                        # dreifach, aber keine 50 € mehr
    book(db, settled, 100, -1000, "Erfundener Neuling")
    book(db, settled, 2, -90000, "Erfundener Neuling")                      # zu wenig Vorgeschichte
    assert kinds(db) == []
    _usual(db, settled, "Erfundene Stadtwerke")
    contract = book(db, settled, 2, -48000, "Erfundene Stadtwerke")
    db.execute("UPDATE transactions SET contract_key = 'x' WHERE id = ?", (contract,))
    assert kinds(db) == []  # bei Verträgen meldet sich die Preisänderung


# --- Ausblenden, Hinweise, Haushalt -------------------------------------------------------

def test_checked_booking_gets_no_further_notice(client, db, settled):
    first = book(db, settled, 3, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR)
    tx = book(db, settled, 2, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR)
    # Ein neuer Gläubiger, der gleich zweimal abbucht: die erste Lastschrift und die doppelte.
    assert kinds(db) == [("double", tx), ("debit", first)]
    assert client.post("/api/anomalies/ack", json={"key": f"anomaly:double:{tx}"}).status_code == 200
    assert client.post("/api/anomalies/ack", json={"key": f"anomaly:double:{tx}"}).status_code == 200
    assert kinds(db) == [("debit", first)]
    # Geprüft ist die Buchung: Auch unter einem anderen Hinweis kommt sie nicht wieder.
    assert client.post("/api/anomalies/ack", json={"key": f"anomaly:high:{first}"}).status_code == 200
    assert kinds(db) == []
    for bad in ("anomaly:double:x", "budget:1", "", None, 7):
        assert client.post("/api/anomalies/ack", json={"key": bad}).status_code == 400
    assert db.scalar("SELECT COUNT(*) FROM anomaly_acks") == 2


def test_anomalies_show_up_as_alerts_once(client, db, settled, monkeypatch):
    tx = book(db, settled, 2, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR)
    alerts = [a for a in client.get("/api/overview").json()["alerts"] if a["key"].startswith("anomaly:")]
    assert [(a["key"], a["level"], a["anomaly"]["tx_id"]) for a in alerts] == [(f"anomaly:debit:{tx}", "warning", tx)]
    sent = []
    monkeypatch.setattr(services.ha, "available", lambda: True)
    monkeypatch.setattr(services.ha, "_post", lambda path, body: sent.append((path, body.get("title", ""))) or True)
    services.refresh(db)
    services.refresh(db)
    assert [s for s in sent if "Lastschrift" in s[1]] == [
        ("/services/persistent_notification/create", "Kassensturz: Erste Lastschrift von Erfundenes Abo Ltd")]


def test_anomaly_is_an_event_for_automations(db, settled, monkeypatch):
    tx = book(db, settled, 2, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR)
    fired = []
    monkeypatch.setattr(services.ha, "available", lambda: True)
    monkeypatch.setattr(services.ha, "_post", lambda path, body: fired.append((path, body)) or True)
    services.refresh(db)
    services.refresh(db)
    events = [body for path, body in fired if path == "/events/kassensturz_auffaelligkeit"]
    until = (TODAY - timedelta(days=2) + timedelta(days=56)).isoformat()
    assert events == [{"art": "erste_lastschrift", "empfaenger": "Erfundenes Abo Ltd", "betrag": 29.9,
                       "konto": "KS-Testkonto", "datum": day(2), "rueckgabe_bis": until}]
    assert db.scalar("SELECT COUNT(*) FROM anomaly_acks") == 0 and tx


def test_notice_for_a_private_account_goes_to_its_owner(db):
    anna = household.create_person(db, {"name": "Anna"})["id"]
    household.update_person(db, anna, {"notify_service": "notify.mobile_app_anna"})
    ben = household.create_person(db, {"name": "Ben"})["id"]
    assert services._alert_service(db, {"owner_person_id": anna}, "notify.alle") == "notify.mobile_app_anna"
    assert services._alert_service(db, {"owner_person_id": ben}, "notify.alle") == "notify.alle"
    assert services._alert_service(db, {"owner_person_id": None}, "notify.alle") == "notify.alle"
    assert services._alert_service(db, {}, None) is None


def test_each_person_sees_only_what_is_on_their_accounts(db):
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    shared, private = account(db, "KS-Gemeinsam"), account(db, "KS-Anna", owner_person_id=anna)
    for acc in (shared, private):
        book(db, acc, 200, -1000, "Erfundener Altbestand")
    mine = book(db, private, 2, -2990, "Erfundenes Abo Ltd", creditor_id=CREDITOR)
    ours = book(db, shared, 2, -1990, "Erfundene Zeitung", creditor_id="DE11ZZZ00000000001")
    assert {a["tx_id"] for a in anomalies.find(db, TODAY)} == {mine, ours}
    assert {a["tx_id"] for a in anomalies.find(db.scoped(anna), TODAY)} == {mine, ours}
    assert {a["tx_id"] for a in anomalies.find(db.scoped(ben), TODAY)} == {ours}
    assert anomalies.find(db, TODAY)[0]["owner_person_id"] in (anna, None)


def test_pocket_money_and_archived_accounts_are_left_out(db):
    kid = household.create_person(db, {"name": "Mia", "is_child": True})["id"]
    pocket = db.insert("accounts", {"name": "KS-Taschengeld", "kind": "taschengeld", "owner_person_id": kid})
    old = account(db, "KS-Altkonto", archived=1)
    for acc in (pocket, old):
        book(db, acc, 200, -1000, "Erfundener Altbestand")
        book(db, acc, 3, -1500, "Erfundener Kiosk")
        book(db, acc, 2, -1500, "Erfundener Kiosk")
    assert kinds(db) == []
