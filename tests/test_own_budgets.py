"""Eigene Budgets je Person neben den gemeinsamen – nur erfundene Daten."""
from datetime import date

import pytest

from kassensturz import analytics, household
from test_household import pair
from test_mobile_write import https_client, reset_mobile_guards

TODAY = date.today().isoformat()


def spend(db, account_id, cents, category_id, who):
    return db.insert("transactions", {
        "account_id": account_id, "booking_date": TODAY, "amount_cents": -cents, "counterparty": who,
        "category_id": category_id, "source": "manual", "created": TODAY})


@pytest.fixture()
def home(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    food = db.scalar("SELECT id FROM categories WHERE kind = 'expense' AND parent_id IS NULL ORDER BY id LIMIT 1")
    fun = db.scalar("SELECT id FROM categories WHERE kind = 'expense' AND parent_id IS NULL ORDER BY id LIMIT 1 OFFSET 1")
    shared = db.insert("accounts", {"name": "KS-GEMEINSAM Kasse", "kind": "cash"})
    mine = db.insert("accounts", {"name": "KS-ANNA Kasse", "kind": "cash", "owner_person_id": anna})
    his = db.insert("accounts", {"name": "KS-BEN Kasse", "kind": "cash", "owner_person_id": ben})
    spend(db, shared, 10000, food, "KS-GEMEINSAM Markt")
    spend(db, mine, 3000, food, "KS-ANNA Imbiss")
    spend(db, his, 700, food, "KS-BEN Kiosk")
    spend(db, mine, 2500, fun, "KS-ANNA Kino")
    db.update("categories", "id", food, {"budget_cents": 40000})
    return {"db": db, "anna": anna, "ben": ben, "food": food, "fun": fun}


def test_household_budget_counts_shared_accounts_and_own_budget_own_accounts(home):
    db, anna, ben, food, fun = (home[k] for k in ("db", "anna", "ben", "food", "fun"))
    household.set_own_budget(db, anna, food, 5000)
    household.set_own_budget(db, anna, fun, 2000)

    shared = analytics.budgets(db.part("shared"))
    assert [(b["category_id"], b["budget_cents"], b["spent_cents"]) for b in shared] == [(food, 40000, 10000)]
    own = {b["category_id"]: b for b in household.own_budgets(db, anna)}
    assert (own[food]["budget_cents"], own[food]["spent_cents"], own[food]["state"]) == (5000, 3000, "ok")
    assert (own[fun]["budget_cents"], own[fun]["spent_cents"], own[fun]["state"]) == (2000, 2500, "over")
    assert household.own_budgets(db, ben) == []

    # Ändern und Entfernen
    assert household.set_own_budget(db, anna, fun, 6000)["limit_cents"] == 6000
    assert household.set_own_budget(db, anna, fun, None)["limit_cents"] is None
    assert list(household.own_budget_limits(db, anna)) == [food]
    income = db.scalar("SELECT id FROM categories WHERE kind = 'income' LIMIT 1")
    for person, category, cents in ((anna, food, -1), (anna, food, "5"), (anna, food, True), (anna, 999999, 100),
                                    (anna, income, 100), (999, food, 100), (None, food, 100)):
        with pytest.raises(household.HouseholdError):
            household.set_own_budget(db, person, category, cents)
    assert household.own_budget_limits(db, anna) == {food: 5000}


def test_without_private_accounts_budgets_count_everything_as_before(db):
    food = db.scalar("SELECT id FROM categories WHERE kind = 'expense' AND parent_id IS NULL ORDER BY id LIMIT 1")
    account = db.insert("accounts", {"name": "KS-TEST Kasse", "kind": "cash"})
    spend(db, account, 1234, food, "KS-TEST Markt")
    db.update("categories", "id", food, {"budget_cents": 5000})
    assert db.part("shared") is db
    assert analytics.budgets(db.part("shared"))[0]["spent_cents"] == 1234
    assert db.part("own", None).scalar("SELECT COUNT(*) FROM accounts") == 0


def test_app_gets_shared_and_own_budgets_and_sets_its_own(home):
    db, anna_id, ben_id, food, fun = (home[k] for k in ("db", "anna", "ben", "food", "fun"))
    with https_client() as client:
        anna, ben, nobody = pair(client, anna_id), pair(client, ben_id), pair(client)
        saved = client.put(f"/api/v1/budgets/own/{fun}", headers=anna, json={"limit_cents": 2000})
        assert saved.status_code == 200 and saved.json()["budget"]["limit_cents"] == 2000

        overview = client.get("/api/v1/overview", headers=anna).json()
        assert [(b["category_id"], b["limit_cents"], b["spent_cents"]) for b in overview["budgets"]] == [(food, 40000, 10000)]
        assert [(b["category_id"], b["limit_cents"], b["spent_cents"], b["state"]) for b in overview["own_budgets"]] == [
            (fun, 2000, 2500, "over")]
        # Ben sieht dasselbe gemeinsame Budget, aber nichts von Annas eigenem.
        his = client.get("/api/v1/overview", headers=ben).json()
        assert his["budgets"] == overview["budgets"] and his["own_budgets"] == []
        assert client.get("/api/v1/overview", headers=nobody).json()["own_budgets"] == []

        for bad in ({}, {"limit_cents": -5}, {"limit_cents": "5"}, {"limit_cents": 100, "x": 1}):
            assert client.put(f"/api/v1/budgets/own/{fun}", headers=anna, json=bad).status_code == 400, bad
        assert client.put("/api/v1/budgets/own/999999", headers=anna, json={"limit_cents": 100}).status_code == 404
        assert client.put(f"/api/v1/budgets/own/{fun}", headers=nobody, json={"limit_cents": 100}).status_code == 409
        assert client.put(f"/api/v1/budgets/own/{fun}", json={"limit_cents": 100}).status_code == 401
        assert client.put(f"/api/v1/budgets/own/{fun}", headers=anna, json={"limit_cents": None}).status_code == 200
        assert db.scalar("SELECT COUNT(*) FROM person_budgets") == 0
        assert "budgets.own" in client.get("/api/v1/me", headers=anna).json()["capabilities"]


def test_administration_reads_and_sets_budgets_of_a_person(home):
    db, anna, food = home["db"], home["anna"], home["food"]
    with https_client() as client:
        assert client.put(f"/api/persons/{anna}/budgets/{food}", json={"budget_cents": 6000}).status_code == 200
        own = client.get(f"/api/budgets?person={anna}").json()
        assert [(b["budget_cents"], b["spent_cents"]) for b in own["budgets"]] == [(6000, 3000)]
        assert own["stats"]["expense_cents"] == 5500 and own["limits"] == {str(food): 6000}
        shared = client.get("/api/budgets").json()
        assert [(b["budget_cents"], b["spent_cents"]) for b in shared["budgets"]] == [(40000, 10000)]
        assert client.get("/api/budgets?person=999").status_code == 404
        assert client.put(f"/api/persons/999/budgets/{food}", json={"budget_cents": 100}).status_code == 409
        assert client.put(f"/api/persons/{anna}/budgets/{food}", json={"budget_cents": None}).status_code == 200
        assert client.get(f"/api/budgets?person={anna}").json()["budgets"] == []
        # Mit der Person verschwinden ihre Budgets.
        client.put(f"/api/persons/{anna}/budgets/{food}", json={"budget_cents": 100})
        db.execute("UPDATE accounts SET owner_person_id = NULL WHERE owner_person_id = ?", (anna,))
        assert client.delete(f"/api/persons/{anna}").status_code == 200
        assert db.scalar("SELECT COUNT(*) FROM person_budgets") == 0


def test_own_budget_warns_its_person_and_fires_events(home, monkeypatch):
    from kassensturz import services
    db, anna, ben, food, fun = (home[k] for k in ("db", "anna", "ben", "food", "fun"))
    household.set_own_budget(db, anna, fun, 2000)   # 25 € von 20 €: drüber
    household.set_own_budget(db, anna, food, 3500)  # 30 € von 35 €: 86 %
    household.set_own_budget(db, ben, food, 5000)   # 7 € von 50 €: nichts
    today = date.today()

    summary = services.build_summary(db)
    own = [a for a in services.alerts(db, summary) if a["key"].startswith("own-budget:")]
    assert [(a["owner_person_id"], a["key"]) for a in own] == [(anna, f"own-budget:{anna}:{fun}:{today:%Y-%m}")]
    assert own[0]["text"].startswith("Anna: ")

    # Am Handy sieht nur Anna ihre Warnung, Ben nicht.
    def own_keys(person):
        view = db.scoped(person)
        return [a["key"] for a in services.alerts(view, services.build_summary(view)) if a["key"].startswith("own-budget:")]
    assert own_keys(anna) == [own[0]["key"]]
    assert own_keys(ben) == []

    events = services.budget_events({"budgets": []}, today, household.all_own_budgets(db))
    got = sorted((k, d["person"], d["schwelle"]) for k, _, d in events)
    month = f"{today:%Y-%m}"
    assert got == sorted([(f"ev-budget:{month}:p{anna}:{fun}:100", "Anna", 100),
                          (f"ev-budget:{month}:p{anna}:{fun}:80", "Anna", 80),
                          (f"ev-budget:{month}:p{anna}:{food}:80", "Anna", 80)])
    # Gemeinsame Budgets behalten ihre bisherigen Schlüssel.
    assert all(":p" not in k for k, _, _ in services.budget_events(summary, today))
