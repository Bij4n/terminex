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


# 0.4.0 read commodities from Stooq, which quoted these futures in US cents;
# from 0.5.0 every commodity price is USD per unit. A saved threshold at or
# above the value here can only be cents (none of these has ever traded near
# that many dollars), so it is divided by 100. Smaller ones already look like
# dollars and are left alone.
_CENT_THRESHOLDS: dict[str, float] = {
    "SI.F": 300.0,   # silver, $/oz
    "HG.F": 30.0,    # copper, $/lb
    "ZW.F": 50.0,    # wheat, $/bu
    "ZC.F": 30.0,    # corn, $/bu
    "ZS.F": 60.0,    # soybeans, $/bu
    "KC.F": 20.0,    # coffee, $/lb
    "SB.F": 3.0,     # sugar, $/lb
    "CT.F": 10.0,    # cotton, $/lb
}

SCHEMA_VERSION = 1


def _migrate(conn: sqlite3.Connection) -> list[str]:
    """Bring an older database up to ``SCHEMA_VERSION``; return notices."""
    notices: list[str] = []
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        converted = []
        rows = conn.execute(
            "SELECT id, symbol, threshold FROM alerts WHERE asset_class = 'commodity'"
        ).fetchall()
        for alert_id, symbol, threshold in rows:
            floor = _CENT_THRESHOLDS.get(symbol)
            if floor is not None and threshold >= floor:
                new = round(threshold / 100.0, 6)
                conn.execute(
                    "UPDATE alerts SET threshold = ? WHERE id = ?", (new, alert_id)
                )
                converted.append(f"{symbol} {threshold:g} → {new:g}")
        # Stored commodity prices are in the old units too.
        conn.execute("DELETE FROM prices WHERE asset_class = 'commodity'")
        if converted:
            notices.append(
                "commodity prices are now USD per unit; converted alert "
                "thresholds from cents: " + ", ".join(converted)
            )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return notices


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (and migrate) the on-disk store. See ``open_store`` for notices."""
    conn, _ = _connect(path)
    return conn


def _connect(path: Path | None) -> tuple[sqlite3.Connection, list[str]]:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    notices = _migrate(conn)
    _prune_prices(conn)
    return conn, notices


def connect_memory() -> sqlite3.Connection:
    """A throwaway in-memory store with the same schema."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn


def open_store(path: Path | None = None) -> tuple[sqlite3.Connection, list[str]]:
    """Open the on-disk store, or fall back to memory if it can't be written.

    Prices don't need the database, so an unwritable data directory should
    cost persistence, not the whole app. Returns ``(connection, notices)``:
    things the user should be told at startup (a fallback, a migration).
    """
    p = path or db_path()
    try:
        return _connect(p)
    except (OSError, sqlite3.Error) as exc:
        reason = getattr(exc, "strerror", None) or str(exc)
        return connect_memory(), [
            f"can't write {p.parent} ({reason}); alerts and trend history "
            "won't be saved this session"
        ]
