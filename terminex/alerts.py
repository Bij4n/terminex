"""Alert dataclass and DAO.

An alert fires when its condition (``price op threshold``) becomes true
while it is *armed*. Firing disarms it; seeing the condition false again
re-arms it. One-shot alerts also deactivate when they fire. Both flags
live in the database, so several terminex windows sharing it fire each
crossing once, and a restart doesn't re-fire an alert that already fired.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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
    armed: bool = True
    base: str = "USD"  # FX: base currency the threshold is quoted in


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
    armed: bool = True,
    base: str = "USD",
) -> Alert:
    """Create an alert. Pass ``armed=False`` when the condition already
    holds, so it fires on the next crossing rather than straight away."""
    cur = conn.execute(
        """
        INSERT INTO alerts
          (asset_class, symbol, op, threshold, recurring, active, armed, base, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            asset_class, symbol, op, threshold, int(recurring), int(armed),
            base.upper(), _now_utc_iso(),
        ),
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


def claim_fire(conn: sqlite3.Connection, alert: Alert, price: float) -> bool:
    """Atomically take ownership of a fire; False if it was already taken.

    The UPDATE only matches an active, armed alert, so when several
    instances see the same crossing exactly one of them records the fire.
    """
    ts = _now_utc_iso()
    one_shot = "" if alert.recurring else ", active = 0"
    cur = conn.execute(
        f"UPDATE alerts SET armed = 0, last_fired_at = ?{one_shot}"
        " WHERE id = ? AND active = 1 AND armed = 1",
        (ts, alert.id),
    )
    if cur.rowcount != 1:
        return False
    conn.execute(
        "INSERT INTO fires (alert_id, fired_at, price) VALUES (?, ?, ?)",
        (alert.id, ts, price),
    )
    return True


def rearm(conn: sqlite3.Connection, alert_id: int) -> None:
    """The condition is false again: the next time it holds, fire."""
    conn.execute(
        "UPDATE alerts SET armed = 1 WHERE id = ? AND active = 1 AND armed = 0",
        (alert_id,),
    )


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
        armed=bool(row["armed"]),
        base=row["base"],
    )
