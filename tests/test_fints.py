"""TAN-Ablauf mit nachgebauten Bankantworten. Ein echter Abruf gegen eine Test-Bank läuft in
test_fints_mock.py, sofern der Quellcode von python-fints mit seinem Test-Server vorliegt."""
import threading
import time

from fints.client import NeedTANResponse

from kassensturz import fints_sync


class FakeTAN(NeedTANResponse):
    def __init__(self, decoupled=False, challenge="Bitte TAN eingeben", hhduc=None):
        self.decoupled = decoupled
        self.challenge = challenge
        self.challenge_html = None
        self.challenge_matrix = None
        self.challenge_hhduc = hhduc


class FakeClient:
    def __init__(self, confirm_after=0):
        self.sent = []
        self.confirm_after = confirm_after

    def send_tan(self, res, tan):
        self.sent.append(tan)
        if res.decoupled and len(self.sent) <= self.confirm_after:
            return FakeTAN(decoupled=True)
        return ["ok"]


def _answer_when_asked(job, value):
    def run():
        for _ in range(100):
            if job.question:
                job.answer(value)
                return
            time.sleep(0.02)
    threading.Thread(target=run, daemon=True).start()


def test_tan_entry():
    job = fints_sync.Job(1, "Test")
    client = FakeClient()
    _answer_when_asked(job, " 123456 ")
    assert fints_sync._resolve(client, FakeTAN(), job, background=False) == ["ok"]
    assert client.sent == ["123456"]
    assert job.question is None


def test_decoupled_polls_until_confirmed(monkeypatch):
    job = fints_sync.Job(1, "Test")
    client = FakeClient(confirm_after=2)
    seen = []
    orig = job.wait_external

    def fast_wait(kind, payload, seconds):
        seen.append(kind)
        return orig(kind, payload, 0.01)

    monkeypatch.setattr(job, "wait_external", fast_wait)
    assert fints_sync._resolve(client, FakeTAN(decoupled=True), job, background=False) == ["ok"]
    assert seen == ["decoupled"] * 3 and client.sent == ["", "", ""]


def test_background_never_waits_for_tan():
    job = fints_sync.Job(1, "Test")
    try:
        fints_sync._resolve(FakeClient(), FakeTAN(), job, background=True)
    except fints_sync.UserFacingError as exc:
        assert "TAN" in str(exc)
    else:
        raise AssertionError("Hintergrund-Abruf darf nicht auf eine TAN warten")


def test_flicker_payload():
    payload = fints_sync._challenge_payload(FakeTAN(hhduc="0388A01239230520422,42"))
    assert payload["flicker"] and all(len(f) == 5 for f in payload["flicker"])


def test_missing_product_id_is_explained(db, monkeypatch):
    monkeypatch.delenv("KASSENSTURZ_FINTS_PRODUCT_ID", raising=False)
    cid = db.insert("connections", {"name": "Bank", "blz": "12345678", "login": "x", "server": "https://example.invalid/fints"})
    job = fints_sync.start(cid, "1234")
    for _ in range(100):
        if job.state not in ("running", "waiting"):
            break
        time.sleep(0.02)
    assert job.state == "error" and "Produkt-ID" in job.error


class FakeReply:
    def __init__(self, code, text):
        self.code, self.text, self.parameters = code, text, None


def _recording(replies):
    client = fints_sync._recording_client(replies)("12345678", "erfunden", "00000", "https://bank.invalid/fints",
                                                   product_id="ERFUNDEN")
    client._bootstrap_mode = True  # wie beim ersten Kontakt: Fehler brechen hier noch nicht ab
    return client


