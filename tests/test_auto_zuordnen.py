"""Zuordnen ohne Zutun: mehr Merkmale beim Lernen, größeres Wörterbuch, Vorschläge – erfundene Daten."""
import pytest

from kassensturz import categorize, ledger
from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _cat(db, key):
    return db.scalar("SELECT id FROM categories WHERE builtin_key = ?", (key,))


def _book(db, acc, who, cents=-2500, purpose="Test", iban=None, creditor=None, day="2026-11-02"):
    ledger.import_rows(db, acc, [{"booking_date": day, "amount_cents": cents, "counterparty": who, "purpose": purpose,
                                  "counterparty_iban": iban, "creditor_id": creditor}], "fints")
    return db.scalar("SELECT MAX(id) FROM transactions")


def _key_of(db, tx):
    return db.scalar("SELECT c.builtin_key FROM transactions t JOIN categories c ON c.id = t.category_id WHERE t.id = ?", (tx,))


@pytest.fixture
def acc(db):
    return db.insert("accounts", {"name": "Testgiro", "kind": "giro"})


def test_creditor_id_is_recognised_under_a_changing_name(client, db, acc):
    first = _book(db, acc, "Erfundene Abrechnung Nord", creditor="DE98ZZZ00000012345")
    assert _key_of(db, first) == "sonstiges"
    client.patch(f"/api/transactions/{first}", json={"category_id": _cat(db, "hobby")})
    other = _book(db, acc, "Erfundene Abrechnung Sued GmbH", creditor="DE98ZZZ00000012345", day="2026-11-09")
    stranger = _book(db, acc, "Erfundener Fremder", creditor="DE11ZZZ00000099999", day="2026-11-10")
    assert _key_of(db, other) == "hobby"
    assert _key_of(db, stranger) == "sonstiges"


def test_iban_is_recognised_and_the_name_wins_over_it(client, db, acc):
    a = _book(db, acc, "Erfundener Verein Abteilung A", iban="DE02120300000000202051")
    client.patch(f"/api/transactions/{a}", json={"category_id": _cat(db, "hobby")})
    b = _book(db, acc, "Erfundener Verein Abteilung B", iban="DE02120300000000202051", day="2026-11-05")
    assert _key_of(db, b) == "hobby"
    client.patch(f"/api/transactions/{b}", json={"category_id": _cat(db, "bildung")})
    again_a = _book(db, acc, "Erfundener Verein Abteilung A", iban="DE02120300000000202051", day="2026-11-12")
    again_b = _book(db, acc, "Erfundener Verein Abteilung B", iban="DE02120300000000202051", day="2026-11-13")
    assert (_key_of(db, again_a), _key_of(db, again_b)) == ("hobby", "bildung")


def test_own_accounts_stay_transfers(client, db, acc):
    db.insert("accounts", {"name": "Testtagesgeld", "kind": "tagesgeld", "iban": "DE02500105170137075030"})
    db.execute("INSERT INTO learned_categories(key, sign, label, category_id) VALUES('iban:DE02500105170137075030', 'out', 'x', ?)",
               (_cat(db, "hobby"),))
    tx = _book(db, acc, "Ich selbst", iban="DE02500105170137075030")
    assert _key_of(db, tx) == "umbuchung"


def test_merchant_behind_a_payment_service_is_learned(client, db, acc):
    purpose = "1044444444444 PP.1234.PP . ERFUNDENER HOFLADEN XY, Ihr Einkauf bei ERFUNDENER HOFLADEN XY"
    first = _book(db, acc, "PayPal Europe S.a.r.l. et Cie S.C.A", purpose=purpose, iban="LU89751000135104200E", creditor="LU96ZZZ0000000000000000058")
    assert categorize.merchant_behind({"counterparty": "PayPal Europe", "purpose": purpose}) == "erfundener hofladen xy"
    client.patch(f"/api/transactions/{first}", json={"category_id": _cat(db, "supermarkt")})
    same = _book(db, acc, "PayPal Europe S.a.r.l. et Cie S.C.A", purpose=purpose.replace("1044444444444", "1055555555555"), day="2026-11-08",
                 iban="LU89751000135104200E", creditor="LU96ZZZ0000000000000000058")
    other = _book(db, acc, "PayPal Europe S.a.r.l. et Cie S.C.A", purpose="PP.9999.PP . ERFUNDENER ANDERER, Ihr Einkauf bei ERFUNDENER ANDERER",
                  iban="LU89751000135104200E", creditor="LU96ZZZ0000000000000000058", day="2026-11-09")
    assert _key_of(db, same) == "supermarkt"
    assert _key_of(db, other) == "sonstiges"
    keys = [r["key"] for r in db.query("SELECT key FROM learned_categories")]
    assert keys == ["via:erfundener hofladen xy"]
    assert categorize.merchant_behind({"counterparty": "SumUp *Erfundenes Cafe", "purpose": ""}) == "erfundenes cafe"
    assert categorize.learn_keys({"counterparty": "Klarna", "purpose": "ohne Hinweis"}) == []


