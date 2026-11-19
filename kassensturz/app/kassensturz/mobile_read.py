"""Explicit, privacy-minimizing read DTOs for the future mobile API.

No HTTP routes are registered here. Functions return allowlisted dictionaries and
never expose raw SQLite rows or provider/credential fields.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from . import analytics, contracts, expected, mobile_write, options, planned, savings, services
from .db import Database


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_PURPOSE_LENGTH = 140
MAX_COUNTERPARTY_LENGTH = 100
_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class MobileQueryError(ValueError):
    """A mobile list query contains invalid or out-of-range parameters."""


def _text(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    if not normalized:
        return None
    return normalized[:maximum]


def _integer(value: Any, *, default: int, minimum: int, maximum: int, name: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise MobileQueryError(f"{name} must be an integer.")
    if isinstance(value, str):
        normalized = value.strip()
        if not re.fullmatch(r"[+-]?\d+", normalized):
            raise MobileQueryError(f"{name} must be an integer.")
        parsed = int(normalized)
    elif isinstance(value, int):
        parsed = value
    else:
        raise MobileQueryError(f"{name} must be an integer.")
    if not minimum <= parsed <= maximum:
        raise MobileQueryError(f"{name} is outside the permitted range.")
    return parsed


def _optional_positive_id(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, default=1, minimum=1, maximum=2**63 - 1, name=name)


def _validate_month(month: str | None) -> str | None:
    if month is None or month == "":
        return None
    if not isinstance(month, str) or not _MONTH_PATTERN.fullmatch(month):
        raise MobileQueryError("month must use YYYY-MM format.")
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise MobileQueryError("month must use YYYY-MM format.") from exc
    return month


MAX_SEARCH_LENGTH = 80
TRANSACTION_KINDS = ("in", "out")


def _validate_search(value: Any) -> str | None:
    """Return the trimmed search text, or None when nothing is searched."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise MobileQueryError("q must be text.")
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_SEARCH_LENGTH:
        raise MobileQueryError("q is too long.")
    return text


