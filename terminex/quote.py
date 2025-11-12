"""Asset-agnostic Quote and Snapshot types shared by all providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

AssetClass = Literal["fx", "crypto", "commodity"]


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    price: float
    quote_ccy: str
    change_24h_pct: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Snapshot:
    asset_class: AssetClass
    quote_ccy: str
    quotes: list[Quote]
    fetched_at: datetime
    provider_time: datetime | None = None
    provider_name: str = ""

    def as_rate_map(self) -> dict[str, float]:
        """Return {symbol: price} — useful for delta comparisons."""
        return {q.symbol: q.price for q in self.quotes}
