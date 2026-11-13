from datetime import datetime, timezone

import pytest

from kassensturz.mobile_read import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MobileQueryError,
    list_transactions,
    serialize_overview,
)


def test_overview_dto_allowlists_fields_and_uses_integer_cents():
    summary = {
        "accounts": [
            {
                "id": 7, "name": "Girokonto", "kind": "giro",
                "balance_now": 123456, "balance_known": True,
                "balance_date": "2026-11-01", "tx_count": 42,
                "iban": "DE89370400440532013000",
                "fints_ref": "private-provider-reference",
            }
        ],
        "forecast": {
            "today": "2026-11-03", "balance_now": 123456,
            "free_cents": 100000, "free_per_day_cents": 10000,
            "period_end": "2026-11-13", "period_label": "bis zum nächsten Gehalt",
            "days_left": 10, "fixed_out_cents": -20000, "fixed_in_cents": 0,
            "variable_daily_cents": 1000, "variable_expected_cents": 10000,
            "buffer_cents": 5000, "month_end_cents": 90000,
            "low_point": {"date": "2026-11-10", "cents": 80000},
            "upcoming": [{
                "key": "internal-contract-key", "name": "Miete",
                "date": "2026-11-05", "amount_cents": -80000,
                "interval": "monatlich", "account_id": 7, "overdue": False,
                "provider_id": "private",
            }],
            "raw_internal_field": "must not escape",
        },
        "month": {
            "month": "2026-11", "income_cents": 250000,
            "expense_cents": 150000, "saldo_cents": 100000,
            "breakdown": [{
                "category_id": 3, "name": "Lebensmittel",
                "cents": 40000, "internal": "must not escape",
            }],
            "internal": "must not escape",
        },
        "budgets": [{
            "category_id": 3, "name": "Lebensmittel",
            "budget_cents": 50000, "spent_cents": 40000,
            "left_cents": 10000, "ratio": 0.8, "pace": 0.1,
            "state": "warn", "parent_id": None,
            "internal": "must not escape",
        }],
        "contracts": [{"key": "private-contract"}],
    }
    alerts = [{
        "key": "private-alert-key", "level": "warning",
        "title": "Budget Lebensmittel überschritten",
        "text": "50,00 € von 45,00 € ausgegeben.",
        "contract": "private-contract-key", "eb": 99,
    }]

    dto = serialize_overview(
        summary, alerts,
        as_of=datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc),
    )

    assert dto["as_of"] == "2026-11-03T12:00:00+00:00"
    assert dto["currency"] == "EUR"
    assert dto["accounts"] == [{
        "id": 7, "name": "Girokonto", "type": "giro",
        "balance_cents": 123456, "balance_known": True,
        "balance_date": "2026-11-01", "transaction_count": 42,
        "in_forecast": True, "group": "alltag", "matures_on": None,
        "previous_value_cents": None, "previous_value_date": None,
    }]
    assert dto["forecast"]["upcoming"] == [{
        "date": "2026-11-05", "name": "Miete",
        "amount_cents": -80000, "interval": "monatlich", "overdue": False,
    }]
    assert dto["budgets"][0]["remaining_cents"] == 10000
    assert dto["month"]["balance_cents"] == 100000
    assert dto["alerts"] == [{
        "level": "warning",
        "title": "Budget Lebensmittel überschritten",
        "message": "50,00 € von 45,00 € ausgegeben.",
    }]

    serialized = repr(dto)
    for forbidden in (
        "DE89370400440532013000", "private-provider-reference",
        "internal-contract-key", "private-alert-key", "private-contract-key",
        "must not escape", "provider_id", '"contracts"',
    ):
        assert forbidden not in serialized


def test_overview_rejects_naive_timestamp():
    with pytest.raises(ValueError):
        serialize_overview({}, [], as_of=datetime(2026, 11, 3, 12, 0))


