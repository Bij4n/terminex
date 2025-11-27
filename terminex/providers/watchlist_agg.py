"""Synthetic provider that composes pinned quotes from other providers.

This provider does no network I/O; it reads from already-fetched
snapshots of the fx/crypto/commodity tabs and builds a unified snapshot
from the user's watchlist pins.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from ..quote import AssetClass, Quote, Snapshot
from ..watchlist import Watchlist
from .base import Provider

QuoteLookup = Callable[[AssetClass, str], Quote | None]

_TAB_LABELS: dict[AssetClass, str] = {
    "fx": "FX",
    "crypto": "Crypto",
    "commodity": "Cmdty",
}


class WatchlistAggregator(Provider):
    name = "watchlist"
    asset_class = "fx"  # placeholder; renderer keys off provider_name

    def __init__(
        self,
        watchlist: Watchlist,
        lookup: QuoteLookup,
    ) -> None:
        self.watchlist = watchlist
        self.lookup = lookup

    def fetch(self) -> Snapshot:
        quotes: list[Quote] = []
        for pin in self.watchlist.pins:
            q = self.lookup(pin.asset_class, pin.symbol)
            if q is None:
                # source snapshot not loaded yet — render as placeholder
                quotes.append(
                    Quote(
                        symbol=pin.symbol,
                        name=f"(loading {_TAB_LABELS[pin.asset_class]}…)",
                        price=0.0,
                        quote_ccy="USD",
                        change_24h_pct=None,
                        meta={
                            "source_tab": pin.asset_class,
                            "source_label": _TAB_LABELS[pin.asset_class],
                            "pending": True,
                        },
                    )
                )
                continue
            quotes.append(
                Quote(
                    symbol=q.symbol,
                    name=q.name,
                    price=q.price,
                    quote_ccy=q.quote_ccy,
                    change_24h_pct=q.change_24h_pct,
                    meta={
                        **q.meta,
                        "source_tab": pin.asset_class,
                        "source_label": _TAB_LABELS[pin.asset_class],
                    },
                )
            )

        return Snapshot(
            asset_class="fx",
            quote_ccy="USD",
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_time=None,
            provider_name=self.name,
        )
