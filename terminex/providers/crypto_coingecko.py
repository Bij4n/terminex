"""Crypto provider backed by CoinGecko's public demo API.

No API key required. The public tier serves prices from a cache that
refreshes about once a minute and rate-limits at a few requests per
minute per IP (less on shared VPN exits), so polling faster than the
cache only fetches the same prices again and invites 429s.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..quote import Quote, Snapshot
from .base import Provider, ProviderError, RateLimitError, parse_retry_after

API_URL = "https://api.coingecko.com/api/v3/coins/markets"
TIMEOUT = 10.0


class CryptoCoinGecko(Provider):
    name = "coingecko.com"
    asset_class = "crypto"
    min_poll_interval: float = 60.0

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
                    "price_change_percentage": "24h,7d",
                    # A week of hourly prices for the trend column, in the
                    # same request.
                    "sparkline": "true",
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"request failed: {exc}") from exc

        if resp.status_code == 429:
            retry_after = parse_retry_after(resp.headers.get("Retry-After"), 60.0)
            raise RateLimitError(
                "CoinGecko rate limited — retrying automatically. "
                "Set TERMINEX_COINCAP_KEY for a more reliable crypto feed.",
                retry_after=retry_after,
            )

        try:
            resp.raise_for_status()
            payload = resp.json()
        except requests.HTTPError as exc:
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
            meta: dict = {}
            if rank_i is not None:
                meta["rank"] = rank_i
            history = _history(entry.get("sparkline_in_7d"))
            if history:
                meta["history"] = history
            change_7d = entry.get("price_change_percentage_7d_in_currency")
            if isinstance(change_7d, (int, float)):
                meta["change_7d_pct"] = float(change_7d)
            quotes.append(
                Quote(
                    symbol=str(symbol).upper(),
                    name=str(name or symbol),
                    price=price_f,
                    quote_ccy="USD",
                    change_24h_pct=change_f,
                    meta=meta,
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


def _history(sparkline: object) -> list[float]:
    """Hourly prices from ``sparkline_in_7d``, skipping gaps."""
    if not isinstance(sparkline, dict):
        return []
    prices = sparkline.get("price")
    if not isinstance(prices, list):
        return []
    return [float(p) for p in prices if isinstance(p, (int, float)) and p > 0]