def _validate_kind(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if value not in TRANSACTION_KINDS:
        raise MobileQueryError("kind must be 'in' or 'out'.")
    return value


def _like_pattern(text: str) -> str:
    """Search for the text as typed: % and _ are ordinary characters."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _forecast_dto(source: dict) -> dict:
    low = source.get("low_point") or {}
    return {
        "today": source.get("today"),
        "balance_cents": int(source.get("balance_now") or 0),
        "free_cents": int(source.get("free_cents") or 0),
        "free_per_day_cents": int(source.get("free_per_day_cents") or 0),
        "period_end": source.get("period_end"),
        "period_label": _text(source.get("period_label"), 60),
        "days_left": int(source.get("days_left") or 0),
        "fixed_out_cents": int(source.get("fixed_out_cents") or 0),
        "fixed_in_cents": int(source.get("fixed_in_cents") or 0),
        "planned_out_cents": int(source.get("planned_out_cents") or 0),
        "variable_daily_cents": int(source.get("variable_daily_cents") or 0),
        "variable_expected_cents": int(source.get("variable_expected_cents") or 0),
        "buffer_cents": int(source.get("buffer_cents") or 0),
        "reserve": {
            "reserved_cents": int(source.get("reserve_cents") or 0),
            "monthly_cents": int(source.get("reserve_monthly_cents") or 0),
            "deducted": bool(source.get("reserve_deducted", False)),
            "items": [
                {
                    "name": _text(item.get("name"), MAX_COUNTERPARTY_LENGTH),
                    "amount_cents": int(item.get("amount_cents") or 0),
                    "next_due": item.get("next_due"),
                    "interval": _text(item.get("interval"), 32),
                    "monthly_cents": int(item.get("monthly_cents") or 0),
                    "reserved_cents": int(item.get("reserved_cents") or 0),
                }
                for item in source.get("reserve_items", [])
            ],
        },
        "month_end_cents": (
            int(source["month_end_cents"])
            if source.get("month_end_cents") is not None
            else None
        ),
        "low_point": {
            "date": low.get("date"),
            "balance_cents": int(low.get("cents") or 0),
        },
        "upcoming": [
            {
                "date": item.get("date"),
                "name": _text(item.get("name"), MAX_COUNTERPARTY_LENGTH),
                "amount_cents": int(item.get("amount_cents") or 0),
                "interval": _text(item.get("interval"), 32),
                "overdue": bool(item.get("overdue", False)),
            }
            for item in source.get("upcoming", [])
        ],
    }


def budget_items(budgets: list[dict]) -> list[dict]:
    """Budgets in der Form, in der die App sie bekommt."""
    return [
        {
            "category_id": int(item["category_id"]),
            "name": _text(item.get("name"), 80),
            "limit_cents": int(item.get("budget_cents") or 0),
            "spent_cents": int(item.get("spent_cents") or 0),
            "remaining_cents": int(item.get("left_cents") or 0),
            "state": item.get("state") if item.get("state") in {"ok", "warn", "over"} else "ok",
        }
        for item in budgets
    ]


def serialize_overview(
    summary: dict,
    alerts: list[dict],
    *,
    as_of: datetime | None = None,
    viewer: int | None = None,
) -> dict:
    """Map domain summaries to a stable, strictly allowlisted mobile DTO."""
    timestamp = as_of or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware.")
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)

    accounts = []
    for account in summary.get("accounts", []):
        accounts.append(
            {
                "id": int(account["id"]),
                "name": _text(account.get("name"), 80),
                "type": _text(account.get("kind"), 24),
                "balance_cents": int(account.get("balance_now") or 0),
                "balance_known": bool(account.get("balance_known", False)),
                "balance_date": account.get("balance_date"),
                "transaction_count": int(account.get("tx_count") or 0),
                "in_forecast": bool(account.get("in_forecast", True)),
                "group": account.get("group") or "alltag",
                "matures_on": account.get("matures_on"),
                "previous_value_cents": None
                if account.get("value_prev_cents") is None
                else int(account["value_prev_cents"]),
                "previous_value_date": account.get("value_prev_date"),
                # Depot, Kredit und Ähnliches ohne Bankabruf: Der Wert lässt sich am Handy eintragen.
                "value_editable": mobile_write.value_editable(account),
                # Fremde eigene Konten kommen hier gar nicht an.
                "ownership": mobile_write.ownership(account, viewer),
            }
        )

    budgets = budget_items(summary.get("budgets", []))

    month = summary.get("month") or {}
    month_dto = {
        "month": month.get("month"),
        "income_cents": int(month.get("income_cents") or 0),
        "expense_cents": int(month.get("expense_cents") or 0),
        "balance_cents": int(month.get("saldo_cents") or 0),
        "breakdown": [
            {
                "category_id": item.get("category_id"),
                "name": _text(item.get("name"), 80),
                "amount_cents": int(item.get("cents") or 0),
            }
            for item in month.get("breakdown", [])
        ],
    }

    alert_dto = []
    for item in alerts:
        if not (item.get("title") and item.get("text")):
            continue
        dto = {
            "level": item["level"] if item.get("level") in {"critical", "warning", "info"} else "info",
            "title": _text(item.get("title"), 120),
            "message": _text(item.get("text"), 300),
        }
        # Nur Hinweise, die die App erledigen kann, verraten ihre Kennung; die übrigen bleiben, wie sie waren.
        actions = alert_actions(item)
        if actions:
            dto.update({"key": _text(item.get("key"), 120), "actions": actions})
        alert_dto.append(dto)

    return {
        "as_of": timestamp.isoformat(),
        "currency": "EUR",
        "accounts": accounts,
        "forecast": _forecast_dto(summary.get("forecast") or {}),
        "month": month_dto,
        "budgets": budgets,
        "alerts": alert_dto,
    }


def alert_actions(item: dict) -> list[str]:
    if item.get("anomaly"):
        return ["ack"]
    if item.get("expected"):
        return ["received", "drop"]
    if item.get("planned"):
        return ["paid", "drop"]
    return []


def plans(db: Database) -> dict:
    """Offene geplante Ausgaben und erwartete Eingänge, so weit die Person sie sieht."""
    open_planned = planned.overview(db)["open"]
    open_expected = expected.overview(db)["open"]
    return {
        "planned": [
            {"id": int(p["id"]), "label": _text(p["label"], 80), "cents": int(p["cents"]), "due_date": p["due_date"],
             "account": _text(p["account"], 80), "overdue": bool(p["overdue"]), "in_forecast": bool(p["in_forecast"])}
            for p in open_planned
        ],
        "expected": [
            {"id": int(e["id"]), "label": _text(e["label"], 80), "cents": int(e["cents"]), "since": e["since"],
             "due_date": e["due_date"], "account": _text(e["account"], 80), "overdue": bool(e["overdue"])}
            for e in open_expected
        ],
        "planned_cents": sum(int(p["cents"]) for p in open_planned),
        "expected_cents": sum(int(e["cents"]) for e in open_expected),
    }


def get_overview(db: Database, *, as_of: datetime | None = None, view=None) -> dict:
    """Build a fresh mobile overview from the existing local domain services.

    Contracts are detected on the whole database; everything shown is read
    through ``view``, the part of it the device's person may see.
    """
    contracts.detect(db)
    db = view or db
    summary = services.build_summary(db)
    alert_items = services.alerts(db, summary)
    overview = serialize_overview(summary, alert_items, as_of=as_of, viewer=getattr(db, "person_id", None))
    overview["goals"] = [
        {
            "id": int(goal["id"]),
            "name": _text(goal["name"], 60),
            "target_cents": int(goal["target_cents"]),
            "saved_cents": int(goal["saved_cents"]),
            "rest_cents": int(goal["rest_cents"]),
            "due_date": goal["due_date"],
            "monthly_cents": goal["monthly_cents"],
            "status": goal["status"],
            "progress": goal["progress"],
            "ownership": "shared" if goal.get("owner_person_id") is None else "mine",
        }
        for goal in savings.list_goals(db)
    ]
    overview["plans"] = plans(db)
    return overview


MAX_STATS_CATEGORIES = 40
CURVE_PAST_DAYS = 30


def get_stats(db: Database, *, month: str | None = None) -> dict:
    """Return the figures behind the app's analysis page.

    Spending of one month by top-level category, income and expenses of the
    last twelve months, and the balance curve: the last days as booked, the
    coming days as forecast. Transfers between own accounts are left out, as
    everywhere else. Only names and amounts leave the server.
    """
    selected = _validate_month(month) or date.today().strftime("%Y-%m")
    stats = analytics.month_stats(db, selected)
    expense = int(stats["expense_cents"])
    categories = [
        {
            "category_id": item["category_id"],
            "name": str(item["name"]),
            "cents": int(item["cents"]),
            "share": round(item["cents"] / expense, 4) if expense > 0 else 0.0,
        }
        for item in stats["breakdown"][:MAX_STATS_CATEGORIES]
    ]
    history = [
        {
            "month": item["month"],
            "income_cents": int(item["income_cents"]),
            "expense_cents": int(item["expense_cents"]),
        }
        for item in analytics.monthly_totals(db, 12)
    ]
    forecast = analytics.forecast(db)
    points = [
        {"date": day, "cents": int(cents), "forecast": False}
        for day, cents in forecast["past"][-CURVE_PAST_DAYS:]
    ] + [
        {"date": day, "cents": int(cents), "forecast": True}
        for day, cents in forecast["future"]
    ]
    review = analytics.month_review(db, selected)
    return {
        "review": {
            "label": str(review["label"]),
            "has_data": bool(review["has_data"]),
            "complete": bool(review["complete"]),
            "saved_cents": int(review["saved_cents"]),
            "savings_rate": review["savings_rate"],
            "expense_change_cents": review["expense_change_cents"],
            "compared_months": int(review["compared_months"]),
            "notable": [str(name) for name in review["notable"]],
        },
        "month": {
            "month": selected,
            "income_cents": int(stats["income_cents"]),
            "expense_cents": expense,
            "balance_cents": int(stats["saldo_cents"]),
        },
        "categories": categories,
        "history": history,
        "balance_curve": {
            "today": forecast["today"],
            "low_point": {
                "date": forecast["low_point"]["date"],
                "cents": int(forecast["low_point"]["cents"]),
            },
            "points": points,
        },
    }


def get_year(db: Database, year: Any) -> dict:
    """The year in review for the app: totals, months, categories and the biggest single expenses.

    Compared with the year before as far as there are bookings, in the running year only up to the same
    day. Transfers between own accounts are left out."""
    today = date.today()
    if year is None or year == "":
        year = today.year
    if isinstance(year, str):
        if not (year.isascii() and year.isdigit() and len(year) == 4):
            raise MobileQueryError("year")
        year = int(year)
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= today.year:
        raise MobileQueryError("year")
    r = analytics.year_review(db, year, today=today)
    prev = r["previous"]

    def month_ref(item):
        return item and {"month": item["month"], "label": str(item["label"]), "saldo_cents": int(item["saldo_cents"])}

    return {
        "year": r["year"],
        "running": r["running"],
        "until": r["until"],
        "has_data": r["has_data"],
        "years": [int(y) for y in r["years"]],
        "income_cents": int(r["income_cents"]),
        "expense_cents": int(r["expense_cents"]),
        "saved_cents": int(r["saved_cents"]),
        "savings_rate": r["savings_rate"],
        "fixed_cents": int(r["fixed_cents"]),
        "count": int(r["count"]),
        "previous": prev and {k: int(prev[k]) for k in ("income_cents", "expense_cents", "saved_cents")},
        "months": [{"month": m["month"], "income_cents": int(m["income_cents"]),
                    "expense_cents": int(m["expense_cents"])} for m in r["months"] if not m["future"]],
        "best_month": month_ref(r["best_month"]),
        "worst_month": month_ref(r["worst_month"]),
        "categories": [{"name": str(c["name"]), "cents": int(c["cents"]), "share": c["share"],
                        "previous_cents": c["previous_cents"]} for c in r["categories"]],
        "biggest": [{"name": str(b["name"]), "amount_cents": int(b["amount_cents"]), "date": b["date"]}
                    for b in r["biggest"]],
    }


def get_afford(db: Database, amount_cents: Any) -> dict:
    """What a purchase of this amount today means for the rest of the period."""
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise MobileQueryError("amount_cents")
    if not 0 < amount_cents <= analytics.MAX_AFFORD_CENTS:
        raise MobileQueryError("amount_cents")
    threshold = int(options.load().get("warn_threshold") or 0) * 100
    return analytics.afford(analytics.forecast(db), amount_cents, threshold)


def list_transactions(
    db: Database,
    *,
    limit: int | None = None,
    offset: int | None = 0,
    month: str | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    q: str | None = None,
    kind: str | None = None,
    triage: bool = False,
) -> dict:
    """Return paginated transaction DTOs without internal or banking metadata.

    ``q`` searches counterparty, purpose and note; ``kind`` limits the list to
    income ("in") or expenses ("out"), both without transfers between own
    accounts, as in the web interface.
    """
    page_size = _integer(
        limit,
        default=DEFAULT_PAGE_SIZE,
        minimum=1,
        maximum=MAX_PAGE_SIZE,
        name="limit",
    )
    page_offset = _integer(
        offset,
        default=0,
        minimum=0,
        maximum=2**31 - 1,
        name="offset",
    )
    selected_month = _validate_month(month)
    selected_account = _optional_positive_id(account_id, "account_id")
    selected_category = _optional_positive_id(category_id, "category_id")
    search = _validate_search(q)
    selected_kind = _validate_kind(kind)

    where = ["a.archived = 0"]
    params: list[Any] = []
    if selected_month:
        where.append("substr(t.booking_date, 1, 7) = ?")
        params.append(selected_month)
    if selected_account is not None:
        where.append("t.account_id = ?")
        params.append(selected_account)
    if selected_category is not None:
        where.append("t.category_id = ?")
        params.append(selected_category)
    if search is not None:
        where.append(
            "(t.counterparty LIKE ? ESCAPE '\\' OR t.purpose LIKE ? ESCAPE '\\' "
            "OR t.note LIKE ? ESCAPE '\\')"
        )
        params.extend([_like_pattern(search)] * 3)
    if selected_kind == "in":
        where.append("t.amount_cents > 0 AND t.is_transfer = 0")
    elif selected_kind == "out":
        where.append("t.amount_cents < 0 AND t.is_transfer = 0")

    if triage:
        # Was noch niemand zugeordnet hat: ohne Kategorie oder im Auffangbecken.
        where.append(
            "t.is_transfer = 0 AND (t.category_id IS NULL "
            "OR c.builtin_key IN ('sonstiges', 'sonstige_einnahmen'))"
        )

    predicate = " AND ".join(where)
    total = db.scalar(
        "SELECT COUNT(*) FROM transactions AS t "
        "JOIN accounts AS a ON a.id = t.account_id "
        "LEFT JOIN categories AS c ON c.id = t.category_id "
        f"WHERE {predicate}",
        tuple(params),
    )
    rows = db.query(
        """
        SELECT
            t.id,
            t.account_id,
            t.note,
            t.source,
            t.tax_kind,
            t.warranty_until,
            (SELECT COUNT(*) FROM receipts AS r WHERE r.tx_id = t.id) AS receipt_count,
            t.booking_date,
            t.value_date,
            t.amount_cents,
            t.currency,
            t.counterparty,
            t.purpose,
            a.name AS account_name,
            t.category_id,
            c.name AS category_name
        FROM transactions AS t
        JOIN accounts AS a ON a.id = t.account_id
        LEFT JOIN categories AS c ON c.id = t.category_id
        WHERE
        """
        + predicate
        # Beim Zuordnen die größten Beträge zuerst: Sie verändern die Auswertung am meisten.
        + (" ORDER BY ABS(t.amount_cents) DESC, t.id DESC LIMIT ? OFFSET ?" if triage
           else " ORDER BY t.booking_date DESC, t.id DESC LIMIT ? OFFSET ?"),
        (*params, page_size, page_offset),
    )

    items = [
        {
            "id": int(row["id"]),
            "account_id": int(row["account_id"]),
            "booking_date": row["booking_date"],
            "value_date": row["value_date"],
            "amount_cents": int(row["amount_cents"]),
            "currency": row.get("currency") or "EUR",
            "counterparty": _text(row.get("counterparty"), MAX_COUNTERPARTY_LENGTH),
            "purpose": _text(row.get("purpose"), MAX_PURPOSE_LENGTH),
            "note": _text(row.get("note"), 300),
            "account_name": _text(row.get("account_name"), 80),
            "manual": row.get("source") == "manual",
            "tax_kind": row.get("tax_kind"),
            "warranty_until": row.get("warranty_until"),
            "receipt_count": int(row.get("receipt_count") or 0),
            "category": (
                {
                    "id": int(row["category_id"]),
                    "name": _text(row.get("category_name"), 80),
                }
                if row.get("category_id") is not None
                else None
            ),
        }
        for row in rows
    ]

    return {
        "items": items,
        "total": int(total or 0),
        "limit": page_size,
        "offset": page_offset,
    }


def triage(db: Database, limit: int | None = None) -> dict:
    """Buchungen, die noch keiner richtigen Kategorie zugeordnet sind."""
    page = list_transactions(db, limit=limit, triage=True)
    spent = db.scalar(
        "SELECT COALESCE(SUM(-t.amount_cents), 0) FROM transactions AS t "
        "JOIN accounts AS a ON a.id = t.account_id LEFT JOIN categories AS c ON c.id = t.category_id "
        "WHERE a.archived = 0 AND t.is_transfer = 0 AND t.amount_cents < 0 "
        "AND (t.category_id IS NULL OR c.builtin_key = 'sonstiges')"
    )
    # Vorschlag je Buchung, wenn der Bestand einen klaren Hinweis hergibt.
    from . import categorize

    hints = categorize.suggestions(db, [
        {"id": i["id"], "counterparty": i["counterparty"], "purpose": i["purpose"], "amount_cents": i["amount_cents"]}
        for i in page["items"]
    ])
    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM categories")} if hints else {}
    for item in page["items"]:
        hint = hints.get(item["id"])
        item["suggestion"] = {"id": hint, "name": names[hint]} if hint in names else None
    return {"items": page["items"], "total": page["total"], "expense_cents": int(spent or 0)}


NEWS_KEY = "mobile_news_seen"
NEWS_TOP = 3


def _news_marks(db: Database) -> dict:
    marks = db.get_setting(NEWS_KEY)
    return marks if isinstance(marks, dict) else {}


def news(db: Database, device_id: str) -> dict:
    """Was seit dem letzten „Gelesen" dieses Geräts dazugekommen ist.

    Gemerkt wird je Gerät die höchste gesehene Buchungs-ID. Beim ersten Aufruf
    gilt der aktuelle Stand als gelesen, damit nicht der ganze Bestand als neu erscheint.
    """
    newest = int(db.scalar("SELECT COALESCE(MAX(id), 0) FROM transactions") or 0)
    marks = _news_marks(db)
    seen = marks.get(device_id)
    if not isinstance(seen, int) or seen > newest:
        marks[device_id] = newest
        db.set_setting(NEWS_KEY, marks)
        seen = newest
    rows = db.query(
        "SELECT t.amount_cents, t.counterparty, t.purpose, t.booking_date, a.name AS account_name "
        "FROM transactions AS t JOIN accounts AS a ON a.id = t.account_id "
        "WHERE t.id > ? AND a.archived = 0 AND t.is_transfer = 0 ORDER BY ABS(t.amount_cents) DESC, t.id DESC",
        (seen,),
    )
    return {
        "count": len(rows),
        "income_cents": sum(r["amount_cents"] for r in rows if r["amount_cents"] > 0),
        "expense_cents": -sum(r["amount_cents"] for r in rows if r["amount_cents"] < 0),
        "largest": [
            {"label": _text(r["counterparty"] or r["purpose"], MAX_COUNTERPARTY_LENGTH) or "Buchung",
             "amount_cents": int(r["amount_cents"]), "booking_date": r["booking_date"],
             "account_name": _text(r["account_name"], 80)}
            for r in rows[:NEWS_TOP]
        ],
    }


def mark_news_seen(db: Database, device_id: str, known_devices: set[str] | None = None) -> None:
    marks = _news_marks(db)
    if known_devices is not None:
        marks = {key: value for key, value in marks.items() if key in known_devices}
    marks[device_id] = int(db.scalar("SELECT COALESCE(MAX(id), 0) FROM transactions") or 0)
    db.set_setting(NEWS_KEY, marks)


def papers_overview(db: Database, year: int | None = None) -> dict:
    """Steuerübersicht und Garantien ohne die einzelnen Buchungen der Steuerliste."""
    from . import papers

    tax = papers.tax_year(db, year if year and 1990 <= year <= 2200 else papers.default_year(db))

    def warranty(row: dict) -> dict:
        return {"id": int(row["id"]), "label": _text(row["label"], MAX_COUNTERPARTY_LENGTH),
                "amount_cents": int(row["amount_cents"]), "booking_date": row["booking_date"],
                "warranty_until": row["warranty_until"], "days_left": int(row["days_left"]),
                "receipt_count": int(row["receipt_count"] or 0)}

    found = papers.warranties(db)
    return {
        "tax": {
            "year": tax["year"], "years": tax["years"], "count": tax["count"], "total_cents": tax["total_cents"],
            "missing_receipts": tax["missing_receipts"],
            "groups": [{"kind": g["kind"], "label": g["label"], "count": g["count"], "total_cents": g["total_cents"],
                        "missing_receipts": g["missing_receipts"]} for g in tax["groups"]],
        },
        "warranties": {"running": [warranty(r) for r in found["running"]],
                       "expired": [warranty(r) for r in found["expired"]]},
    }