def test_bank_replies_are_recorded_and_explain_a_refused_login():
    """Erfundene Antworten: Scheitert die Anmeldung, steht der Grund der Bank in der Meldung."""
    replies = []
    client = _recording(replies)
    dialog = type("D", (), {"open": False})()
    for code, text in (("0020", "Auftrag ausgeführt"), ("3050", "Erfundene Warnung"),
                       ("9800", "Dialog   abgebrochen"), ("9800", "Dialog abgebrochen"), ("9330", "Erfundener Grund")):
        client._process_response(dialog, None, FakeReply(code, text))
    assert replies == [("0020", "Auftrag ausgeführt"), ("3050", "Erfundene Warnung"), ("9800", "Dialog abgebrochen"),
                       ("9330", "Erfundener Grund")]
    text = fints_sync._explain(ValueError("Could not find system_id"), replies)
    assert text.startswith("Die Bank hat die Anmeldung nicht angenommen. Antwort der Bank: Dialog abgebrochen (Code 9800); "
                           "Erfundener Grund (Code 9330).")
    assert "system_id" not in text and "nicht mehrfach" in text
    # Ohne Fehler der Bank zählen ihre Warnungen; ohne jede Antwort bleibt die Meldung ehrlich.
    assert "Erfundene Warnung (Code 3050)" in fints_sync._explain(ValueError("Could not find system_id"), replies[:2])
    assert "Einen Grund hat sie nicht genannt" in fints_sync._explain(ValueError("Could not find system_id"), [])
    assert fints_sync._explain(RuntimeError("anderes")) == "Abruf fehlgeschlagen: anderes"


def test_recorded_replies_stay_bounded():
    replies = []
    client = _recording(replies)
    dialog = type("D", (), {"open": True})()
    for i in range(60):
        client._process_response(dialog, None, FakeReply(f"30{i:02d}", "x" * 500))
    assert len(replies) == fints_sync.MAX_BANK_REPLIES and len(replies[-1][1]) == 160 and replies[-1][0] == "3059"


def test_1822direkt_gets_its_fints_bank_code_upper_case_login_and_no_customer_id():
    """Erfundene Zugangsdaten."""
    server = "https://fints.1822direkt.com/fints/hbci"
    assert fints_sync.bank_access({"blz": "500 502 01", "login": " 1234567a ", "customer_id": "1234567", "server": server}) == (
        "50050222", "1234567A", None)
    assert fints_sync.bank_access({"blz": "50050222", "login": "1234567A", "customer_id": None, "server": server}) == (
        "50050222", "1234567A", None)
    # Andere Banken bleiben, wie eingetragen.
    assert fints_sync.bank_access({"blz": "50050201", "login": "erfunden", "customer_id": " k1 ",
                                   "server": "https://bank.invalid/fints"}) == ("50050201", "erfunden", "k1")
    assert fints_sync.bank_access({"blz": "12030000", "login": "Erfunden", "customer_id": "", "server": None}) == (
        "12030000", "Erfunden", None)


def test_code_9210_says_what_to_check():
    replies = [("9800", "Dialoginitialisierung abgebrochen."), ("9210", "Benutzer für Kunden nicht bevollmächtigt.")]
    text = fints_sync._explain(ValueError("Could not find system_id"), replies)
    assert text.startswith("Die Bank kennt diesen Zugang nicht. Antwort der Bank:") and "Code 9210" in text
    assert "Bankleitzahl" in text and "Kundennummer" in text and "system_id" not in text
    assert fints_sync._explain(fints_sync.UserFacingError("Eigene Meldung"), replies) == "Eigene Meldung"


def test_code_9078_explains_the_waiting_time():
    replies = [("9800", "Dialoginitialisierung abgebrochen."), ("9078", "Dialog abgebrochen - FinTS-Produkt ist nicht registriert")]
    text = fints_sync._explain(ValueError("Could not find system_id"), replies)
    assert text.startswith("Die Bank kennt die FinTS-Produkt-ID noch nicht (Code 9078).") and "25 Zeichen" in text


