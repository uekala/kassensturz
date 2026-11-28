"""Ausgaben teilen und ausgleichen – nur erfundene Daten."""
from datetime import date

import pytest
from test_household import booking, pair
from test_mobile_write import https_client, reset_mobile_guards

from kassensturz import household, sharing

TODAY = date.today().isoformat()


@pytest.fixture()
def home(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    accounts = {
        "shared": db.insert("accounts", {"name": "KS-GEMEINSAM Kasse", "kind": "cash"}),
        "anna": db.insert("accounts", {"name": "KS-ANNA Kasse", "kind": "cash", "owner_person_id": anna}),
        "ben": db.insert("accounts", {"name": "KS-BEN Kasse", "kind": "cash", "owner_person_id": ben}),
    }
    return {"db": db, "anna": anna, "ben": ben, "accounts": accounts}


def test_split_by_weight_keeps_every_cent():
    assert sharing.split_by_weight(1001, {1: 1, 2: 1}, payer=1) == {1: 501, 2: 500}
    assert sharing.split_by_weight(1001, {1: 1, 2: 1}, payer=2) == {1: 500, 2: 501}
    assert sharing.split_by_weight(1000, {1: 60, 2: 40}, payer=1) == {1: 600, 2: 400}
    assert sharing.split_by_weight(100, {1: 1, 2: 1, 3: 1}, payer=3) == {1: 33, 2: 33, 3: 34}
    # Wer nichts mitträgt, bekommt keinen Teil; den Rest trägt dann das größte Gewicht.
    assert sharing.split_by_weight(101, {1: 0, 2: 2, 3: 1}, payer=1) == {2: 68, 3: 33}
    for total in (1, 7, 99, 12345):
        assert sum(sharing.split_by_weight(total, {1: 3, 2: 2, 3: 1}, payer=2).values()) == total


def test_sharing_an_expense_creates_a_debt_and_a_settlement_clears_it(home):
    db, anna, ben = home["db"], home["anna"], home["ben"]
    tx = booking(db, home["accounts"]["anna"], -9001, "KS-ANNA Wocheneinkauf")
    shared = sharing.set_share(db, tx)
    assert shared["shared"] is True and shared["payer"] == "Anna" and shared["total_cents"] == 9001
    assert {p["name"]: p["cents"] for p in shared["parts"]} == {"Anna": 4501, "Ben": 4500}
    assert sharing.balances(db) == [{"from_id": ben, "from": "Ben", "to_id": anna, "to": "Anna", "cents": 4500}]
    assert sharing.for_person(db, anna) == [{"person": "Ben", "cents": 4500}]
    assert sharing.for_person(db, ben) == [{"person": "Anna", "cents": -4500}]

    # Ben zahlt etwas für beide: es wird gegengerechnet.
    other = booking(db, home["accounts"]["ben"], -2000, "KS-BEN Getränke")
    sharing.set_share(db, other)
    assert sharing.balances(db)[0]["cents"] == 3500

    sharing.add_settlement(db, {"from_person_id": ben, "to_person_id": anna, "cents": 3000, "note": " KS  Ausgleich "})
    assert sharing.balances(db)[0]["cents"] == 500
    paid = sharing.add_settlement(db, {"from_person_id": ben, "to_person_id": anna, "cents": 500})
    assert sharing.balances(db) == []
    # Zu viel gezahlt dreht die Richtung um.
    sharing.add_settlement(db, {"from_person_id": ben, "to_person_id": anna, "cents": 100})
    assert sharing.balances(db) == [{"from_id": anna, "from": "Anna", "to_id": ben, "to": "Ben", "cents": 100}]
    sharing.delete_settlement(db, paid["id"])
    assert sharing.balances(db)[0] == {"from_id": ben, "from": "Ben", "to_id": anna, "to": "Anna", "cents": 400}
    assert sharing.list_settlements(db)[-1]["note"] == "KS Ausgleich"

    # Teilen zurücknehmen nimmt die Schuld zurück; die Buchung selbst bleibt unverändert.
    sharing.clear_share(db, tx)
    assert sharing.get_share(db, tx)["shared"] is False
    assert db.scalar("SELECT amount_cents FROM transactions WHERE id = ?", (tx,)) == -9001


def test_weights_and_explicit_parts(home):
    db, anna, ben = home["db"], home["anna"], home["ben"]
    household.update_person(db, anna, {"share_weight": 60})
    household.update_person(db, ben, {"share_weight": 40})
    tx = booking(db, home["accounts"]["anna"], -10000, "KS-ANNA Miete")
    assert {p["name"]: p["cents"] for p in sharing.set_share(db, tx)["parts"]} == {"Anna": 6000, "Ben": 4000}
    explicit = sharing.set_share(db, tx, [{"person_id": anna, "cents": 2500}, {"person_id": ben, "cents": 7500}])
    assert {p["name"]: p["cents"] for p in explicit["parts"]} == {"Anna": 2500, "Ben": 7500}
    assert sharing.balances(db)[0]["cents"] == 7500
    for bad in ([{"person_id": anna, "cents": 10000}], [{"person_id": ben, "cents": 9999}], [], "x",
                [{"person_id": ben, "cents": 10001}, {"person_id": anna, "cents": -1}],
                [{"person_id": 999, "cents": 10000}], [{"person_id": ben, "cents": 5000}, {"person_id": ben, "cents": 5000}],
                [{"person_id": ben, "cents": True}]):
        with pytest.raises(sharing.SharingError):
            sharing.set_share(db, tx, bad)
    assert sharing.balances(db)[0]["cents"] == 7500
    # Trägt außer dem Zahler niemand etwas, gibt es nichts zu teilen.
    household.update_person(db, ben, {"share_weight": 0})
    with pytest.raises(sharing.SharingError):
        sharing.set_share(db, tx)
    for bad in (-1, 1001, "2", True, 1.5):
        with pytest.raises(household.HouseholdError):
            household.update_person(db, ben, {"share_weight": bad})


def test_only_expenses_from_an_own_account_can_be_shared(home):
    db = home["db"]
    cases = {
        "gemeinsames Konto": booking(db, home["accounts"]["shared"], -500, "KS-GEMEINSAM Markt"),
        "Einnahme": booking(db, home["accounts"]["anna"], 500, "KS-ANNA Erstattung"),
    }
    transfer = booking(db, home["accounts"]["anna"], -500, "KS-ANNA Umbuchung")
    db.update("transactions", "id", transfer, {"is_transfer": 1})
    cases["Umbuchung"] = transfer
    for name, tx in cases.items():
        assert sharing.get_share(db, tx)["shareable"] is False, name
        with pytest.raises(sharing.SharingError) as refused:
            sharing.set_share(db, tx)
        assert refused.value.status == 409, name
    with pytest.raises(sharing.SharingError) as missing:
        sharing.set_share(db, 999999)
    assert missing.value.status == 404
    assert db.scalar("SELECT COUNT(*) FROM tx_shares") == 0


def test_debt_follows_the_account_and_a_person_with_open_debt_stays(home):
    db, anna, ben = home["db"], home["anna"], home["ben"]
    tx = booking(db, home["accounts"]["anna"], -1000, "KS-ANNA Einkauf")
    sharing.set_share(db, tx)
    # Wird das Konto gemeinsam, hat niemand mehr etwas ausgelegt.
    db.update("accounts", "id", home["accounts"]["anna"], {"owner_person_id": None})
    assert sharing.balances(db) == [] and sharing.items(db) == []
    db.update("accounts", "id", home["accounts"]["anna"], {"owner_person_id": anna})
    assert sharing.balances(db)[0]["cents"] == 500
    # Eine gelöschte Buchung zählt nicht mehr.
    gone = booking(db, home["accounts"]["anna"], -4000, "KS-ANNA Storno")
    sharing.set_share(db, gone)
    db.execute("DELETE FROM transactions WHERE id = ?", (gone,))
    assert sharing.balances(db)[0]["cents"] == 500

    db.update("accounts", "id", home["accounts"]["ben"], {"owner_person_id": None})
    with pytest.raises(household.HouseholdError) as open_debt:
        household.delete_person(db, ben)
    assert open_debt.value.status == 409
    sharing.add_settlement(db, {"from_person_id": ben, "to_person_id": anna, "cents": 500})
    assert household.delete_person(db, ben) == {"ok": True}
    assert db.scalar("SELECT COUNT(*) FROM tx_shares WHERE person_id = ?", (ben,)) == 0
    assert db.scalar("SELECT COUNT(*) FROM settlements") == 0
    assert sharing.balances(db) == []


def test_settlement_validation(home):
    db, anna, ben = home["db"], home["anna"], home["ben"]
    for bad in ({"from_person_id": anna, "to_person_id": anna, "cents": 100}, {"from_person_id": anna, "to_person_id": 999, "cents": 100},
                {"from_person_id": anna, "to_person_id": ben, "cents": 0}, {"from_person_id": anna, "to_person_id": ben, "cents": "5"},
                {"from_person_id": anna, "to_person_id": ben, "cents": 100, "on_date": "2999-01-01"},
                {"from_person_id": anna, "to_person_id": ben, "cents": 100, "on_date": "gestern"},
                {"from_person_id": anna, "to_person_id": ben, "cents": 100, "note": 5}):
        with pytest.raises(sharing.SharingError):
            sharing.add_settlement(db, bad)
    assert db.scalar("SELECT COUNT(*) FROM settlements") == 0
    with pytest.raises(sharing.SharingError):
        sharing.delete_settlement(db, 1)


def test_app_shares_own_expenses_and_sees_only_what_concerns_it(home):
    db, anna_id, ben_id = home["db"], home["anna"], home["ben"]
    carl_id = household.create_person(db, {"name": "Carl"})["id"]
    household.update_person(db, carl_id, {"share_weight": 0})
    mine = booking(db, home["accounts"]["anna"], -3000, "KS-ANNA Kino")
    private = booking(db, home["accounts"]["anna"], -7700, "KS-ANNA Geheim")
    bens = booking(db, home["accounts"]["ben"], -1200, "KS-BEN Bäcker")
    common = booking(db, home["accounts"]["shared"], -900, "KS-GEMEINSAM Markt")
    with https_client() as client:
        anna, ben, carl, nobody = (pair(client, anna_id), pair(client, ben_id), pair(client, carl_id), pair(client))

        state = client.get(f"/api/v1/transactions/{mine}/share", headers=anna).json()
        assert state["shareable"] is True and state["shared"] is False
        shared = client.put(f"/api/v1/transactions/{mine}/share", headers=anna, json={})
        assert shared.status_code == 200
        assert {p["name"]: p["cents"] for p in shared.json()["parts"]} == {"Anna": 1500, "Ben": 1500}

        # Fremde Buchungen teilt man nicht, und was man nicht sieht, gibt es nicht.
        assert client.put(f"/api/v1/transactions/{bens}/share", headers=anna, json={}).status_code == 404
        assert client.get(f"/api/v1/transactions/{bens}/share", headers=anna).status_code == 404
        assert client.delete(f"/api/v1/transactions/{mine}/share", headers=ben).status_code == 404
        assert client.put(f"/api/v1/transactions/{common}/share", headers=anna, json={}).status_code == 409
        assert client.put(f"/api/v1/transactions/{common}/share", headers=nobody, json={}).status_code == 404
        assert client.put(f"/api/v1/transactions/{mine}/share", headers=anna, json={"x": 1}).status_code == 400

        seen = client.get("/api/v1/household/sharing", headers=ben)
        assert seen.status_code == 200
        body = seen.json()
        assert body["open"] == [{"person": "Anna", "cents": -1500}]
        assert [(i["label"], i["total_cents"], i["payer"]) for i in body["items"]] == [("KS-ANNA Kino", 3000, "Anna")]
        assert sorted(p["name"] for p in body["persons"]) == ["Anna", "Ben", "Carl"]
        # Ben sieht die geteilte Buchung, aber nichts sonst von Annas Konto.
        assert "KS-ANNA Geheim" not in seen.text and "KS-ANNA Kasse" not in seen.text
        assert "KS-ANNA" not in client.get("/api/v1/transactions", headers=ben).text
        assert client.get("/api/v1/overview", headers=ben).json()["household"]["balances"] == [{"person": "Anna", "cents": -1500}]
        # Wer nicht beteiligt ist oder niemand ist, erfährt nichts.
        for headers in (carl, nobody):
            other = client.get("/api/v1/household/sharing", headers=headers).json()
            assert other["items"] == [] and other["open"] == [] and other["balances"] == []
        assert "KS-ANNA" not in client.get("/api/v1/household/sharing", headers=carl).text

        # Ben trägt ein, dass er überwiesen hat. Für andere kann er nichts eintragen.
        paid = client.post("/api/v1/household/settlements", headers=ben, json={"to_person_id": anna_id, "cents": 1500, "note": "KS Überweisung"})
        assert paid.status_code == 201 and paid.json()["settlement"]["from"] == "Ben"
        assert client.get("/api/v1/household/sharing", headers=anna).json()["open"] == []
        for bad in ({"to_person_id": ben_id, "cents": 100}, {"to_person_id": anna_id, "cents": 100, "from_person_id": anna_id},
                    {"to_person_id": anna_id}, {"to_person_id": anna_id, "cents": -5}):
            assert client.post("/api/v1/household/settlements", headers=ben, json=bad).status_code == 400, bad
        assert client.post("/api/v1/household/settlements", headers=nobody, json={"to_person_id": anna_id, "cents": 100}).status_code == 400
        assert db.scalar("SELECT COUNT(*) FROM settlements") == 1

        assert client.delete(f"/api/v1/transactions/{mine}/share", headers=anna).status_code == 200
        assert db.scalar("SELECT COUNT(*) FROM tx_shares") == 0
        assert private and db.scalar("SELECT COUNT(*) FROM transactions") == 4


def test_administration_shares_and_settles(home):
    db, anna, ben = home["db"], home["anna"], home["ben"]
    tx = booking(db, home["accounts"]["ben"], -2400, "KS-BEN Tanken")
    with https_client() as client:
        assert client.get(f"/api/transactions/{tx}/share").json()["shareable"] is True
        assert client.put(f"/api/transactions/{tx}/share", json={}).status_code == 200
        assert client.put("/api/transactions/999999/share", json={}).status_code == 404
        overview = client.get("/api/household/sharing").json()
        assert overview["balances"] == [{"from_id": anna, "from": "Anna", "to_id": ben, "to": "Ben", "cents": 1200}]
        assert overview["items"][0]["label"] == "KS-BEN Tanken"
        added = client.post("/api/household/settlements", json={"from_person_id": anna, "to_person_id": ben, "cents": 1200})
        assert added.status_code == 200
        assert client.get("/api/household/sharing").json()["balances"] == []
        assert client.delete(f"/api/household/settlements/{added.json()['id']}").status_code == 200
        assert client.delete("/api/household/settlements/999").status_code == 404
        assert client.patch(f"/api/persons/{ben}", json={"share_weight": 3}).json()["share_weight"] == 3
        assert client.delete(f"/api/transactions/{tx}/share").json()["shared"] is False
        outside = https_client(peer="203.0.113.7")
        assert outside.get("/api/household/sharing").status_code == 403
        assert outside.put(f"/api/transactions/{tx}/share", json={}).status_code == 403


def _food(db):
    return db.scalar("SELECT id FROM categories WHERE kind = 'expense' AND parent_id IS NULL ORDER BY id LIMIT 1")


def test_shared_expenses_count_by_part_for_each_person(home):
    from kassensturz import analytics

    db, anna, ben = home["db"], home["anna"], home["ben"]
    food = _food(db)
    month = date.today().strftime("%Y-%m")
    paid = booking(db, home["accounts"]["anna"], -9001, "KS-ANNA Wocheneinkauf")
    alone = booking(db, home["accounts"]["anna"], -2000, "KS-ANNA Buch")
    common = booking(db, home["accounts"]["shared"], -5000, "KS-GEMEINSAM Markt")
    for tx in (paid, alone, common):
        db.update("transactions", "id", tx, {"category_id": food})

    def expense(view):
        return analytics.month_stats(view, month)["expense_cents"]

    # Vor dem Teilen zählt alles beim Zahler.
    assert expense(db.scoped(anna)) == 9001 + 2000 + 5000
    assert expense(db.scoped(ben)) == 5000

    sharing.set_share(db, paid)
    # Anna trägt 45,01 €, Ben 45,00 €. Jeder sieht seinen Teil, zusammen fehlt kein Cent.
    assert expense(db.scoped(anna)) == 4501 + 2000 + 5000
    assert expense(db.scoped(ben)) == 4500 + 5000
    assert expense(db.part("own", anna)) == 4501 + 2000
    assert expense(db.part("own", ben)) == 4500
    # Haushalt und Verwaltung sehen die Buchung weiter ganz, Kontostände ändern sich nicht.
    assert expense(db.part("shared")) == 5000
    assert expense(db) == 9001 + 2000 + 5000
    breakdown = analytics.month_stats(db.scoped(ben), month)["breakdown"]
    assert [(b["category_id"], b["cents"]) for b in breakdown] == [(food, 9500)]

    # Eigene Budgets rechnen mit dem Teil.
    household.set_own_budget(db, anna, food, 10000)
    household.set_own_budget(db, ben, food, 4000)
    assert household.own_budgets(db, anna)[0]["spent_cents"] == 6501
    his = household.own_budgets(db, ben)[0]
    assert (his["spent_cents"], his["state"]) == (4500, "over")

    # Ein Kind mit Anteil 0 trägt nichts, auch wenn es dazugehört.
    carl = household.create_person(db, {"name": "Carl"})["id"]
    household.update_person(db, carl, {"share_weight": 0})
    assert expense(db.scoped(carl)) == 5000
    # Ganz von Ben getragen: bei Anna zählt davon nichts mehr.
    sharing.set_share(db, paid, [{"person_id": ben, "cents": 9001}])
    assert expense(db.part("own", anna)) == 2000
    assert expense(db.part("own", ben)) == 9001
    sharing.clear_share(db, paid)
    assert expense(db.part("own", anna)) == 9001 + 2000 and expense(db.part("own", ben)) == 0


def test_parts_of_a_split_booking_keep_their_categories(home):
    from kassensturz import analytics

    db, anna, ben = home["db"], home["anna"], home["ben"]
    first, second = [r["id"] for r in db.query(
        "SELECT id FROM categories WHERE kind = 'expense' AND parent_id IS NULL ORDER BY id LIMIT 2")]
    month = date.today().strftime("%Y-%m")
    tx = booking(db, home["accounts"]["anna"], -1001, "KS-ANNA Drogerie")
    db.update("transactions", "id", tx, {"category_id": first})
    db.insert("splits", {"tx_id": tx, "amount_cents": -301, "category_id": second})
    sharing.set_share(db, tx)

    def by_category(view):
        return {b["category_id"]: b["cents"] for b in analytics.month_stats(view, month)["breakdown"]}

    hers, his = by_category(db.part("own", anna)), by_category(db.part("own", ben))
    assert sum(hers.values()) == 501 and sum(his.values()) == 500
    assert set(hers) == set(his) == {first, second}
    # Je Person stimmt die Summe auf den Cent. Je Kategorie kann zwischen den Personen ein Cent Rundung liegen.
    assert abs(hers[first] + his[first] - 700) <= 1 and abs(hers[second] + his[second] - 301) <= 1
    assert sum(hers.values()) + sum(his.values()) == 1001


def test_app_statistics_use_the_parts(home):
    db, anna_id, ben_id = home["db"], home["anna"], home["ben"]
    tx = booking(db, home["accounts"]["anna"], -3000, "KS-ANNA Kino")
    db.update("transactions", "id", tx, {"category_id": _food(db)})
    sharing.set_share(db, tx)
    with https_client() as client:
        anna, ben = pair(client, anna_id), pair(client, ben_id)
        assert client.get("/api/v1/stats", headers=anna).json()["month"]["expense_cents"] == 1500
        stats = client.get("/api/v1/stats", headers=ben)
        assert stats.json()["month"]["expense_cents"] == 1500
        # Ben sieht den Betrag in seiner Auswertung, aber weiterhin nichts von Annas Konto.
        assert "KS-ANNA Kasse" not in stats.text
        assert "KS-ANNA" not in client.get("/api/v1/transactions", headers=ben).text
        assert client.get("/api/v1/accounts", headers=anna).json()["items"][1]["balance_cents"] == -3000