def test_transaction_list_returns_allowlisted_fields_and_paginates(db):
    account_id = db.insert("accounts", {
        "name": "Girokonto", "kind": "giro",
        "iban": "DE89370400440532013000", "bank": "Musterbank",
    })
    category_id = db.insert("categories", {"name": "Lebensmittel", "kind": "expense"})
    for day, amount, merchant in (
        ("2026-11-01", -1200, "Supermarkt"),
        ("2026-11-02", -3400, "Bäckerei"),
        ("2026-10-31", -500, "Kiosk"),
    ):
        db.insert("transactions", {
            "account_id": account_id, "booking_date": day, "value_date": day,
            "amount_cents": amount, "currency": "EUR", "counterparty": merchant,
            "counterparty_iban": "DE89370400440532013000",
            "purpose": "  Einkauf\n  mit Karte  " * 20,
            "category_id": category_id, "hash": f"secret-hash-{day}",
            "source": "private-import-source",
        })

    first = list_transactions(db, limit=1, offset=0, month="2026-11")
    second = list_transactions(db, limit=1, offset=1, month="2026-11")

    assert first["total"] == 2
    assert first["limit"] == 1 and first["offset"] == 0
    assert len(first["items"]) == len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    item = first["items"][0]
    assert item["counterparty"] == "Bäckerei"
    assert item["account_name"] == "Girokonto"
    assert item["category"] == {"id": category_id, "name": "Lebensmittel"}
    assert item["purpose"] is not None and len(item["purpose"]) <= 140

    serialized = repr(first)
    for forbidden in (
        "DE89370400440532013000", "secret-hash-", "private-import-source",
        "counterparty_iban", '"hash"', '"source"', '"iban"',
    ):
        assert forbidden not in serialized


def test_transaction_filters_by_account_and_category(db):
    account_id = db.insert("accounts", {"name": "Girokonto"})
    other_account_id = db.insert("accounts", {"name": "Tagesgeld"})
    category_id = db.insert("categories", {"name": "Mobilität", "kind": "expense"})
    other_category_id = db.insert("categories", {"name": "Freizeit", "kind": "expense"})
    rows = (
        (account_id, category_id, "2026-11-01", "Tankstelle"),
        (account_id, other_category_id, "2026-11-02", "Kino"),
        (other_account_id, category_id, "2026-11-03", "Ladestation"),
    )
    for account, category, day, merchant in rows:
        db.insert("transactions", {
            "account_id": account, "category_id": category,
            "booking_date": day, "amount_cents": -1000,
            "counterparty": merchant,
        })

    selected = list_transactions(db, account_id=account_id, category_id=category_id)
    assert selected["total"] == 1
    assert selected["items"][0]["counterparty"] == "Tankstelle"


def test_transaction_list_excludes_archived_accounts(db):
    active = db.insert("accounts", {"name": "Aktiv", "archived": 0})
    archived = db.insert("accounts", {"name": "Archiv", "archived": 1})
    for account_id, merchant in ((active, "Aktiv"), (archived, "Archiv")):
        db.insert("transactions", {
            "account_id": account_id, "booking_date": "2026-11-01",
            "amount_cents": -100, "counterparty": merchant,
        })

    result = list_transactions(db)
    assert result["total"] == 1
    assert result["items"][0]["account_name"] == "Aktiv"


def test_transaction_pagination_limits_and_query_validation(db):
    assert list_transactions(db)["limit"] == DEFAULT_PAGE_SIZE
    assert list_transactions(db, limit=MAX_PAGE_SIZE)["limit"] == MAX_PAGE_SIZE
    for kwargs in (
        {"limit": 0}, {"limit": MAX_PAGE_SIZE + 1}, {"offset": -1},
        {"month": "2026-13"}, {"month": "03-2026"},
        {"account_id": 0}, {"category_id": -1}, {"limit": True},
    ):
        with pytest.raises(MobileQueryError):
            list_transactions(db, **kwargs)


def _search_fixture(db):
    account_id = db.insert("accounts", {"name": "Girokonto"})
    rows = (
        ("2026-11-01", -4217, "Supermarkt Nord", "Wocheneinkauf", None, 0),
        ("2026-11-02", -1190, "Bäckerei", "Brötchen", "100% lecker", 0),
        ("2026-11-03", 12000, "Erstattung", "Rückzahlung Supermarkt", None, 0),
        ("2026-11-04", -50000, "Tagesgeld", "Umbuchung", None, 1),
        ("2026-11-05", 50000, "Girokonto", "Umbuchung", None, 1),
        ("2026-11-06", -900, "Kiosk_7", "Zeitung", None, 0),
    )
    for day, cents, counterparty, purpose, note, transfer in rows:
        db.insert("transactions", {
            "account_id": account_id, "booking_date": day, "amount_cents": cents,
            "counterparty": counterparty, "purpose": purpose, "note": note,
            "is_transfer": transfer,
        })


def _names(result):
    return [item["counterparty"] for item in result["items"]]


