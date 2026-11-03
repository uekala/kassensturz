"""Nachgebaute Enable-Banking-API für Tests: prüft das JWT und spielt eine N26-Freigabe durch."""
import json
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

APP_ID = "11111111-2222-3333-4444-555555555555"
IBAN = "DE89100110012626000001"


def make_key() -> tuple[str, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return pem, key.public_key()


class Bank:
    def __init__(self, public_key):
        self.public_key = public_key
        self.states = {}
        self.sessions = {}
        self.expired = False
        self.history_limit_days = 90   # ältere Umsätze nur direkt nach der Freigabe
        self.fresh = set()
        self.always_limit = False
        self.requests = []
        self.code_counter = 0
        today = date.today()
        self.txs = [
            {"entry_reference": f"r{i}", "transaction_amount": {"amount": f"{10 + i}.50", "currency": "EUR"},
             "credit_debit_indicator": "DBIT", "status": "BOOK", "booking_date": (today - timedelta(days=i * 20)).isoformat(),
             "value_date": (today - timedelta(days=i * 20)).isoformat(), "creditor": {"name": "REWE Markt GmbH"},
             "remittance_information": ["Kartenzahlung"], "bank_transaction_code": {"description": "Presentment"}}
            for i in range(8)
        ] + [
            {"entry_reference": "sal", "transaction_amount": {"amount": "3450.12", "currency": "EUR"}, "credit_debit_indicator": "CRDT",
             "status": "BOOK", "booking_date": (today - timedelta(days=5)).isoformat(), "debtor": {"name": "Muster Systemhaus GmbH"},
             "debtor_account": {"iban": "DE44500105175407324931"}, "remittance_information": ["Gehalt"]},
            {"entry_reference": "card", "transaction_amount": {"amount": "4.80", "currency": "EUR"}, "credit_debit_indicator": "DBIT",
             "status": "BOOK", "booking_date": (today - timedelta(days=2)).isoformat(), "remittance_information": ["Starbucks Berlin", "Kartenzahlung"]},
            {"entry_reference": "pend", "transaction_amount": {"amount": "9.99", "currency": "EUR"}, "credit_debit_indicator": "DBIT",
             "status": "PDNG", "booking_date": today.isoformat(), "creditor": {"name": "Netflix"}},
            {"entry_reference": "usd", "transaction_amount": {"amount": "5.00", "currency": "USD"}, "credit_debit_indicator": "DBIT",
             "status": "BOOK", "booking_date": today.isoformat(), "creditor": {"name": "Steam"}},
        ]


def start(bank: Bank):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _auth(self) -> bool:
            token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            try:
                hdr = jwt.get_unverified_header(token)
                jwt.decode(token, bank.public_key, algorithms=["RS256"], audience="api.enablebanking.com", issuer="enablebanking.com")
                if hdr.get("kid") != APP_ID:
                    raise ValueError("kid")
            except Exception:  # noqa: BLE001
                self._send(401, {"code": 401, "message": "Invalid JWT"})
                return False
            return True

        def _send(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if not self._auth():
                return
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            bank.requests.append(("GET", u.path, q, dict(self.headers)))
            if u.path == "/application":
                return self._send(200, {"name": "Kassensturz", "kid": APP_ID, "environment": "PRODUCTION", "active": True})
            if u.path == "/aspsps":
                return self._send(200, {"aspsps": [
                    {"name": "N26", "country": "DE", "maximum_consent_validity": 15552000, "psu_types": ["personal", "business"]},
                    {"name": "PayPal", "country": "DE", "maximum_consent_validity": 7776000, "psu_types": ["personal"]},
                ]})
            if u.path.startswith("/accounts/acc-1/"):
                if bank.expired:
                    return self._send(422, {"code": 422, "error": "EXPIRED_SESSION", "message": "Session is expired"})
                if u.path.endswith("/balances"):
                    return self._send(200, {"balances": [
                        {"balance_type": "ITAV", "balance_amount": {"amount": "1000.00", "currency": "EUR"}},
                        {"balance_type": "CLBD", "balance_amount": {"amount": "1234.56", "currency": "EUR"},
                         "reference_date": date.today().isoformat()},
                    ]})
                if u.path.endswith("/transactions"):
                    dfrom = date.fromisoformat(q["date_from"])
                    if (date.today() - dfrom).days > bank.history_limit_days and (bank.always_limit or "acc-1" not in bank.fresh):
                        return self._send(422, {"code": 422, "error": "WRONG_TRANSACTIONS_PERIOD", "message": "Period too long"})
                    rows = [t for t in bank.txs if date.fromisoformat(t["booking_date"]) >= dfrom]
                    if q.get("continuation_key") == "p2":
                        return self._send(200, {"transactions": rows[6:], "continuation_key": None})
                    return self._send(200, {"transactions": rows[:6], "continuation_key": "p2" if len(rows) > 6 else None})
            return self._send(404, {"code": 404, "message": "not found"})

        def do_POST(self):
            if not self._auth():
                return
            u = urlparse(self.path)
            body = self._body()
            bank.requests.append(("POST", u.path, body, dict(self.headers)))
            if u.path == "/auth":
                assert body["aspsp"]["name"] and body["access"]["valid_until"] and body["redirect_url"] and body["psu_type"]
                bank.states[body["state"]] = body
                return self._send(200, {"url": f"https://bank.example/consent?state={body['state']}", "authorization_id": "a1"})
            if u.path == "/sessions":
                if not body.get("code", "").startswith("good"):
                    return self._send(422, {"code": 422, "error": "INVALID_CODE", "message": "Code invalid"})
                bank.code_counter += 1
                sid = f"sess-{bank.code_counter}"
                bank.sessions[sid] = True
                bank.expired = False
                bank.fresh.add("acc-1")
                vu = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
                return self._send(200, {"session_id": sid, "aspsp": {"name": "N26", "country": "DE"}, "psu_type": "personal",
                                        "access": {"valid_until": vu},
                                        "accounts": [{"uid": "acc-1", "account_id": {"iban": IBAN}, "name": "Hauptkonto",
                                                      "currency": "EUR", "cash_account_type": "CACC", "identification_hash": "hash-1"}]})
            return self._send(404, {"code": 404})

        def do_DELETE(self):
            if not self._auth():
                return
            u = urlparse(self.path)
            bank.requests.append(("DELETE", u.path, None, dict(self.headers)))
            bank.sessions.pop(u.path.rsplit("/", 1)[-1], None)
            return self._send(200, {})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
