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

CREATE TABLE IF NOT EXISTS provider_contacts(
  provider_key TEXT PRIMARY KEY,
  provider_name TEXT NOT NULL,
  email TEXT,
  postal_address TEXT,
  cancellation_url TEXT,
  contact_url TEXT,
  status TEXT NOT NULL DEFAULT 'unverified',
  checked_at TEXT,
  notes TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_contact_sources(
  id INTEGER PRIMARY KEY,
  provider_key TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'official',
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  excerpt TEXT,
  UNIQUE(provider_key, url)
);
CREATE INDEX IF NOT EXISTS provider_sources_provider ON provider_contact_sources(provider_key);

CREATE TABLE IF NOT EXISTS cancellation_events(
  id INTEGER PRIMARY KEY,
  contract_key TEXT NOT NULL,
  provider_key TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'ordinary',
  status TEXT NOT NULL DEFAULT 'prepared',
  prepared_at TEXT NOT NULL,
  handed_off_at TEXT,
  user_confirmed_sent_at TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS cancellation_events_contract ON cancellation_events(contract_key, prepared_at);

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

CREATE TABLE IF NOT EXISTS eb_sessions(
  id INTEGER PRIMARY KEY,
  session_id TEXT,
  aspsp_name TEXT NOT NULL,
  aspsp_country TEXT NOT NULL,
  valid_until TEXT,
  status TEXT DEFAULT 'active',
  history_days INTEGER DEFAULT 365,
  last_sync TEXT,
  last_status TEXT,
  created TEXT
);

CREATE TABLE IF NOT EXISTS inbox(
  filename TEXT PRIMARY KEY,
  size INTEGER,
  mtime REAL,
  status TEXT,
  message TEXT,
  format TEXT,
  count INTEGER,
  created TEXT
);

CREATE TABLE IF NOT EXISTS mobile_pairings(
  id INTEGER PRIMARY KEY,
  secret_hash TEXT NOT NULL UNIQUE CHECK(length(trim(secret_hash)) > 0),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  expires_at TEXT NOT NULL CHECK(length(trim(expires_at)) > 0),
  consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS mobile_pairings_expiry ON mobile_pairings(expires_at);

CREATE TABLE IF NOT EXISTS mobile_devices(
  id TEXT NOT NULL PRIMARY KEY CHECK(length(trim(id)) > 0),
  name TEXT NOT NULL CHECK(length(trim(name)) > 0),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  last_used_at TEXT,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS mobile_devices_active ON mobile_devices(revoked_at, last_used_at);

CREATE TABLE IF NOT EXISTS mobile_tokens(
  token_hash TEXT NOT NULL PRIMARY KEY CHECK(length(trim(token_hash)) > 0),
  device_id TEXT NOT NULL CHECK(length(trim(device_id)) > 0),
  token_type TEXT NOT NULL CHECK(token_type IN ('access', 'refresh')),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  expires_at TEXT NOT NULL CHECK(length(trim(expires_at)) > 0),
  revoked_at TEXT,
  replaced_by_hash TEXT
);
CREATE INDEX IF NOT EXISTS mobile_tokens_device ON mobile_tokens(device_id, token_type);
CREATE INDEX IF NOT EXISTS mobile_tokens_expiry ON mobile_tokens(expires_at);
"""

# Spalten, die nach Version 0.1.0 dazugekommen sind
MIGRATIONS = {
    "accounts": [("eb_session_id", "INTEGER"), ("eb_uid", "TEXT"), ("eb_ident", "TEXT")],
    "cancellation_events": [("provider_confirmed_at", "TEXT"), ("aborted_at", "TEXT")],
}


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path):
        # Financial data lives in a private directory. Restrict the directory
        # as well as the main database file so SQLite WAL/SHM sidecars inherit
        # a private access boundary even when their own mode depends on umask.
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._depth = 0

    def close(self) -> None:
        """Write the WAL into the database file and close the connection.

        Called on shutdown: Home Assistant stops the app for a cold backup, and
        the backup then holds one complete database file instead of a database
        plus write-ahead log. A running transaction finishes first (lock).
        """
        with self.lock:
            try:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                self.conn.close()

    def _migrate(self) -> None:
        for table, cols in MIGRATIONS.items():
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, typ in cols:
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
        self._migrate_mobile_tables()

    def _migrate_mobile_tables(self) -> None:
        """Härtet die noch nicht produktiv genutzten Mobile-Tabellen verlustfrei nach."""
        specs = {
            "mobile_pairings": {
                "marker": "check(length(trim(secret_hash)) > 0)",
                "columns": "id, secret_hash, created_at, expires_at, consumed_at",
                "ddl": """
                    CREATE TABLE mobile_pairings__migration(
                      id INTEGER PRIMARY KEY,
                      secret_hash TEXT NOT NULL UNIQUE CHECK(length(trim(secret_hash)) > 0),
                      created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
                      expires_at TEXT NOT NULL CHECK(length(trim(expires_at)) > 0),
                      consumed_at TEXT
                    )
                """,
            },
            "mobile_devices": {
                "marker": "check(length(trim(id)) > 0)",
                "columns": "id, name, created_at, last_used_at, revoked_at",
                "ddl": """
                    CREATE TABLE mobile_devices__migration(
                      id TEXT NOT NULL PRIMARY KEY CHECK(length(trim(id)) > 0),
                      name TEXT NOT NULL CHECK(length(trim(name)) > 0),
                      created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
                      last_used_at TEXT,
                      revoked_at TEXT
                    )
                """,
            },
            "mobile_tokens": {
                "marker": "check(length(trim(token_hash)) > 0)",
                "columns": "token_hash, device_id, token_type, created_at, expires_at, revoked_at, replaced_by_hash",
                "ddl": """
                    CREATE TABLE mobile_tokens__migration(
                      token_hash TEXT NOT NULL PRIMARY KEY CHECK(length(trim(token_hash)) > 0),
                      device_id TEXT NOT NULL CHECK(length(trim(device_id)) > 0),
                      token_type TEXT NOT NULL CHECK(token_type IN ('access', 'refresh')),
                      created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
                      expires_at TEXT NOT NULL CHECK(length(trim(expires_at)) > 0),
                      revoked_at TEXT,
                      replaced_by_hash TEXT
                    )
                """,
            },
        }
        rebuild = []
        for table, spec in specs.items():
            row = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            definition = (row[0] or "").lower() if row else ""
            if spec["marker"] not in definition:
                rebuild.append((table, spec))

        if rebuild:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for table, spec in rebuild:
                    temporary = f"{table}__migration"
                    self.conn.execute(f"DROP TABLE IF EXISTS {temporary}")
                    self.conn.execute(spec["ddl"])
                    self.conn.execute(
                        f"INSERT INTO {temporary} ({spec['columns']}) "
                        f"SELECT {spec['columns']} FROM {table}"
                    )
                    self.conn.execute(f"DROP TABLE {table}")
                    self.conn.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS mobile_pairings_expiry ON mobile_pairings(expires_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS mobile_devices_active ON mobile_devices(revoked_at, last_used_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS mobile_tokens_device ON mobile_tokens(device_id, token_type)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS mobile_tokens_expiry ON mobile_tokens(expires_at)"
        )

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

    def execute_count(self, sql: str, params=()) -> int:
        """Führt ein Statement aus und gibt die Anzahl geänderter Zeilen zurück."""
        with self.lock:
            cur = self.conn.execute(sql, params)
            return cur.rowcount

    def executemany(self, sql: str, seq) -> None:
        with self.lock:
            self.conn.executemany(sql, seq)

    @contextmanager
    def tx(self, *, immediate: bool = False):
        """Verschachtelbare Transaktion; immediate reserviert frühzeitig den Schreibzugriff."""
        with self.lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
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


def close_db() -> None:
    """Close the shared database on shutdown (see Database.close)."""
    global _db
    if _db is not None:
        database, _db = _db, None
        database.close()


def reset_db_for_tests(path: Path) -> Database:
    global _db
    _db = Database(path)
    return _db