def test_forgetting_removes_identifiers_too(client, db, acc):
    tx = _book(db, acc, "Erfundene Abrechnung Nord", creditor="DE98ZZZ00000012345", iban="DE02120300000000202051")
    client.patch(f"/api/transactions/{tx}", json={"category_id": _cat(db, "hobby")})
    assert db.scalar("SELECT COUNT(*) FROM learned_categories") == 3
    listed = client.get("/api/learned").json()
    assert [row["label"] for row in listed] == ["Erfundene Abrechnung Nord"]
    client.delete(f"/api/learned/{listed[0]['id']}")
    assert db.scalar("SELECT COUNT(*) FROM learned_categories") == 0
    db.update("transactions", "id", tx, {"category_locked": 0})
    categorize.recategorize(db)
    assert _key_of(db, tx) == "sonstiges"


@pytest.mark.parametrize("who, purpose, cents, key", [
    ("Erfundene Baeckerei Schmitz", "", -480, "supermarkt"), ("Physio Erfunden", "Rechnung Ergotherapie", -4000, "gesundheit"),
    ("Familienkasse Erfunden", "Kindergeld", 25000, "gehalt"), ("Erfundene Tankstelle 123", "", -6000, "laden"),
    ("Techniker Krankenkasse", "Beitrag", -21000, "versicherungen"), ("Hetzner Online GmbH", "Rechnung", -590, "software"),
    ("Pizzeria Erfunden", "", -2350, "restaurant"), ("Stadtkasse Erfunden", "Bussgeld", -3000, "steuern"),
    ("Friseur Erfunden", "", -2800, "drogerie"), ("Fressnapf Erfunden", "", -3500, "haushalt"),
    ("Erfundener Sportverein e.V.", "Mitgliedsbeitrag", -1200, "hobby"), ("Erfundene Fahrschule", "", -45000, "bildung"),
])
def test_dictionary_knows_more_everyday_payees(db, acc, who, purpose, cents, key):
    assert _key_of(db, _book(db, acc, who, cents, purpose)) == key


def test_dictionary_keeps_earlier_meanings(db, acc):
    assert _key_of(db, _book(db, acc, "Media Markt Erfunden", -19900)) == "elektronik"
    assert _key_of(db, _book(db, acc, "REWE Markt GmbH", -4200, day="2026-11-03")) == "supermarkt"
    assert _key_of(db, _book(db, acc, "Erfundener Unbekannter", -4200, day="2026-11-04")) == "sonstiges"


def test_suggestions_come_from_words_shared_by_several_payees(db, acc, monkeypatch):
    reset_mobile_guards(monkeypatch)
    hobby = _cat(db, "hobby")
    for index, name in enumerate(("Kletterwerk Nord", "Kletterwerk Sued", "Kletterwerk West")):
        tx = _book(db, acc, f"Erfundenes {name}", day=f"2026-10-0{index + 1}")
        db.update("transactions", "id", tx, {"category_id": hobby})
    # Ein Ortsname streut über die Kategorien und taugt nicht als Hinweis.
    for index, key in enumerate(("hobby", "bildung", "gesundheit")):
        tx = _book(db, acc, f"Musterhausen Betrieb {index}", day=f"2026-10-1{index}")
        db.update("transactions", "id", tx, {"category_id": _cat(db, key)})
    new = _book(db, acc, "Erfundenes Kletterwerk Ost", -1900, day="2026-11-10")
    town = _book(db, acc, "Musterhausen Neuling", -900, day="2026-11-11")
    income = _book(db, acc, "Erfundenes Kletterwerk Ost", 1900, day="2026-11-12")

    hints = categorize.suggestions(db, db.query("SELECT id, counterparty, purpose, amount_cents FROM transactions WHERE id IN (?, ?, ?)", (new, town, income)))
    assert hints == {new: hobby}

    with https_client() as client:
        items = client.get("/api/v1/triage", headers=paired_headers(client)).json()["items"]
    by_id = {item["id"]: item["suggestion"] for item in items}
    assert by_id[new] == {"id": hobby, "name": "Hobby & Sport"}
    assert by_id[town] is None and by_id[income] is None


def test_two_payees_are_not_enough_for_a_suggestion(db, acc):
    for index, name in enumerate(("Nord", "Sued")):
        tx = _book(db, acc, f"Erfundenes Kletterwerk {name}", day=f"2026-10-0{index + 1}")
        db.update("transactions", "id", tx, {"category_id": _cat(db, "hobby")})
    new = _book(db, acc, "Erfundenes Kletterwerk Ost", day="2026-11-10")
    assert categorize.suggestions(db, db.query("SELECT id, counterparty, purpose, amount_cents FROM transactions WHERE id = ?", (new,))) == {}


def test_new_rules_are_applied_once_and_keep_manual_choices(client, db, acc):
    auto = _book(db, acc, "Erfundene Fahrschule")
    manual = _book(db, acc, "Erfundene Fahrschule Zwei", day="2026-11-03")
    client.patch(f"/api/transactions/{manual}", json={"category_id": _cat(db, "hobby"), "learn": False})
    db.update("transactions", "id", auto, {"category_id": _cat(db, "sonstiges"), "rule_ref": None})
    db.set_setting(categorize.RULES_VERSION_KEY, 1)

    assert categorize.upgrade(db) == 1
    assert (_key_of(db, auto), _key_of(db, manual)) == ("bildung", "hobby")
    assert categorize.upgrade(db) == 0
