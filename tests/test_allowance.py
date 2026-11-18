"""Kinder und Taschengeld – nur erfundene Daten."""
from datetime import date, timedelta

import pytest

from kassensturz import allowance, analytics, household, ledger, services, sharing
from test_household import READ_PATHS, booking, pair
from test_mobile_write import https_client, reset_mobile_guards

TODAY = date.today()


@pytest.fixture()
def family(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    mia = household.create_person(db, {"name": "Mia", "is_child": True})["id"]
    shared = db.insert("accounts", {"name": "KS-GEMEINSAM Kasse", "kind": "cash", "balance_cents": 50000,
                                    "balance_date": "2020-01-01", "in_forecast": 1})
    private = db.insert("accounts", {"name": "KS-ANNA Kasse", "kind": "cash", "owner_person_id": anna})
    booking(db, shared, -1100, "KS-GEMEINSAM Markt")
    booking(db, private, -2200, "KS-ANNA Buchladen")
    return {"db": db, "anna": anna, "ben": ben, "mia": mia, "shared": shared, "private": private}


def pocket(client, family, **extra):
    body = {"name": "KS-MIA Taschengeld", "kind": "taschengeld", "owner_person_id": family["mia"],
            "allowance_cents": 500, "allowance_interval": "week", **extra}
    created = client.post("/api/accounts", json=body)
    assert created.status_code == 200, created.text
    return created.json()


def test_a_child_bears_nothing_of_shared_expenses_by_default(family):
    persons = {p["name"]: p for p in household.list_persons(family["db"])}
    assert (persons["Mia"]["is_child"], persons["Mia"]["share_weight"]) == (1, 0)
    assert (persons["Anna"]["is_child"], persons["Anna"]["share_weight"]) == (0, 1)
    changed = household.update_person(family["db"], family["ben"], {"is_child": True})
    assert (changed["is_child"], changed["share_weight"]) == (1, 0)
    assert household.update_person(family["db"], family["ben"], {"is_child": False})["is_child"] == 0
    with pytest.raises(household.HouseholdError):
        household.update_person(family["db"], family["ben"], {"is_child": "ja"})


def test_allowance_is_credited_on_schedule_and_only_once(family):
    db = family["db"]
    with https_client() as client:
        account = pocket(client, family)
        assert (account["in_forecast"], account["allowance_next"], account["balance_cents"]) == (0, TODAY.isoformat(), 0)
        aid = account["id"]
        assert allowance.apply(db) == 1
        assert allowance.apply(db) == 0
        row = db.one("SELECT amount_cents, counterparty, is_transfer, source, booking_date FROM transactions WHERE account_id = ?", (aid,))
        assert row == {"amount_cents": 500, "counterparty": "Taschengeld", "is_transfer": 1, "source": "taschengeld",
                       "booking_date": TODAY.isoformat()}
        assert db.scalar("SELECT allowance_next FROM accounts WHERE id = ?", (aid,)) == (TODAY + timedelta(days=7)).isoformat()
        assert ledger.accounts_with_balance(db)[-1]["balance_now"] == 500

        # Drei Wochen später: genau die drei ausgefallenen Termine werden nachgeholt.
        later = TODAY + timedelta(days=21)
        assert allowance.apply(db, later) == 3
        assert allowance.apply(db, later) == 0
        assert db.scalar("SELECT COUNT(*) FROM transactions WHERE account_id = ?", (aid,)) == 4
        # Nach sehr langer Pause höchstens zwölf Termine, danach geht es normal weiter.
        much_later = later + timedelta(days=7 * 40)
        assert allowance.apply(db, much_later) == allowance.MAX_CATCH_UP
        assert date.fromisoformat(db.scalar("SELECT allowance_next FROM accounts WHERE id = ?", (aid,))) > much_later

        # Betrag ändern wirkt ab dem nächsten Termin; ohne Betrag gibt es keinen Termin mehr.
        assert client.patch(f"/api/accounts/{aid}", json={"allowance_cents": 800, "allowance_interval": "month"}).status_code == 200
        assert db.scalar("SELECT allowance_cents FROM accounts WHERE id = ?", (aid,)) == 800
        assert client.patch(f"/api/accounts/{aid}", json={"allowance_cents": None}).status_code == 200
        assert db.scalar("SELECT allowance_next FROM accounts WHERE id = ?", (aid,)) is None
        assert allowance.apply(db, much_later + timedelta(days=400)) == 0
        # Archiviert ruht es ebenfalls.
        client.patch(f"/api/accounts/{aid}", json={"allowance_cents": 500, "archived": 1})
        assert allowance.apply(db, much_later + timedelta(days=800)) == 0


def test_pocket_money_account_rules(family):
    db = family["db"]
    with https_client() as client:
        for bad in ({"owner_person_id": None}, {"allowance_cents": -1}, {"allowance_cents": "5"}, {"allowance_cents": 200000},
                    {"allowance_interval": "year"}):
            body = {"name": "KS-TEST Falsch", "kind": "taschengeld", "owner_person_id": family["mia"], "allowance_cents": 500, **bad}
            assert client.post("/api/accounts", json=body).status_code == 400, bad
        assert db.scalar("SELECT COUNT(*) FROM accounts WHERE kind = 'taschengeld'") == 0
        account = pocket(client, family, in_forecast=1)
        assert account["in_forecast"] == 0
        # Wird daraus ein gewöhnliches Konto, endet das Taschengeld.
        assert client.patch(f"/api/accounts/{account['id']}", json={"kind": "bargeld"}).status_code == 200
        row = db.one("SELECT allowance_cents, allowance_interval, allowance_next FROM accounts WHERE id = ?", (account["id"],))
        assert row == {"allowance_cents": None, "allowance_interval": None, "allowance_next": None}
        assert client.patch("/api/accounts/999999", json={"name": "x"}).status_code == 404
        # Ein gewöhnliches Konto bekommt kein Taschengeld.
        plain = client.post("/api/accounts", json={"name": "KS-TEST Kasse", "kind": "bargeld", "allowance_cents": 500}).json()
        assert plain["allowance_cents"] is None and plain["allowance_next"] is None


def test_pocket_money_stays_out_of_household_figures(family):
    db, anna, mia = family["db"], family["anna"], family["mia"]
    month = TODAY.strftime("%Y-%m")
    with https_client() as client:
        aid = pocket(client, family)["id"]
        allowance.apply(db)
        spent = booking(db, aid, -300, "KS-MIA Eis")
        before = services.net_worth(ledger.accounts_with_balance(db))["total_cents"]

        summary = services.build_summary(db)
        assert summary["worth"]["total_cents"] == before
        assert all(a["name"] != "KS-MIA Taschengeld" or a["group"] == "taschengeld" for a in summary["accounts"])
        assert ledger.net_worth_history(db)[-1]["cents"] == before
        # Die Ausgabe des Kindes zählt weder beim Haushalt noch bei den Eltern, wohl aber beim Kind.
        assert analytics.month_stats(db, month)["expense_cents"] == 1100 + 2200
        assert analytics.month_stats(db.scoped(anna), month)["expense_cents"] == 1100 + 2200
        assert analytics.month_stats(db.scoped(mia), month)["expense_cents"] == 300
        assert analytics.month_stats(db.scoped(mia), month)["income_cents"] == 0
        # Und sie lässt sich nicht teilen.
        assert sharing.get_share(db, spent)["shareable"] is False
        with pytest.raises(sharing.SharingError):
            sharing.set_share(db, spent)
        # Die Prognose rechnet ohne das Taschengeld-Konto.
        assert aid not in [a["id"] for a in analytics._forecast_accounts(db)]


def test_a_child_does_not_see_the_budgets_of_the_household(family):
    db = family["db"]
    category = db.scalar("SELECT id FROM categories WHERE builtin_key = 'supermarkt'")
    db.execute("UPDATE categories SET budget_cents = 44400 WHERE id = ?", (category,))
    db.execute("UPDATE transactions SET category_id = ?, category_locked = 1 WHERE counterparty = 'KS-GEMEINSAM Markt'", (category,))
    with https_client() as client:
        pocket(client, family)
        anna, mia = pair(client, family["anna"]), pair(client, family["mia"])
        # Die Erwachsenen sehen das Budget mit dem, was davon ausgegeben ist.
        seen = client.get("/api/v1/overview", headers=anna).json()["budgets"]
        assert [(b["limit_cents"], b["spent_cents"]) for b in seen] == [(44400, 1100)]
        assert any(c["budget_cents"] == 44400 for c in client.get("/api/v1/categories", headers=anna).json()["items"])
        # Das Kind bekommt weder Limit noch Ausgaben des Haushalts, auf keinem Leseweg.
        assert client.get("/api/v1/overview", headers=mia).json()["budgets"] == []
        names = client.get("/api/v1/categories", headers=mia).json()["items"]
        assert names and all(c["budget_cents"] is None for c in names)
        for path in READ_PATHS:
            assert "44400" not in client.get(path, headers=mia).text, path


def test_adults_see_pocket_money_and_the_child_sees_only_its_own(family):
    db, mia_id = family["db"], family["mia"]
    with https_client() as client:
        aid = pocket(client, family)["id"]
        anna, ben, mia, nobody = (pair(client, family["anna"]), pair(client, family["ben"]), pair(client, mia_id), pair(client))

        for headers in (anna, ben):
            accounts = {a["name"]: a["ownership"] for a in client.get("/api/v1/accounts", headers=headers).json()["items"]}
            assert accounts["KS-MIA Taschengeld"] == "child"
        assert {a["name"]: a["ownership"] for a in client.get("/api/v1/accounts", headers=anna).json()["items"]} == {
            "KS-GEMEINSAM Kasse": "shared", "KS-ANNA Kasse": "mine", "KS-MIA Taschengeld": "child"}
        assert "KS-MIA" not in client.get("/api/v1/accounts", headers=nobody).text

        # Das Kind sieht nur sein Konto – keine gemeinsamen und keine der Eltern, auf keinem Leseweg.
        for path in READ_PATHS:
            response = client.get(path, headers=mia)
            assert response.status_code == 200, (path, response.text)
            assert "KS-GEMEINSAM" not in response.text and "KS-ANNA" not in response.text, path
        own = client.get("/api/v1/accounts", headers=mia).json()["items"]
        assert [(a["name"], a["ownership"], a["balance_cents"]) for a in own] == [("KS-MIA Taschengeld", "mine", 500)]
        assert [t["counterparty"] for t in client.get("/api/v1/transactions", headers=mia).json()["items"]] == ["Taschengeld"]
        assert client.get("/api/v1/me", headers=mia).json()["household"]["read_only"] is True
        offered = client.get("/api/v1/me", headers=mia).json()["capabilities"]
        assert "accounts" in offered and not any(c.endswith(".write") or c in ("sync", "budgets.own", "triage") for c in offered)
        assert "transactions.write" in client.get("/api/v1/me", headers=anna).json()["capabilities"]
        assert client.get("/api/v1/me", headers=anna).json()["household"]["read_only"] is False

        # Die Eltern tragen eine Ausgabe ein; das Kind sieht sie.
        entry = {"client_request_id": "c" * 32, "account_id": aid, "booking_date": TODAY.isoformat(),
                 "amount_cents": -150, "counterparty": "KS-MIA Kiosk"}
        assert client.post("/api/v1/transactions", headers=ben, json=entry).status_code == 201
        assert client.get("/api/v1/accounts", headers=mia).json()["items"][0]["balance_cents"] == 350

        # Das Handy des Kindes ändert nichts.
        tx = db.scalar("SELECT id FROM transactions WHERE counterparty = 'KS-MIA Kiosk'")
        denied = [
            client.post("/api/v1/transactions", headers=mia, json={**entry, "client_request_id": "d" * 32}),
            client.patch(f"/api/v1/transactions/{tx}", headers=mia, json={"note": "x"}),
            client.delete(f"/api/v1/transactions/{tx}", headers=mia),
            client.post("/api/v1/accounts", headers=mia, json={"name": "KS-MIA Spardose"}),
            client.put("/api/v1/budgets/1", headers=mia, json={"limit_cents": 100}),
            client.put("/api/v1/budgets/own/1", headers=mia, json={"limit_cents": 100}),
            client.post("/api/v1/sync", headers=mia),
            client.post("/api/v1/household/settlements", headers=mia, json={"to_person_id": family["anna"], "cents": 100}),
            client.put(f"/api/v1/transactions/{tx}/share", headers=mia, json={}),
        ]
        assert [r.status_code for r in denied] == [403] * len(denied)
        assert denied[0].json()["error"]["code"] == "read_only"
        assert db.scalar("SELECT COUNT(*) FROM transactions WHERE account_id = ?", (aid,)) == 2
        assert db.scalar("SELECT note FROM transactions WHERE id = ?", (tx,)) is None
        # Lesen als gelesen merken und Abmelden gehen.
        assert client.post("/api/v1/news/seen", headers=mia).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=mia).status_code == 200
        assert client.get("/api/v1/accounts", headers=mia).status_code == 401

        # Wird aus dem Kind eine erwachsene Person, gelten sofort deren Regeln.
        again = pair(client, mia_id)
        household.update_person(db, mia_id, {"is_child": False})
        assert "KS-GEMEINSAM Kasse" in client.get("/api/v1/accounts", headers=again).text
        assert client.patch(f"/api/v1/transactions/{tx}", headers=again, json={"note": "ok"}).status_code == 200
