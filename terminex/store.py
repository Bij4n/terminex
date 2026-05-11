"""SQLite storage for alerts and audit logs.

Follows XDG spec: ``~/.local/share/terminex/terminex.db``. Opens in WAL
mode for single-writer/multi-reader friendliness. Schema is applied
idempotently on each ``connect()``.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_class     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    op              TEXT NOT NULL,      -- '>' or '<'
    threshold       REAL NOT NULL,
    recurring       INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    last_fired_at   TEXT
);

CREATE INDEX IF NOT EXISTS alerts_active_sym
    ON alerts(active, asset_class, symbol);

CREATE TABLE IF NOT EXISTS fires (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    INTEGER NOT NULL,
    fired_at    TEXT NOT NULL,
    price       REAL NOT NULL,
    FOREIGN KEY(alert_id) REFERENCES alerts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_class TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    price       REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS prices_lookup
    ON prices(asset_class, symbol, id);
"""

# Retain this many price observations per (asset_class, symbol).
_PRICES_KEEP = 50


def _prune_prices(conn: sqlite3.Connection) -> None:
    conn.execute("""
        DELETE FROM prices
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY asset_class, symbol
                           ORDER BY id DESC
                       ) AS rn
                FROM prices
            ) WHERE rn <= ?
        )
    """, (_PRICES_KEEP,))


def db_path() -> Path:
    base = (
        os.environ.get("XDG_DATA_HOME")
        or str(Path.home() / ".local" / "share")
    )
    return Path(base) / "terminex" / "terminex.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    _prune_prices(conn)
    return conn
