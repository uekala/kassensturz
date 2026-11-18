"""Projekte – nur erfundene Daten."""
import pytest

from kassensturz import household, ledger, projects, services


@pytest.fixture()
def giro(db):
    return db.insert("accounts", {"name": "KS-Girokonto", "kind": "giro"})


def book(db, acc, day, cents, who, **extra):
    ledger.import_rows(db, acc, [{"booking_date": day, "amount_cents": cents, "counterparty": who,
                                  "purpose": f"Beleg {day} {cents}"}], "openbanking")
    tx = db.scalar("SELECT MAX(id) FROM transactions")
    if extra:
        db.update("transactions", "id", tx, extra)
    return tx


def cat(db, name):
    return db.scalar("SELECT id FROM categories WHERE name = ?", (name,)) or db.insert(
        "categories", {"name": name, "kind": "expense"})


def test_project_collects_bookings_across_categories_and_months(client, db, giro):
    made = client.post("/api/projects", json={"name": "  Erfundener   Urlaub 2027 ", "budget_cents": 200000, "note": "Juli"})
    assert made.status_code == 200, made.text
    pid = made.json()["id"]
    assert (made.json()["name"], made.json()["cost_cents"], made.json()["left_cents"]) == ("Erfundener Urlaub 2027", 0, 200000)
    reise, essen = cat(db, "KS-Reise"), cat(db, "KS-Essen")
    flug = book(db, giro, "2027-03-02", -64000, "Erfundene Fluglinie", category_id=reise)
    hotel = book(db, giro, "2027-07-10", -80000, "Erfundenes Hotel", category_id=reise)
    lokal = book(db, giro, "2027-07-12", -9000, "Erfundenes Lokal", category_id=essen)
    zurueck = book(db, giro, "2027-07-20", 5000, "Erfundenes Hotel", category_id=reise)
    fremd = book(db, giro, "2027-07-13", -3000, "Erfundener Supermarkt", category_id=essen)
    done = client.post(f"/api/projects/{pid}/assign", json={"tx_ids": [flug, hotel, lokal, zurueck, hotel, 99999]})
    assert done.status_code == 200 and done.json()["assigned"] == 4
    seen = client.get(f"/api/projects/{pid}").json()
    assert (seen["spent_cents"], seen["back_cents"], seen["cost_cents"], seen["count"]) == (153000, 5000, 148000, 4)
    assert (seen["first"], seen["last"], seen["left_cents"]) == ("2027-03-02", "2027-07-20", 52000)
    assert [(c["name"], c["cents"]) for c in seen["categories"]] == [("KS-Reise", 144000), ("KS-Essen", 9000)]
    assert seen["months"] == [{"month": "2027-03", "cents": 64000}, {"month": "2027-07", "cents": 84000}]
    assert [t["id"] for t in seen["transactions"]] == [zurueck, lokal, hotel, flug]
    # Die Buchungsliste filtert nach Projekt und nennt das Projekt je Buchung.
    listed = client.get(f"/api/transactions?project={pid}").json()
    assert listed["total"] == 4 and {t["project_id"] for t in listed["items"]} == {pid}
    everything = {t["id"]: t["project_id"] for t in client.get("/api/transactions").json()["items"]}
    assert everything[fremd] is None and everything[flug] == pid
    # An der Kategorie ändert das Projekt nichts.
    assert db.scalar("SELECT category_id FROM transactions WHERE id = ?", (lokal,)) == essen


def test_split_parts_count_in_their_categories_and_transfers_not_at_all(client, db, giro):
    pid = client.post("/api/projects", json={"name": "Erfundene Sanierung"}).json()["id"]
    bau, moebel = cat(db, "KS-Bau"), cat(db, "KS-Möbel")
    kauf = book(db, giro, "2027-02-01", -50000, "Erfundener Baumarkt", category_id=bau)
    db.insert("splits", {"tx_id": kauf, "amount_cents": -20000, "category_id": moebel})
    umbuchung = book(db, giro, "2027-02-02", -99900, "Erfundenes Sparkonto")
    db.execute("UPDATE transactions SET is_transfer = 1 WHERE id = ?", (umbuchung,))
    client.post(f"/api/projects/{pid}/assign", json={"tx_ids": [kauf, umbuchung]})
    seen = client.get(f"/api/projects/{pid}").json()
    assert seen["cost_cents"] == 50000 and seen["count"] == 1
    assert sorted((c["name"], c["cents"]) for c in seen["categories"]) == [("KS-Bau", 30000), ("KS-Möbel", 20000)]


