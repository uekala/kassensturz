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
