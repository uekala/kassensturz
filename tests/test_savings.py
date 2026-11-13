"""Rücklage für Jahreskosten und Sparziele – nur erfundene Daten."""
from datetime import date

from kassensturz import analytics, ledger, savings


def _contract(**extra):
    base = {"key": "manual:versicherung", "name": "Erfundene Versicherung", "kind": "expense", "interval": "jährlich",
            "amount_cents": -60000, "next_due": "2027-05-01", "status": "confirmed", "active": 1, "manual": 1}
    base.update(extra)
    return base


def test_reserve_spreads_rare_payments_over_their_interval():
    today, period_end = date(2026, 11, 1), date(2026, 11, 27)
    result = savings.reserve([
        _contract(),                                                            # 600 € im Jahr, 6 von 12 Monaten vorbei
        _contract(key="k2", name="Quartal", interval="vierteljährlich", amount_cents=-9000, next_due="2026-12-01"),
        _contract(key="k3", name="Monatlich", interval="monatlich", next_due="2026-12-01"),
        _contract(key="k4", name="Bald", next_due="2026-11-20"),                # steckt schon in den festen Abbuchungen
        _contract(key="k5", name="Gekündigt", status="cancelled", cancel_effective="2026-10-01"),
        _contract(key="k6", name="Einnahme", kind="income", amount_cents=60000),
    ], today, period_end)

    assert [i["name"] for i in result["items"]] == ["Quartal", "Erfundene Versicherung"]
    quartal, yearly = result["items"]
    assert yearly["monthly_cents"] == 5000 and 29800 <= yearly["reserved_cents"] <= 30400
    assert quartal["monthly_cents"] == 3000 and 5900 <= quartal["reserved_cents"] <= 6100
    assert result["monthly_cents"] == 8000
    assert result["reserved_cents"] == yearly["reserved_cents"] + quartal["reserved_cents"]


def test_reserve_is_shown_always_but_deducted_only_on_request(client, db):
    acc = client.post("/api/accounts", json={"name": "Testgiro", "kind": "giro"}).json()["id"]
    client.post(f"/api/accounts/{acc}/balance", json={"balance_cents": 300000, "date": date.today().isoformat()})
    due = ledger_date_in(200)
    db.insert("contracts", {**_contract(next_due=due), "account_id": acc})

    before = analytics.forecast(db)
    assert before["reserve_cents"] > 0 and before["reserve_deducted"] is False

    client.put("/api/settings", json={"deduct_reserve": True})
    after = analytics.forecast(db)
    assert after["reserve_deducted"] is True
    assert after["free_cents"] == before["free_cents"] - before["reserve_cents"]
    assert client.get("/api/settings").json()["deduct_reserve"] is True
    plan = client.get("/api/goals").json()
    assert plan["reserve"]["deducted"] is True and plan["reserve"]["monthly_cents"] == 5000


def ledger_date_in(days):
    from datetime import timedelta
    return (date.today() + timedelta(days=days)).isoformat()


def test_goal_with_manual_progress_and_monthly_rate(client, db):
    r = client.post("/api/goals", json={"name": "  Test   Urlaub ", "target_cents": 240000, "saved_cents": 60000,
                                        "due_date": "2027-05-15"})
    assert r.status_code == 200
    goal = savings.list_goals(db, date(2026, 11, 13))[0]
    assert goal["name"] == "Test Urlaub" and goal["saved_cents"] == 60000 and goal["rest_cents"] == 180000
    assert goal["monthly_cents"] == 25715          # 1.800 € in 7 Monaten, aufgerundet
    assert goal["status"] == "open" and goal["progress"] == 0.25

    client.patch(f"/api/goals/{goal['id']}", json={"saved_cents": 240000})
    done = savings.list_goals(db, date(2026, 11, 13))[0]
    assert done["status"] == "done" and done["monthly_cents"] is None

    client.patch(f"/api/goals/{goal['id']}", json={"saved_cents": 1000, "due_date": "2026-01-01"})
    assert savings.list_goals(db, date(2026, 11, 13))[0]["status"] == "late"


def test_goals_on_one_account_share_its_balance_in_order(client, db):
    acc = client.post("/api/accounts", json={"name": "Test-Tagesgeld", "kind": "tagesgeld"}).json()["id"]
    client.post(f"/api/accounts/{acc}/balance", json={"balance_cents": 500000, "date": "2026-11-01"})
    client.post("/api/goals", json={"name": "Notgroschen", "target_cents": 300000, "account_id": acc})
    client.post("/api/goals", json={"name": "Auto", "target_cents": 1000000, "account_id": acc})
    first, second = savings.list_goals(db)
    assert (first["saved_cents"], first["status"]) == (300000, "done")
    assert (second["saved_cents"], second["rest_cents"]) == (200000, 800000)
    assert first["account_name"] == "Test-Tagesgeld" and first["linked"] is True

    client.delete(f"/api/accounts/{acc}")
    assert [g["account_id"] for g in savings.list_goals(db)] == [None, None]


def test_goal_requests_are_validated(client, db):
    for body in ({"name": "", "target_cents": 100}, {"name": "X", "target_cents": 0}, {"name": "X", "target_cents": "viel"},
                 {"name": "X", "target_cents": 100, "due_date": "bald"}, {"name": "X", "target_cents": 100, "account_id": 999},
                 {"name": "X", "target_cents": 100, "saved_cents": -5}):
        assert client.post("/api/goals", json=body).status_code == 400, body
    assert client.patch("/api/goals/999", json={"name": "X"}).status_code == 404
    gid = client.post("/api/goals", json={"name": "X", "target_cents": 100}).json()["id"]
    assert client.delete(f"/api/goals/{gid}").status_code == 200
    assert savings.list_goals(db) == []


def test_mobile_overview_carries_goals_and_reserve(client, db):
    from kassensturz import mobile_read

    client.post("/api/goals", json={"name": "Test Urlaub", "target_cents": 100000, "saved_cents": 25000})
    overview = mobile_read.get_overview(db)
    assert overview["goals"] == [{"id": 1, "name": "Test Urlaub", "target_cents": 100000, "saved_cents": 25000,
                                  "rest_cents": 75000, "due_date": None, "monthly_cents": None, "status": "open",
                                  "progress": 0.25}]
    assert set(overview["forecast"]["reserve"]) == {"reserved_cents", "monthly_cents", "deducted", "items"}
