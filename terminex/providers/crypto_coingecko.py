"""Crypto provider backed by CoinGecko's public demo API.

No API key required. Rate-limited to roughly 5-15 req/min on the free
public tier, which is well within a 10-second polling cadence.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..quote import Quote, Snapshot
from .base import Provider, ProviderError

API_URL = "https://api.coingecko.com/api/v3/coins/markets"
TIMEOUT = 10.0


class CryptoCoinGecko(Provider):
    name = "coingecko.com"
    asset_class = "crypto"

    def __init__(self, limit: int = 25) -> None:
        self.limit = limit

    def fetch(self) -> Snapshot:
        try:
            resp = requests.get(
                API_URL,
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": self.limit,
                    "page": 1,
                    "price_change_percentage": "24h",
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise ProviderError(f"request failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"invalid json: {exc}") from exc

        if not isinstance(payload, list):
            raise ProviderError("unexpected payload shape (not a list)")

        quotes: list[Quote] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            price = entry.get("current_price")
            symbol = entry.get("symbol")
            name = entry.get("name")
            if price is None or symbol is None:
                continue
            try:
                price_f = float(price)
            except (TypeError, ValueError):
                continue
            change = entry.get("price_change_percentage_24h")
            try:
                change_f = float(change) if change is not None else None
            except (TypeError, ValueError):
                change_f = None
            rank = entry.get("market_cap_rank")
            try:
                rank_i = int(rank) if rank is not None else None
            except (TypeError, ValueError):
                rank_i = None
            quotes.append(
                Quote(
                    symbol=str(symbol).upper(),
                    name=str(name or symbol),
                    price=price_f,
                    quote_ccy="USD",
                    change_24h_pct=change_f,
                    meta={"rank": rank_i} if rank_i is not None else {},
                )
            )

        return Snapshot(
            asset_class="crypto",
            quote_ccy="USD",
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_time=None,
            provider_name=self.name,
        )