def test_one_project_per_booking_and_single_assignment_via_the_booking(client, db, giro):
    one = client.post("/api/projects", json={"name": "Erfundenes Auto"}).json()["id"]
    two = client.post("/api/projects", json={"name": "Erfundener Umzug"}).json()["id"]
    tx = book(db, giro, "2027-01-05", -12000, "Erfundene Werkstatt")
    assert client.patch(f"/api/transactions/{tx}", json={"project_id": one}).status_code == 200
    assert client.get(f"/api/projects/{one}").json()["cost_cents"] == 12000
    assert client.patch(f"/api/transactions/{tx}", json={"project_id": two}).status_code == 200
    assert client.get(f"/api/projects/{one}").json()["count"] == 0 and client.get(f"/api/projects/{two}").json()["count"] == 1
    assert client.patch(f"/api/transactions/{tx}", json={"note": "bleibt"}).status_code == 200      # ohne project_id: unverändert
    assert client.get(f"/api/projects/{two}").json()["count"] == 1
    assert client.patch(f"/api/transactions/{tx}", json={"project_id": None}).status_code == 200
    assert client.get(f"/api/projects/{two}").json()["count"] == 0
    assert client.patch(f"/api/transactions/{tx}", json={"project_id": 4711}).status_code == 404
    assert client.patch(f"/api/transactions/{tx}", json={"project_id": "eins"}).status_code == 400


def test_all_search_hits_can_be_assigned_at_once(client, db, giro):
    pid = client.post("/api/projects", json={"name": "Erfundene Reise"}).json()["id"]
    a = book(db, giro, "2027-05-01", -1000, "Erfundene Bahn")
    b = book(db, giro, "2027-05-02", -2000, "Erfundener Bäcker")
    c = book(db, giro, "2027-05-03", -3000, "Erfundenes Museum")
    d = book(db, giro, "2027-05-04", -4000, "Erfundene Umbuchung")
    db.execute("UPDATE transactions SET note = 'Tags: Reise2027' WHERE id IN (?, ?, ?)", (a, c, d))
    db.execute("UPDATE transactions SET is_transfer = 1 WHERE id = ?", (d,))
    done = client.post(f"/api/projects/{pid}/assign", json={"filter": {"q": "Reise2027"}})
    assert done.status_code == 200 and done.json()["assigned"] == 2
    assert {t["id"] for t in done.json()["project"]["transactions"]} == {a, c}
    assert client.post(f"/api/projects/{pid}/assign", json={"filter": {"q": "Reise2027"}}).json()["assigned"] == 0
    # Ohne Eingrenzung, ohne Treffer, mit kaputtem Filter: nichts passiert.
    assert client.post(f"/api/projects/{pid}/assign", json={"filter": {}}).status_code == 400
    assert client.post(f"/api/projects/{pid}/assign", json={"filter": {"q": "gibtesnicht"}}).status_code == 404
    assert client.post(f"/api/projects/{pid}/assign", json={"filter": {"account": "x"}}).status_code == 400
    assert client.post(f"/api/projects/{pid}/assign", json={"filter": {"month": "2027-05"}}).json()["assigned"] == 1
    assert client.get(f"/api/projects/{pid}").json()["count"] == 3 and b in {
        t["id"] for t in client.get(f"/api/projects/{pid}").json()["transactions"]}
    assert client.post("/api/projects/unassign", json={"tx_ids": [a, b]}).json() == {"removed": 2}
    assert client.get(f"/api/projects/{pid}").json()["count"] == 1


