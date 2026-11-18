"""Antworten für die Bildschirmfotos der App – nur Beispieldaten."""
import json
import subprocess
import sys

from conftest import ROOT


def test_fixture_holds_an_answer_for_every_page_of_the_app(tmp_path):
    target = tmp_path / "server.json"
    # Eigener Prozess: Das Werkzeug startet den Server in einem eigenen, leeren Ordner.
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "app_fixture.py"), str(target)],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    views = json.loads(target.read_text("utf-8"))["views"]
    assert set(views) == {"anna", "mia"}
    for view, answers in views.items():
        assert all(answer["status"] == 200 for answer in answers.values()), view
    anna, mia = views["anna"], views["mia"]
    overview = anna["GET /api/v1/overview"]["body"]
    assert overview["household"]["person"]["name"] == "Anna" and overview["household"]["private_accounts"] is True
    assert {a["ownership"] for a in overview["accounts"]} == {"shared", "mine", "child"}
    assert overview["budgets"] and overview["goals"] and anna["GET /api/v1/contracts"]["body"]["items"]
    assert anna["GET /api/v1/household/sharing"]["body"]["items"]
    assert anna["GET /api/v1/transactions"]["body"]["items"][0]["counterparty"]
    # Das Kind sieht nur sein Taschengeld und kann nichts ändern.
    child = mia["GET /api/v1/overview"]["body"]
    assert [a["ownership"] for a in child["accounts"]] == ["mine"] and child["household"]["read_only"] is True
    assert not any(c.endswith(".write") for c in mia["GET /api/v1/me"]["body"]["capabilities"])