def test_code_9900_names_login_data_not_the_product():
    replies = [("9800", "Dialoginitialisierung abgebrochen."), ("9900", "Es ist ein Fehler bei der Anmeldung aufgetreten.")]
    text = fints_sync._explain(ValueError("Could not find system_id"), replies)
    assert text.startswith("Die Bank hat die Anmeldung abgelehnt. Antwort der Bank:") and "Code 9900" in text
    assert "Anmeldename oder PIN" in text and "nicht mehr von selbst" in text and "9078" not in text


def _fail_with(monkeypatch, exc, replies):
    def fake_sync(job, conn, pin, history_days, background):
        job.bank_replies.extend(replies)
        raise exc
    monkeypatch.setattr(fints_sync, "_sync", fake_sync)


def _wait(job):
    for _ in range(200):
        if job.state not in ("running", "waiting"):
            return job
        time.sleep(0.01)
    raise AssertionError("Auftrag läuft noch")


def test_rejected_login_stops_automatic_fetches(db, monkeypatch, tmp_path):
    import pytest

    from kassensturz import banksync, secrets_store, services

    cid = db.insert("connections", {"name": "KS-Testbank", "blz": "00000000", "login": "erfunden",
                                    "server": "https://example.invalid/fints", "created": "2026-01-01"})
    pins = {cid: "erfundene-pin"}
    monkeypatch.setattr(secrets_store, "has_pin", lambda c: c in pins)
    monkeypatch.setattr(secrets_store, "get_pin", lambda c: pins.get(c))
    monkeypatch.setattr(secrets_store, "set_pin", lambda c, p: pins.__setitem__(c, p))
    _fail_with(monkeypatch, ValueError("Could not find system_id"),
               [("9800", "Dialoginitialisierung abgebrochen."), ("9900", "Fehler bei der Anmeldung.")])

    _wait(fints_sync.start(cid, None, background=True))
    assert fints_sync.login_rejected(db, cid)
    source = next(s for s in banksync.status(db)["sources"] if s["id"] == f"fints:{cid}")
    assert (source["automatic"], source["state"]) == (False, "error")

    # Weder der tägliche Abruf noch ein Abruf mit der gespeicherten PIN versucht es noch einmal.
    started = []
    real_start = fints_sync.start
    monkeypatch.setattr(fints_sync, "start", lambda *a, **k: started.append(a) or real_start(*a, **k))
    services.run_daily_sync()
    assert started == []
    with pytest.raises(fints_sync.UserFacingError, match="letzte Anmeldung abgelehnt"):
        real_start(cid, None)

    # Ein Erfolg mit eingegebener, aber nicht gespeicherter PIN hebt die Sperre nicht auf.
    monkeypatch.setattr(fints_sync, "_sync", lambda job, conn, pin, h, b: {"added": 0})
    _wait(real_start(cid, "andere-erfundene-pin"))
    assert fints_sync.login_rejected(db, cid)
    # Gespeichert und erfolgreich: wieder automatisch.
    _wait(real_start(cid, "andere-erfundene-pin", save_pin=True))
    assert fints_sync.login_rejected(db, cid) is None

    # Andere Fehler (Produkt-ID unbekannt, Server weg) halten nichts an.
    _fail_with(monkeypatch, ValueError("Could not find system_id"), [("9078", "FinTS-Produkt ist nicht registriert")])
    _wait(real_start(cid, None))
    assert fints_sync.login_rejected(db, cid) is None


def test_changing_login_data_lifts_the_stop(client, db):
    cid = db.insert("connections", {"name": "KS-Testbank", "blz": "00000000", "login": "erfunden",
                                    "server": "https://example.invalid/fints", "created": "2026-01-01"})
    db.set_setting(f"fints_login_rejected:{cid}", "2026-11-18T20:47:59")
    listed = next(c for c in client.get("/api/connections").json() if c["id"] == cid)
    assert listed["login_rejected"] is True
    client.patch(f"/api/connections/{cid}", json={"name": "KS-Umbenannt"})
    assert fints_sync.login_rejected(db, cid)
    client.patch(f"/api/connections/{cid}", json={"login": "erfunden2"})
    assert fints_sync.login_rejected(db, cid) is None
