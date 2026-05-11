"""Ring-buffered price history, keyed by (asset_class, symbol)."""

from __future__ import annotations

import sqlite3
from collections import deque
from collections.abc import Iterable
from datetime import datetime, timezone

DEFAULT_MAXLEN = 20


class SeriesStore:
    def __init__(
        self,
        maxlen: int = DEFAULT_MAXLEN,
        db: sqlite3.Connection | None = None,
    ) -> None:
        self.maxlen = maxlen
        self._buffers: dict[tuple[str, str], deque[float]] = {}
        self._db = db
        if db is not None:
            self._load_from_db(db)

    def _load_from_db(self, db: sqlite3.Connection) -> None:
        rows = db.execute("""
            SELECT asset_class, symbol, price FROM (
                SELECT asset_class, symbol, price,
                       ROW_NUMBER() OVER (
                           PARTITION BY asset_class, symbol
                           ORDER BY id DESC
                       ) AS rn
                FROM prices
            ) WHERE rn <= ?
            ORDER BY asset_class, symbol, rn DESC
        """, (self.maxlen,)).fetchall()
        for row in rows:
            self.append(row["asset_class"], row["symbol"], row["price"], _persist=False)

    def append(
        self,
        asset_class: str,
        symbol: str,
        price: float,
        *,
        _persist: bool = True,
    ) -> None:
        key = (asset_class, symbol)
        buf = self._buffers.get(key)
        if buf is None:
            buf = deque(maxlen=self.maxlen)
            self._buffers[key] = buf
        buf.append(price)
        if _persist and self._db is not None:
            self._db.execute(
                "INSERT INTO prices (asset_class, symbol, price, recorded_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    asset_class,
                    symbol,
                    price,
                    datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
                ),
            )

    def get(self, asset_class: str, symbol: str) -> list[float]:
        buf = self._buffers.get((asset_class, symbol))
        return list(buf) if buf is not None else []

    def extend_from_snapshot(
        self, asset_class: str, quotes: Iterable
    ) -> None:
        for q in quotes:
            if q.price > 0:
                self.append(asset_class, q.symbol, q.price)
