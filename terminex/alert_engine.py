"""Alert evaluation against live snapshots.

Holds in-memory ``last_price`` per (asset_class, symbol) to detect
threshold *crossings* rather than firing every tick while the
condition stays true.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import alerts as alerts_dao
from .alerts import Alert
from .quote import Snapshot


@dataclass(frozen=True)
class FireEvent:
    alert: Alert
    price: float


class AlertEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._last_price: dict[tuple[str, str], float] = {}

    def evaluate(self, snapshot: Snapshot, asset_class: str) -> list[FireEvent]:
        quote_by_sym = {q.symbol: q.price for q in snapshot.quotes}
        # Only load alerts for this asset_class
        rows = self.conn.execute(
            """
            SELECT * FROM alerts
            WHERE active = 1 AND asset_class = ?
            """,
            (asset_class,),
        ).fetchall()
        fires: list[FireEvent] = []
        for row in rows:
            alert = _row_to_alert(row)
            price = quote_by_sym.get(alert.symbol)
            if price is None:
                continue
            key = (asset_class, alert.symbol)
            prev = self._last_price.get(key)
            triggered = _is_triggered(alert, price, prev)
            if triggered:
                alerts_dao.record_fire(self.conn, alert.id, price)
                if not alert.recurring:
                    alerts_dao.deactivate(self.conn, alert.id)
                fires.append(FireEvent(alert=alert, price=price))
        # update last-seen prices for every symbol in this snapshot
        for sym, price in quote_by_sym.items():
            self._last_price[(asset_class, sym)] = price
        return fires


def _is_triggered(alert: Alert, price: float, prev: float | None) -> bool:
    if alert.op == ">":
        if price <= alert.threshold:
            return False
        # first observation OR prev did not satisfy the condition
        return prev is None or prev <= alert.threshold
    if alert.op == "<":
        if price >= alert.threshold:
            return False
        return prev is None or prev >= alert.threshold
    return False


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
