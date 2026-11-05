"""Alert evaluation against live snapshots.

An alert fires when its condition holds and it is armed; firing disarms
it, and seeing the condition false re-arms it. That makes alerts fire on
*crossings* rather than every tick while the condition stays true. The
armed flag lives in the database (see ``alerts.claim_fire``), so it holds
across restarts and across several terminex windows.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import alerts as alerts_dao
from .alerts import Alert, _row_to_alert
from .quote import Snapshot


@dataclass(frozen=True)
class FireEvent:
    alert: Alert
    price: float


class AlertEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def evaluate(self, snapshot: Snapshot, asset_class: str) -> list[FireEvent]:
        quote_by_sym = {q.symbol: q.price for q in snapshot.quotes}
        rows = self.conn.execute(
            "SELECT * FROM alerts WHERE active = 1 AND asset_class = ?",
            (asset_class,),
        ).fetchall()

        fires: list[FireEvent] = []
        for row in rows:
            alert = _row_to_alert(row)
            price = quote_by_sym.get(alert.symbol)
            if price is None:
                continue
            if condition_met(alert.op, alert.threshold, price):
                if alert.armed and alerts_dao.claim_fire(self.conn, alert, price):
                    fires.append(FireEvent(alert=alert, price=price))
            elif not alert.armed:
                alerts_dao.rearm(self.conn, alert.id)
        return fires


def condition_met(op: str, threshold: float, price: float) -> bool:
    if op == ">":
        return price > threshold
    if op == "<":
        return price < threshold
    return False
