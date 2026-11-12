import sqlite3

from fastapi.testclient import TestClient

from kassensturz import main
from kassensturz.db import Database
from kassensturz.ledger import import_rows
from kassensturz.mobile_security import InMemoryRateLimiter

REQUEST_ID = "5b0f6c1e-7d0a-4a55-9a0e-2f7f5a3f9c11"


def https_client(peer="127.0.0.1"):
    return TestClient(main.app, base_url="https://testserver", client=(peer, 50123))


def reset_mobile_guards(monkeypatch):
    monkeypatch.setattr(main, "MOBILE_RATE_LIMITER", InMemoryRateLimiter())
    monkeypatch.setattr(main, "TRUSTED_PROXY_NETWORKS", ())
    monkeypatch.setattr(main, "MOBILE_CLIENT_NETWORKS", ())


def paired_headers(client):
    secret = client.post("/api/mobile/pairings").json()["pairing_secret"]
    paired = client.post(
        "/api/v1/pair",
        json={"pairing_secret": secret, "device_name": "Testgerät"},
    )
    assert paired.status_code == 201
    return {"Authorization": f"Bearer {paired.json()['access_token']}"}


def cash_account(db, **extra):
    return db.insert("accounts", {"name": "Bargeld", "kind": "cash", **extra})


def bank_account(db):
    connection_id = db.insert(
        "connections",
        {"name": "Musterbank", "blz": "10000000", "login": "x", "server": "https://example.invalid"},
    )
    return db.insert(
        "accounts",
        {
            "name": "Girokonto",
            "kind": "giro",
            "iban": "DE89370400440532013000",
            "connection_id": connection_id,
        },
    )


def new_payload(account_id, **overrides):
    payload = {
        "client_request_id": REQUEST_ID,
        "account_id": account_id,
        "booking_date": "2026-11-09",
        "amount_cents": -450,
        "counterparty": "KS-MOBILTEST Bäckerei",
        "purpose": "Brötchen",
    }
    payload.update(overrides)
    return payload


