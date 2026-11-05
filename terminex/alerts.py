"""Alert dataclass and DAO.

An alert fires when ``price`` crosses ``threshold`` in the ``op``
direction. Non-recurring alerts auto-deactivate on fire; recurring
ones stay active (but only fire again after the price leaves the
triggered region, so we don't spam).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

Op = Literal[">", "<"]


@dataclass(frozen=True)
class Alert:
    id: int
    asset_class: str
    symbol: str
    op: Op
    threshold: float
    recurring: bool
    active: bool
    created_at: str
    last_fired_at: str | None


def _now_utc_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def create(
    conn: sqlite3.Connection,
    *,
    asset_class: str,
    symbol: str,
    op: Op,
    threshold: float,
    recurring: bool = False,
) -> Alert:
    cur = conn.execute(
        """
        INSERT INTO alerts
          (asset_class, symbol, op, threshold, recurring, active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (asset_class, symbol, op, threshold, int(recurring), _now_utc_iso()),
    )
    return get(conn, cur.lastrowid)


def get(conn: sqlite3.Connection, alert_id: int) -> Alert:
    row = conn.execute(
        "SELECT * FROM alerts WHERE id = ?", (alert_id,)
    ).fetchone()
    if row is None:
        raise KeyError(alert_id)
    return _row_to_alert(row)


def list_active(conn: sqlite3.Connection) -> list[Alert]:
    rows = conn.execute(
        "SELECT * FROM alerts WHERE active = 1 ORDER BY id"
    ).fetchall()
    return [_row_to_alert(r) for r in rows]


def list_all(conn: sqlite3.Connection) -> list[Alert]:
    rows = conn.execute("SELECT * FROM alerts ORDER BY active DESC, id").fetchall()
    return [_row_to_alert(r) for r in rows]


def delete(conn: sqlite3.Connection, alert_id: int) -> bool:
    cur = conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    return cur.rowcount > 0


def deactivate(conn: sqlite3.Connection, alert_id: int) -> None:
    conn.execute("UPDATE alerts SET active = 0 WHERE id = ?", (alert_id,))


def record_fire(
    conn: sqlite3.Connection, alert_id: int, price: float
) -> None:
    ts = _now_utc_iso()
    conn.execute(
        "INSERT INTO fires (alert_id, fired_at, price) VALUES (?, ?, ?)",
        (alert_id, ts, price),
    )
    conn.execute(
        "UPDATE alerts SET last_fired_at = ? WHERE id = ?",
        (ts, alert_id),
    )


# A recurring alert re-arms this long after it fires. It stops a price that
# hovers at the threshold from notifying on every poll, and it is longer
# than the slowest feed's poll interval (FX, 5 min), so a second terminex
# on the same database that sees the same crossing later does not fire it
# again.
RECURRING_COOLDOWN_SECONDS = 300


def claim_fire(conn: sqlite3.Connection, alert: Alert, price: float) -> bool:
    """Atomically take ownership of a fire; False if another instance won.

    One-shot alerts are claimed by flipping ``active`` from 1 to 0;
    recurring alerts by moving ``last_fired_at`` forward when it is older
    than ``RECURRING_COOLDOWN_SECONDS``. Only the claimant records the fire.
    """
    now = datetime.now(tz=timezone.utc)
    ts = now.isoformat(timespec="seconds")
    if alert.recurring:
        cutoff = (now - timedelta(seconds=RECURRING_COOLDOWN_SECONDS)).isoformat(
            timespec="seconds"
        )
        cur = conn.execute(
            "UPDATE alerts SET last_fired_at = ? WHERE id = ? AND active = 1"
            " AND (last_fired_at IS NULL OR last_fired_at < ?)",
            (ts, alert.id, cutoff),
        )
    else:
        cur = conn.execute(
            "UPDATE alerts SET active = 0, last_fired_at = ?"
            " WHERE id = ? AND active = 1",
            (ts, alert.id),
        )
    if cur.rowcount != 1:
        return False
    conn.execute(
        "INSERT INTO fires (alert_id, fired_at, price) VALUES (?, ?, ?)",
        (alert.id, ts, price),
    )
    return True


def count_active(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE active = 1"
    ).fetchone()[0]


def _row_to_alert(row: sqlite3.Row) -> Alert:
    return Alert(
        id=row["id"],
        asset_class=row["asset_class"],
        symbol=row["symbol"],
        op=row["op"],
        threshold=row["threshold"],
        recurring=bool(row["recurring"]),
        active=bool(row["active"]),
        created_at=row["created_at"],
        last_fired_at=row["last_fired_at"],
    )
