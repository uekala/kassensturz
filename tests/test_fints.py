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