def test_write_routes_require_a_device_token(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = cash_account(db)
    with https_client() as client:
        assert client.post("/api/v1/transactions", json=new_payload(account_id)).status_code == 401
        assert client.patch("/api/v1/transactions/1", json={"note": "x"}).status_code == 401
        assert client.delete("/api/v1/transactions/1").status_code == 401
        for path in ("/api/v1/accounts", "/api/v1/categories", "/api/v1/contracts"):
            assert client.get(path).status_code == 401
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 0


def test_create_manual_transaction_updates_balance_and_is_listed(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = cash_account(db, balance_cents=10000, balance_date="2026-11-01")
    with https_client() as client:
        headers = paired_headers(client)
        created = client.post("/api/v1/transactions", json=new_payload(account_id), headers=headers)
        assert created.status_code == 201
        body = created.json()
        assert body["created"] is True
        transaction = body["transaction"]
        assert transaction["manual"] is True
        assert transaction["amount_cents"] == -450
        assert transaction["account_id"] == account_id
        assert transaction["category"] is not None

        accounts = client.get("/api/v1/accounts", headers=headers).json()["items"]
        assert accounts == [
            {
                "id": account_id,
                "name": "Bargeld",
                "type": "cash",
                "currency": "EUR",
                "balance_cents": 9550,
                "balance_known": True,
                "balance_date": "2026-11-01",
                "transaction_count": 1,
                "manual_entries": True,
            }
        ]

        listed = client.get("/api/v1/transactions", headers=headers).json()
        assert listed["total"] == 1
        assert listed["items"][0]["id"] == transaction["id"]
        assert listed["items"][0]["manual"] is True

        stored = db.one("SELECT source, hash, client_request_id FROM transactions")
        assert stored["source"] == "manual"
        assert stored["hash"]
        assert stored["client_request_id"] == REQUEST_ID


def test_repeating_the_same_request_id_does_not_book_twice(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = cash_account(db)
    with https_client() as client:
        headers = paired_headers(client)
        first = client.post("/api/v1/transactions", json=new_payload(account_id), headers=headers)
        again = client.post("/api/v1/transactions", json=new_payload(account_id), headers=headers)
        changed = client.post(
            "/api/v1/transactions",
            json=new_payload(account_id, amount_cents=-99999),
            headers=headers,
        )
        assert first.status_code == 201
        assert again.status_code == 200 and again.json()["created"] is False
        assert changed.status_code == 200
        assert again.json()["transaction"] == first.json()["transaction"]
        assert changed.json()["transaction"]["amount_cents"] == -450
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 1


def test_request_id_is_unique_in_the_database(db):
    account_id = cash_account(db)
    row = {
        "account_id": account_id,
        "booking_date": "2026-11-09",
        "amount_cents": -1,
        "client_request_id": REQUEST_ID,
    }
    db.insert("transactions", row)
    try:
        db.insert("transactions", row)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("duplicate request id was accepted")
    # Imported rows without a request id are unaffected by the unique index.
    db.insert("transactions", {"account_id": account_id, "booking_date": "2026-11-09", "amount_cents": -1})
    db.insert("transactions", {"account_id": account_id, "booking_date": "2026-11-09", "amount_cents": -1})


def test_accounts_with_bank_feed_reject_manual_transactions(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    fints_account = bank_account(db)
    open_banking_account = db.insert("accounts", {"name": "Neobank", "kind": "giro", "eb_session_id": 7})
    archived = cash_account(db, archived=1)
    with https_client() as client:
        headers = paired_headers(client)
        for index, account_id in enumerate((fints_account, open_banking_account)):
            response = client.post(
                "/api/v1/transactions",
                json=new_payload(account_id, client_request_id=f"{REQUEST_ID}-{index}"),
                headers=headers,
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "account_not_manual"
        gone = client.post(
            "/api/v1/transactions",
            json=new_payload(archived, client_request_id=f"{REQUEST_ID}-a"),
            headers=headers,
        )
        assert gone.status_code == 400
        flags = {
            item["id"]: item["manual_entries"]
            for item in client.get("/api/v1/accounts", headers=headers).json()["items"]
        }
        assert flags == {fints_account: False, open_banking_account: False}
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 0


def test_create_rejects_invalid_input_without_writing(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = cash_account(db)
    bad = (
        {"amount_cents": 0},
        {"amount_cents": 12.5},
        {"amount_cents": "100"},
        {"amount_cents": True},
        {"amount_cents": 10**12},
        {"booking_date": "09.11.2026"},
        {"booking_date": "2026-02-30"},
        {"booking_date": "1990-01-01"},
        {"counterparty": "   "},
        {"counterparty": "x" * 101},
        {"client_request_id": "short"},
        {"client_request_id": "has spaces in the request id"},
        {"account_id": 99999},
        {"account_id": "1"},
        {"category_id": 99999},
        {"iban": "DE89370400440532013000"},
    )
    with https_client() as client:
        headers = paired_headers(client)
        for overrides in bad:
            response = client.post(
                "/api/v1/transactions",
                json={**new_payload(account_id), **overrides},
                headers=headers,
            )
            assert response.status_code == 400, overrides
            assert response.json()["error"]["code"] == "invalid_request"
        not_an_object = client.post("/api/v1/transactions", json=[1, 2], headers=headers)
        assert not_an_object.status_code == 400
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 0


def test_manual_transaction_can_be_changed_and_deleted(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = cash_account(db)
    category_id = db.insert("categories", {"name": "Geschenke", "kind": "expense"})
    with https_client() as client:
        headers = paired_headers(client)
        tx_id = client.post(
            "/api/v1/transactions", json=new_payload(account_id), headers=headers
        ).json()["transaction"]["id"]
        old_hash = db.scalar("SELECT hash FROM transactions WHERE id = ?", (tx_id,))

        updated = client.patch(
            f"/api/v1/transactions/{tx_id}",
            json={
                "amount_cents": -990,
                "booking_date": "2026-11-08",
                "counterparty": "KS-MOBILTEST Blumen",
                "purpose": None,
                "category_id": category_id,
                "note": "korrigiert",
            },
            headers=headers,
        )
        assert updated.status_code == 200
        transaction = updated.json()["transaction"]
        assert transaction["amount_cents"] == -990
        assert transaction["booking_date"] == "2026-11-08"
        assert transaction["purpose"] is None
        assert transaction["note"] == "korrigiert"
        assert transaction["category"] == {"id": category_id, "name": "Geschenke"}
        assert db.scalar("SELECT hash FROM transactions WHERE id = ?", (tx_id,)) != old_hash
        assert db.scalar("SELECT category_locked FROM transactions WHERE id = ?", (tx_id,)) == 1

        db.insert("splits", {"tx_id": tx_id, "amount_cents": -100, "category_id": category_id})
        deleted = client.delete(f"/api/v1/transactions/{tx_id}", headers=headers)
        assert deleted.status_code == 200
        assert client.delete(f"/api/v1/transactions/{tx_id}", headers=headers).status_code == 404
        assert client.patch(
            f"/api/v1/transactions/{tx_id}", json={"note": "x"}, headers=headers
        ).status_code == 404
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 0
        assert db.scalar("SELECT COUNT(*) FROM splits") == 0


def test_bank_transactions_keep_their_data_and_cannot_be_deleted(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = bank_account(db)
    category_id = db.insert("categories", {"name": "Lebensmittel", "kind": "expense"})
    tx_id = db.insert(
        "transactions",
        {
            "account_id": account_id,
            "booking_date": "2026-11-03",
            "amount_cents": -1234,
            "counterparty": "Supermarkt",
            "purpose": "Kartenzahlung",
            "hash": "bank-hash",
            "source": "fints",
        },
    )
    with https_client() as client:
        headers = paired_headers(client)
        assert client.delete(f"/api/v1/transactions/{tx_id}", headers=headers).status_code == 409
        for field, value in (
            ("amount_cents", -1),
            ("booking_date", "2026-11-04"),
            ("counterparty", "Anders"),
            ("purpose", "Anders"),
        ):
            response = client.patch(
                f"/api/v1/transactions/{tx_id}", json={field: value}, headers=headers
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "not_editable"
        allowed = client.patch(
            f"/api/v1/transactions/{tx_id}",
            json={"category_id": category_id, "note": "Wocheneinkauf"},
            headers=headers,
        )
        assert allowed.status_code == 200
        assert allowed.json()["transaction"]["manual"] is False
        unknown = client.patch(
            f"/api/v1/transactions/{tx_id}", json={"hash": "x"}, headers=headers
        )
        assert unknown.status_code == 400
        for bad_id in ("abc", "0", "-1", "1e3", "9" * 30):
            assert client.patch(
                f"/api/v1/transactions/{bad_id}", json={"note": "x"}, headers=headers
            ).status_code == 404
        row = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        assert (row["amount_cents"], row["booking_date"], row["counterparty"], row["hash"], row["source"]) == (
            -1234, "2026-11-03", "Supermarkt", "bank-hash", "fints",
        )
        assert row["category_id"] == category_id and row["note"] == "Wocheneinkauf"


def test_later_file_import_does_not_duplicate_a_manual_transaction(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = cash_account(db)
    with https_client() as client:
        headers = paired_headers(client)
        assert client.post(
            "/api/v1/transactions", json=new_payload(account_id), headers=headers
        ).status_code == 201
        result = import_rows(
            db,
            account_id,
            [
                {"booking_date": "2026-11-09", "amount_cents": -450, "counterparty": "BAECKEREI 123", "purpose": "Karte"},
                {"booking_date": "2026-11-09", "amount_cents": -700, "counterparty": "Kiosk", "purpose": ""},
            ],
            source="csv",
        )
        assert result["added"] == 1 and result["skipped"] == 1
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 2


def test_categories_and_contracts_are_allowlisted(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = bank_account(db)
    db.insert(
        "contracts",
        {
            "key": "manual:strom",
            "name": "Strom",
            "kind": "expense",
            "interval": "monthly",
            "amount_cents": -6500,
            "status": "confirmed",
            "manual": 1,
            "account_id": account_id,
            "customer_no": "KD-4711",
            "provider_email": "kontakt@example.invalid",
            "provider_address": "Musterweg 1",
            "notes": "privat",
        },
    )
    db.insert("contracts", {"key": "manual:alt", "name": "Alt", "status": "ignored", "manual": 1, "amount_cents": -1})
    with https_client() as client:
        headers = paired_headers(client)
        categories = client.get("/api/v1/categories", headers=headers).json()["items"]
        contracts = client.get("/api/v1/contracts", headers=headers).json()
    assert categories and set(categories[0]) == {"id", "name", "parent_id", "kind", "color", "budget_cents"}
    names = [item["name"] for item in contracts["items"]]
    assert "Strom" in names and "Alt" not in names
    strom = next(item for item in contracts["items"] if item["name"] == "Strom")
    assert set(strom) == {
        "key", "name", "kind", "interval", "amount_cents", "monthly_cents", "next_due", "status",
        "running", "category_name", "account_name", "cancellation_deadline",
    }
    serialized = repr(contracts)
    for forbidden in ("KD-4711", "example.invalid", "Musterweg", "privat", "DE8937"):
        assert forbidden not in serialized


def test_write_routes_are_rate_limited_before_dispatch(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    monkeypatch.setitem(main.MOBILE_RATE_LIMITS, ("POST", "/api/v1/transactions"), ("transaction-write", 2, 60))
    account_id = cash_account(db)
    with https_client() as client:
        headers = paired_headers(client)
        codes = [
            client.post(
                "/api/v1/transactions",
                json=new_payload(account_id, client_request_id=f"{REQUEST_ID}-{index}"),
                headers=headers,
            ).status_code
            for index in range(3)
        ]
        assert codes == [201, 201, 429]
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 2


def test_request_id_column_is_added_to_an_existing_database(tmp_path):
    path = tmp_path / "legacy.sqlite"
    legacy = sqlite3.connect(path)
    legacy.execute(
        "CREATE TABLE transactions(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, "
        "booking_date TEXT NOT NULL, amount_cents INTEGER NOT NULL, hash TEXT, source TEXT)"
    )
    legacy.execute(
        "INSERT INTO transactions(account_id, booking_date, amount_cents, hash, source) "
        "VALUES (1, '2026-10-01', -500, 'keep-me', 'fints')"
    )
    legacy.commit()
    legacy.close()

    migrated = Database(path)
    row = migrated.one("SELECT * FROM transactions")
    assert row["hash"] == "keep-me" and row["amount_cents"] == -500 and row["source"] == "fints"
    assert row["client_request_id"] is None
    # Opening twice must stay idempotent.
    assert Database(path).scalar("SELECT COUNT(*) FROM transactions") == 1


def test_transaction_list_accepts_search_and_kind_over_the_api(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    account_id = cash_account(db)
    for cents, name in ((-450, "Bäckerei"), (-700, "Kiosk"), (2000, "Flohmarkt")):
        db.insert("transactions", {
            "account_id": account_id, "booking_date": "2026-11-09", "amount_cents": cents, "counterparty": name,
        })
    with https_client() as client:
        headers = paired_headers(client)
        found = client.get("/api/v1/transactions", params={"q": "kiosk"}, headers=headers)
        income = client.get("/api/v1/transactions", params={"kind": "in"}, headers=headers)
        invalid = client.get("/api/v1/transactions", params={"kind": "alles"}, headers=headers)
        unauthenticated = client.get("/api/v1/transactions", params={"q": "kiosk"})
        capabilities = client.get("/api/v1/me", headers=headers).json()["capabilities"]

    assert [item["counterparty"] for item in found.json()["items"]] == ["Kiosk"]
    assert [item["counterparty"] for item in income.json()["items"]] == ["Flohmarkt"]
    assert invalid.status_code == 400 and invalid.json()["error"]["code"] == "invalid_query"
    assert unauthenticated.status_code == 401
    assert "transactions.search" in capabilities


def test_stats_endpoint_needs_a_device_and_validates_the_month(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    cash_account(db)
    with https_client() as client:
        headers = paired_headers(client)
        ok = client.get("/api/v1/stats", headers=headers)
        invalid = client.get("/api/v1/stats", params={"month": "bald"}, headers=headers)
        unauthenticated = client.get("/api/v1/stats")
        capabilities = client.get("/api/v1/me", headers=headers).json()["capabilities"]

    assert ok.status_code == 200
    assert set(ok.json()) == {"month", "categories", "history", "balance_curve"}
    assert invalid.status_code == 400 and invalid.json()["error"]["code"] == "invalid_query"
    assert unauthenticated.status_code == 401
    assert "stats" in capabilities