def test_transaction_search_matches_counterparty_purpose_and_note(db):
    _search_fixture(db)

    assert _names(list_transactions(db, q="supermarkt")) == ["Erstattung", "Supermarkt Nord"]
    assert _names(list_transactions(db, q="  Brötchen ")) == ["Bäckerei"]
    assert _names(list_transactions(db, q="lecker")) == ["Bäckerei"]
    assert list_transactions(db, q="gibt es nicht")["total"] == 0
    # Leere Suche ist keine Suche.
    assert list_transactions(db, q="   ")["total"] == 6


def test_transaction_search_takes_wildcards_literally(db):
    _search_fixture(db)

    assert _names(list_transactions(db, q="100%")) == ["Bäckerei"]
    assert _names(list_transactions(db, q="_7")) == ["Kiosk_7"]
    assert list_transactions(db, q="%")["total"] == 1
    assert list_transactions(db, q="_")["total"] == 1


def test_transaction_kind_splits_income_and_expenses_without_transfers(db):
    _search_fixture(db)

    assert _names(list_transactions(db, kind="in")) == ["Erstattung"]
    assert _names(list_transactions(db, kind="out")) == ["Kiosk_7", "Bäckerei", "Supermarkt Nord"]
    assert _names(list_transactions(db, kind="out", q="supermarkt")) == ["Supermarkt Nord"]
    assert list_transactions(db, kind="")["total"] == 6


def test_transaction_search_rejects_invalid_parameters(db):
    import pytest

    from kassensturz.mobile_read import MAX_SEARCH_LENGTH, MobileQueryError

    for arguments in ({"kind": "transfer"}, {"kind": "IN"}, {"q": "x" * (MAX_SEARCH_LENGTH + 1)}, {"q": 5}):
        with pytest.raises(MobileQueryError):
            list_transactions(db, **arguments)
    assert list_transactions(db, q="x" * MAX_SEARCH_LENGTH)["total"] == 0


def _stats_fixture(db):
    from datetime import date as _date

    month = _date.today().strftime("%Y-%m")
    account_id = db.insert("accounts", {"name": "Girokonto", "in_forecast": 1})
    food = db.insert("categories", {"name": "Lebensmittel", "kind": "expense"})
    bakery = db.insert("categories", {"name": "Bäcker", "kind": "expense", "parent_id": food})
    leisure = db.insert("categories", {"name": "Freizeit", "kind": "expense"})
    rows = (
        (-6000, "Supermarkt", food, 0),
        (-1500, "Bäckerei", bakery, 0),
        (-2500, "Kino", leisure, 0),
        (-40000, "Tagesgeld", None, 1),
        (200000, "Gehalt", None, 0),
    )
    for cents, name, category, transfer in rows:
        db.insert("transactions", {
            "account_id": account_id, "booking_date": f"{month}-01", "amount_cents": cents,
            "counterparty": name, "category_id": category, "is_transfer": transfer,
        })
    return month


def test_stats_group_spending_by_top_category_without_transfers(db):
    from kassensturz.mobile_read import CURVE_PAST_DAYS, get_stats

    month = _stats_fixture(db)
    stats = get_stats(db)

    assert stats["month"] == {
        "month": month, "income_cents": 200000, "expense_cents": 10000, "balance_cents": 190000,
    }
    assert [(item["name"], item["cents"], item["share"]) for item in stats["categories"]] == [
        ("Lebensmittel", 7500, 0.75),
        ("Freizeit", 2500, 0.25),
    ]
    assert len(stats["history"]) == 12
    assert stats["history"][-1] == {"month": month, "income_cents": 200000, "expense_cents": 10000}

    curve = stats["balance_curve"]
    booked = [point for point in curve["points"] if not point["forecast"]]
    planned = [point for point in curve["points"] if point["forecast"]]
    assert len(booked) == CURVE_PAST_DAYS and booked[-1]["date"] == curve["today"]
    assert planned and planned[0]["date"] > curve["today"]
    assert set(curve["low_point"]) == {"date", "cents"}

    serialized = repr(stats)
    for forbidden in ("iban", "hash", "Supermarkt", "Gehalt"):
        assert forbidden not in serialized


def test_stats_for_another_month_and_invalid_month(db):
    import pytest

    from kassensturz.mobile_read import MobileQueryError, get_stats

    _stats_fixture(db)
    empty = get_stats(db, month="2020-01")
    assert empty["month"] == {"month": "2020-01", "income_cents": 0, "expense_cents": 0, "balance_cents": 0}
    assert empty["categories"] == []
    with pytest.raises(MobileQueryError):
        get_stats(db, month="2026-13")
