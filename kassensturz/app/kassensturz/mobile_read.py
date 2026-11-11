"""Explicit, privacy-minimizing read DTOs for the future mobile API.

No HTTP routes are registered here. Functions return allowlisted dictionaries and
never expose raw SQLite rows or provider/credential fields.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from . import contracts, services
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
        "variable_daily_cents": int(source.get("variable_daily_cents") or 0),
        "variable_expected_cents": int(source.get("variable_expected_cents") or 0),
        "buffer_cents": int(source.get("buffer_cents") or 0),
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


def serialize_overview(
    summary: dict,
    alerts: list[dict],
    *,
    as_of: datetime | None = None,
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
            }
        )

    budgets = [
        {
            "category_id": int(item["category_id"]),
            "name": _text(item.get("name"), 80),
            "limit_cents": int(item.get("budget_cents") or 0),
            "spent_cents": int(item.get("spent_cents") or 0),
            "remaining_cents": int(item.get("left_cents") or 0),
            "state": item.get("state") if item.get("state") in {"ok", "warn", "over"} else "ok",
        }
        for item in summary.get("budgets", [])
    ]

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

    alert_dto = [
        {
            "level": item["level"] if item.get("level") in {"critical", "warning", "info"} else "info",
            "title": _text(item.get("title"), 120),
            "message": _text(item.get("text"), 300),
        }
        for item in alerts
        if item.get("title") and item.get("text")
    ]

    return {
        "as_of": timestamp.isoformat(),
        "currency": "EUR",
        "accounts": accounts,
        "forecast": _forecast_dto(summary.get("forecast") or {}),
        "month": month_dto,
        "budgets": budgets,
        "alerts": alert_dto,
    }


def get_overview(db: Database, *, as_of: datetime | None = None) -> dict:
    """Build a fresh mobile overview from the existing local domain services."""
    contracts.detect(db)
    summary = services.build_summary(db)
    alert_items = services.alerts(db, summary)
    return serialize_overview(summary, alert_items, as_of=as_of)


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

    predicate = " AND ".join(where)
    total = db.scalar(
        "SELECT COUNT(*) FROM transactions AS t "
        "JOIN accounts AS a ON a.id = t.account_id "
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
        + " ORDER BY t.booking_date DESC, t.id DESC LIMIT ? OFFSET ?",
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
