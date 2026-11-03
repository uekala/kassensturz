"""SQLite-Speicher. Eine Verbindung, durch ein Lock serialisiert – für einen Haushalt völlig ausreichend."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("KASSENSTURZ_DATA", "/data"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS connections(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  blz TEXT NOT NULL,
  login TEXT NOT NULL,
  customer_id TEXT,
  server TEXT NOT NULL,
  tan_mechanism TEXT,
  tan_medium TEXT,
  client_state BLOB,
  history_days INTEGER DEFAULT 365,
  last_sync TEXT,
  last_status TEXT,
  created TEXT
);

CREATE TABLE IF NOT EXISTS accounts(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'giro',
  iban TEXT,
  bank TEXT,
  connection_id INTEGER,
  fints_ref TEXT,
  currency TEXT DEFAULT 'EUR',
  balance_cents INTEGER,
  balance_date TEXT,
  settlement_pattern TEXT,
  in_forecast INTEGER DEFAULT 1,
  archived INTEGER DEFAULT 0,
  demo INTEGER DEFAULT 0,
  sort INTEGER DEFAULT 0,
  created TEXT
);

CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  parent_id INTEGER,
  kind TEXT NOT NULL DEFAULT 'expense',
  color TEXT,
  budget_cents INTEGER,
  sort INTEGER DEFAULT 0,
  builtin_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL,
  booking_date TEXT NOT NULL,
  value_date TEXT,
  amount_cents INTEGER NOT NULL,
  currency TEXT DEFAULT 'EUR',
  counterparty TEXT,
  counterparty_iban TEXT,
  purpose TEXT,
  booking_text TEXT,
  creditor_id TEXT,
  mandate_ref TEXT,
  end_to_end TEXT,
  category_id INTEGER,
  category_locked INTEGER DEFAULT 0,
  rule_ref TEXT,
  is_transfer INTEGER DEFAULT 0,
  contract_key TEXT,
  note TEXT,
  source TEXT,
  import_id INTEGER,
  hash TEXT,
  created TEXT
);
CREATE INDEX IF NOT EXISTS tx_account_date ON transactions(account_id, booking_date);
CREATE INDEX IF NOT EXISTS tx_date ON transactions(booking_date);
CREATE INDEX IF NOT EXISTS tx_hash ON transactions(account_id, hash);

CREATE TABLE IF NOT EXISTS splits(
  id INTEGER PRIMARY KEY,
  tx_id INTEGER NOT NULL,
  amount_cents INTEGER NOT NULL,
  category_id INTEGER,
  note TEXT
);
CREATE INDEX IF NOT EXISTS splits_tx ON splits(tx_id);

CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY,
  pattern TEXT NOT NULL,
  field TEXT NOT NULL DEFAULT 'any',
  sign TEXT NOT NULL DEFAULT 'any',
  category_id INTEGER,
  mark_transfer INTEGER DEFAULT 0,
  priority INTEGER DEFAULT 100,
  enabled INTEGER DEFAULT 1,
  created TEXT
);

CREATE TABLE IF NOT EXISTS contracts(
  key TEXT PRIMARY KEY,
  name TEXT,
  counterparty TEXT,
  kind TEXT DEFAULT 'expense',
  interval TEXT,
  amount_cents INTEGER,
  prev_amount_cents INTEGER,
  first_date TEXT,
  last_date TEXT,
  next_due TEXT,
  count INTEGER DEFAULT 0,
  category_id INTEGER,
  account_id INTEGER,
  status TEXT DEFAULT 'detected',
  active INTEGER DEFAULT 1,
  manual INTEGER DEFAULT 0,
  match_pattern TEXT,
  customer_no TEXT,
  provider_address TEXT,
  provider_email TEXT,
  contract_end TEXT,
  notice_months INTEGER,
  cancelled_on TEXT,
  cancel_effective TEXT,
  notes TEXT,
  price_change_ack INTEGER,
  updated TEXT
);

CREATE TABLE IF NOT EXISTS imports(
  id INTEGER PRIMARY KEY,
  account_id INTEGER,
  source TEXT,
  filename TEXT,
  created TEXT,
  added INTEGER,
  skipped INTEGER
);

CREATE TABLE IF NOT EXISTS csv_profiles(
  signature TEXT PRIMARY KEY,
  mapping TEXT,
  account_id INTEGER,
  updated TEXT
);

CREATE TABLE IF NOT EXISTS notices(
  key TEXT PRIMARY KEY,
  created TEXT
);
"""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.executescript(SCHEMA)
        self._depth = 0

    # --- Grundoperationen -------------------------------------------------
    def query(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params=()) -> dict | None:
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def scalar(self, sql: str, params=()):
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
            return row[0] if row else None

    def execute(self, sql: str, params=()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, params)
            return cur.lastrowid

    def executemany(self, sql: str, seq) -> None:
        with self.lock:
            self.conn.executemany(sql, seq)

    @contextmanager
    def tx(self):
        """Verschachtelbare Transaktion."""
        with self.lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN")
            self._depth += 1
            try:
                yield self
            except Exception:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self.conn.execute("COMMIT")

    def insert(self, table: str, data: dict) -> int:
        cols = ", ".join(data.keys())
        marks = ", ".join("?" for _ in data)
        return self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))

    def update(self, table: str, key_col: str, key, data: dict) -> None:
        if not data:
            return
        sets = ", ".join(f"{k} = ?" for k in data)
        self.execute(f"UPDATE {table} SET {sets} WHERE {key_col} = ?", (*data.values(), key))

    # --- Einstellungen ------------------------------------------------------
    def get_setting(self, key: str, default=None):
        row = self.one("SELECT value FROM settings WHERE key = ?", (key,))
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return default

    def set_setting(self, key: str, value) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(DATA_DIR / "kassensturz.sqlite")
    return _db


def reset_db_for_tests(path: Path) -> Database:
    global _db
    _db = Database(path)
    return _db