def test_change_archive_delete_and_overview_order(client, db, giro):
    old = client.post("/api/projects", json={"name": "Erfundenes Altprojekt"}).json()["id"]
    new = client.post("/api/projects", json={"name": "Erfundenes Neuprojekt"}).json()["id"]
    leer = client.post("/api/projects", json={"name": "Erfundenes Leerprojekt"}).json()["id"]
    tx = book(db, giro, "2026-01-01", -100, "Erfundener Laden")
    client.post(f"/api/projects/{old}/assign", json={"tx_ids": [tx]})
    client.post(f"/api/projects/{new}/assign", json={"tx_ids": [book(db, giro, "2027-01-01", -200, "Erfundener Laden")]})
    assert [p["id"] for p in client.get("/api/projects").json()["items"]] == [new, old, leer]
    changed = client.post(f"/api/projects/{new}", json={"name": "Erfundenes Hauptprojekt", "budget_cents": 0, "archived": True})
    assert changed.status_code == 200 and (changed.json()["archived"], changed.json()["budget_cents"]) == (True, None)
    seen = client.get("/api/projects").json()
    assert [p["id"] for p in seen["items"]] == [old, leer, new] and seen["active"] == 2
    assert client.post(f"/api/projects/{old}", json={"name": "erfundenes hauptprojekt"}).status_code == 409
    assert client.post(f"/api/projects/{new}", json={"name": "ERFUNDENES Hauptprojekt"}).status_code == 200   # sich selbst nicht im Weg
    assert client.delete(f"/api/projects/{old}").json() == {"ok": True}
    assert client.get(f"/api/projects/{old}").status_code == 404 and client.delete(f"/api/projects/{old}").status_code == 404
    assert db.scalar("SELECT COUNT(*) FROM transactions WHERE id = ?", (tx,)) == 1
    assert db.scalar("SELECT COUNT(*) FROM project_tx WHERE tx_id = ?", (tx,)) == 0


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": 7}, {"name": "Erfunden", "budget_cents": -1},
                                  {"name": "Erfunden", "budget_cents": 1.5}, {"name": "Erfunden", "budget_cents": True},
                                  {"name": "Erfunden", "note": 3}])
def test_bad_project_is_refused(client, body):
    assert client.post("/api/projects", json=body).status_code == 400
    assert client.get("/api/projects").json()["items"] == []


@pytest.mark.parametrize("ids", [None, [], ["1"], [True], "1,2"])
def test_bad_assignment_is_refused(client, ids):
    pid = client.post("/api/projects", json={"name": "Erfunden"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/assign", json={"tx_ids": ids}).status_code == 400
    assert client.post("/api/projects/4711/assign", json={"tx_ids": [1]}).status_code == 404


def test_deleted_bookings_drop_out_and_persons_see_only_their_part(db, giro):
    anna = household.create_person(db, {"name": "KS-Anna"})["id"]
    ben = household.create_person(db, {"name": "KS-Ben"})["id"]
    own = db.insert("accounts", {"name": "KS-Bens Konto", "kind": "giro", "owner_person_id": ben})
    pid = projects.create(db, {"name": "Erfundenes Fest"})["id"]
    gemeinsam = book(db, giro, "2027-06-01", -10000, "Erfundener Saal")
    privat = book(db, own, "2027-06-02", -4000, "Erfundenes Geschenk")
    weg = book(db, giro, "2027-06-03", -700, "Erfundener Kiosk")
    projects.assign(db, pid, [gemeinsam, privat, weg])
    assert projects.detail(db, pid)["cost_cents"] == 14700
    assert projects.detail(db.scoped(anna), pid)["cost_cents"] == 10700
    assert projects.detail(db.scoped(ben), pid)["cost_cents"] == 14700
    db.execute("DELETE FROM transactions WHERE id = ?", (weg,))
    services.refresh(db, notify=False)
    assert db.scalar("SELECT COUNT(*) FROM project_tx") == 2 and projects.detail(db, pid)["cost_cents"] == 14000
