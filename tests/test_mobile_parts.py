"""App: Umsätze und Auswertung nach „Ich“ und „Gemeinsam“ – nur erfundene Daten."""
from test_household import home, pair  # noqa: F401  (Fixture)
from test_mobile_write import https_client

from kassensturz import household


def names(client, headers, part=None):
    url = "/api/v1/transactions" + (f"?part={part}" if part else "")
    got = client.get(url, headers=headers)
    assert got.status_code == 200, got.text
    return sorted(i["counterparty"] for i in got.json()["items"])


def spent(client, headers, part):
    got = client.get(f"/api/v1/stats?part={part}", headers=headers)
    assert got.status_code == 200, got.text
    return got.json()["month"]["expense_cents"]


def test_own_and_shared_parts(home):  # noqa: F811 – pytest-Fixture aus test_household
    db, anna = home["db"], home["anna"]
    child = household.create_person(db, {"name": "Kim", "is_child": True})["id"]
    with https_client() as client:
        a = pair(client, anna, "Annas Handy")
        k = pair(client, child, "Kims Handy")
        nobody = pair(client, None, "Haushaltsgerät")
        assert "parts" in client.get("/api/v1/me", headers=a).json()["capabilities"]
        assert "parts" not in client.get("/api/v1/me", headers=k).json()["capabilities"]

        assert names(client, a) == ["KS-ANNA Buchladen", "KS-GEMEINSAM Markt"]
        assert names(client, a, "all") == names(client, a)
        assert names(client, a, "own") == ["KS-ANNA Buchladen"]
        assert names(client, a, "shared") == ["KS-GEMEINSAM Markt"]
        assert (spent(client, a, "own"), spent(client, a, "shared"), spent(client, a, "all")) == (2200, 1100, 3300)

        # Bens Buchungen erscheinen in keinem Teil, unbekannte Teile und Kinderhandys werden abgelehnt.
        for part in ("other", "OWN", "ben"):
            assert client.get(f"/api/v1/transactions?part={part}", headers=a).status_code == 400
        for part in ("own", "shared"):
            assert client.get(f"/api/v1/transactions?part={part}", headers=k).status_code == 400
            assert client.get(f"/api/v1/stats?part={part}", headers=k).status_code == 400
            assert client.get(f"/api/v1/transactions?part={part}", headers=nobody).status_code == 400
