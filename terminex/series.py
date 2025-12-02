"""Ring-buffered price history, keyed by (asset_class, symbol)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

DEFAULT_MAXLEN = 20


class SeriesStore:
    def __init__(self, maxlen: int = DEFAULT_MAXLEN) -> None:
        self.maxlen = maxlen
        self._buffers: dict[tuple[str, str], deque[float]] = {}

    def append(self, asset_class: str, symbol: str, price: float) -> None:
        key = (asset_class, symbol)
        buf = self._buffers.get(key)
        if buf is None:
            buf = deque(maxlen=self.maxlen)
            self._buffers[key] = buf
        buf.append(price)

    def get(self, asset_class: str, symbol: str) -> list[float]:
        buf = self._buffers.get((asset_class, symbol))
        return list(buf) if buf is not None else []

    def extend_from_snapshot(
        self, asset_class: str, quotes: Iterable
    ) -> None:
        for q in quotes:
            if q.price > 0:
                self.append(asset_class, q.symbol, q.price)
