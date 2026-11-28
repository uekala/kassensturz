"""App: Änderungsprotokoll – nur erfundene Daten."""
from test_household import pair
from test_mobile_write import https_client, reset_mobile_guards

from kassensturz import household


def entry(db, text, account_id=None, route="PATCH /api/accounts/{aid}", person_id=None, actor="Lokal", kind="local"):
    db.insert("audit_log", {"at": "2026-11-18T10:00:00", "actor": actor, "actor_kind": kind, "person_id": person_id,
                            "text": text, "account_id": account_id, "route": route})


def test_phone_sees_household_and_own_entries_only(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    shared = db.insert("accounts", {"name": "KS-Gemeinsam", "kind": "giro"})
    bens = db.insert("accounts", {"name": "KS-Bens Konto", "kind": "giro", "owner_person_id": ben})
    with https_client() as client:
        a = pair(client, anna, "Annas Handy")
        b = pair(client, ben, "Bens Handy")
        entry(db, "gemeinsam", shared)
        entry(db, "privat Ben", bens)
        entry(db, "Haushalt")
        entry(db, "Bens eigenes Budget", route="PUT /api/v1/budgets/own/{category_id}", person_id=ben, actor="Ben", kind="phone")
        entry(db, "Budget von Ben in HA", route="PUT /api/persons/{pid}/budgets/{cid}")
        seen_a = client.get("/api/v1/changes", headers=a).json()
        texts_a = [i["text"] for i in seen_a["items"]]
        assert "gemeinsam" in texts_a and "Haushalt" in texts_a
        assert not {"privat Ben", "Bens eigenes Budget", "Budget von Ben in HA"} & set(texts_a)
        texts_b = [i["text"] for i in client.get("/api/v1/changes", headers=b).json()["items"]]
        assert {"gemeinsam", "privat Ben", "Bens eigenes Budget"} <= set(texts_b) and "Budget von Ben in HA" not in texts_b
        page = client.get("/api/v1/changes?limit=1&offset=1", headers=b).json()
        assert len(page["items"]) == 1 and page["total"] == seen_a["total"] + 2
        assert page["items"][0].keys() == {"at", "actor", "phone", "text"}
        assert client.get("/api/v1/changes?limit=500", headers=a).status_code == 422
