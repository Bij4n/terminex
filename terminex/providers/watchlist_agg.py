"""Synthetic provider that composes pinned quotes from other providers.

This provider does no network I/O; it reads from already-fetched
snapshots of the fx/crypto/commodity tabs and builds a unified snapshot
from the user's watchlist pins.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from ..quote import AssetClass, Quote, Snapshot
from ..series import FX_USD
from ..watchlist import Watchlist
from .base import Provider

QuoteLookup = Callable[[AssetClass, str], Quote | None]
FxUsdPrice = Callable[[str], float | None]
SourceFailed = Callable[[AssetClass], bool]

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
        fx_usd_price: FxUsdPrice | None = None,
        source_failed: SourceFailed | None = None,
    ) -> None:
        self.watchlist = watchlist
        self.lookup = lookup
        # FX tab rates are "units per 1 base"; the watchlist column is
        # USD per unit, so FX pins are converted through this callable.
        self.fx_usd_price = fx_usd_price
        # True when a source tab has failed and has nothing to show, so its
        # pins read "unavailable" instead of "loading…" forever.
        self.source_failed = source_failed

    def fetch(self) -> Snapshot:
        quotes: list[Quote] = []
        for pin in self.watchlist.pins:
            q = self.lookup(pin.asset_class, pin.symbol)
            price = q.price if q is not None else None
            # Trend series to draw, in the same units as the price column.
            # Placeholder rows need it too: stored history still draws.
            series_key = (
                (FX_USD, pin.symbol)
                if pin.asset_class == "fx"
                else (pin.asset_class, pin.symbol)
            )
            extra: dict = {"series_key": series_key}
            if q is not None and pin.asset_class == "fx":
                price = self.fx_usd_price(q.symbol) if self.fx_usd_price else None
                extra["fx_rate"] = q.price
            if q is None or price is None:
                label = _TAB_LABELS[pin.asset_class]
                failed = bool(self.source_failed and self.source_failed(pin.asset_class))
                quotes.append(
                    Quote(
                        symbol=pin.symbol,
                        name=f"({label} unavailable)" if failed else f"(loading {label}…)",
                        price=0.0,
                        quote_ccy="USD",
                        change_24h_pct=None,
                        meta={
                            "source_tab": pin.asset_class,
                            "source_label": label,
                            "series_key": series_key,
                            "unavailable" if failed else "pending": True,
                        },
                    )
                )
                continue
            quotes.append(
                Quote(
                    symbol=q.symbol,
                    name=q.name,
                    price=price,
                    quote_ccy="USD",
                    change_24h_pct=q.change_24h_pct,
                    meta={
                        **q.meta,
                        **extra,
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
