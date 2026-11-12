"""Budgets aus der App setzen – nur erfundene Daten."""
from kassensturz.mobile_security import InMemoryRateLimiter
from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _category(db, name="Testkategorie", kind="expense"):
    return db.insert("categories", {"name": name, "kind": kind})


def test_set_change_and_remove_budget(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    cid = _category(db)
    with https_client() as client:
        headers = paired_headers(client)
        r = client.put(f"/api/v1/budgets/{cid}", json={"limit_cents": 30000}, headers=headers)
        assert r.status_code == 200
        assert r.json()["budget"] == {"category_id": cid, "name": "Testkategorie", "limit_cents": 30000}
        assert db.scalar("SELECT budget_cents FROM categories WHERE id = ?", (cid,)) == 30000

        listed = client.get("/api/v1/categories", headers=headers).json()["items"]
        assert next(c for c in listed if c["id"] == cid)["budget_cents"] == 30000

        overview = client.get("/api/v1/overview", headers=headers).json()
        assert any(b["category_id"] == cid and b["limit_cents"] == 30000 for b in overview["budgets"])

        r = client.put(f"/api/v1/budgets/{cid}", json={"limit_cents": None}, headers=headers)
        assert r.status_code == 200
        assert db.scalar("SELECT budget_cents FROM categories WHERE id = ?", (cid,)) is None


def test_budget_requests_are_validated(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    expense = _category(db)
    income = _category(db, "Testeinnahme", "income")
    with https_client() as client:
        headers = paired_headers(client)
        for body in ({"limit_cents": 0}, {"limit_cents": -5}, {"limit_cents": 10_000_001}, {"limit_cents": "100"},
                     {"limit_cents": 1.5}, {"limit_cents": True}, {}, {"limit_cents": 100, "name": "x"}):
            r = client.put(f"/api/v1/budgets/{expense}", json=body, headers=headers)
            assert r.status_code == 400, body
        assert client.put(f"/api/v1/budgets/{income}", json={"limit_cents": 100}, headers=headers).status_code == 400
        assert client.put("/api/v1/budgets/999999", json={"limit_cents": 100}, headers=headers).status_code == 404
        assert client.put("/api/v1/budgets/abc", json={"limit_cents": 100}, headers=headers).status_code == 404
        assert db.scalar("SELECT budget_cents FROM categories WHERE id = ?", (expense,)) is None


def test_budget_write_needs_a_paired_device(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    cid = _category(db)
    with https_client() as client:
        r = client.put(f"/api/v1/budgets/{cid}", json={"limit_cents": 100})
        assert r.status_code == 401
        r = client.put(f"/api/v1/budgets/{cid}", json={"limit_cents": 100}, headers={"Authorization": "Bearer falsch"})
        assert r.status_code == 401
        assert db.scalar("SELECT budget_cents FROM categories WHERE id = ?", (cid,)) is None


def test_budget_write_is_rate_limited(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    cid = _category(db)
    with https_client() as client:
        headers = paired_headers(client)
        codes = [client.put(f"/api/v1/budgets/{cid}", json={"limit_cents": 100 + i}, headers=headers).status_code
                 for i in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429
