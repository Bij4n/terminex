"""Crypto provider backed by CoinLore's public tickers API.

No key or registration. CoinLore asks for about one request per second at
most; terminex polls far less often. Used as the keyless fallback when
CoinGecko is unavailable. It has no price history, so while it is serving
the Trend column draws the live series collected this session.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..quote import Quote, Snapshot
from .base import (
    Provider,
    ProviderError,
    RateLimitError,
    describe_request_error,
    finite_number,
    parse_retry_after,
    user_agent,
)

API_URL = "https://api.coinlore.net/api/tickers/"
TIMEOUT = 10.0


class CryptoCoinLore(Provider):
    name = "coinlore.com"
    asset_class = "crypto"
    min_poll_interval: float = 60.0

    def __init__(self, limit: int = 25) -> None:
        self.limit = limit

    def fetch(self) -> Snapshot:
        try:
            resp = requests.get(
                API_URL,
                params={"start": 0, "limit": self.limit},
                headers={"User-Agent": user_agent()},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(describe_request_error(self.name, exc)) from exc

        if resp.status_code == 429:
            raise RateLimitError(
                f"{self.name} rate limited this connection.",
                retry_after=parse_retry_after(resp.headers.get("Retry-After"), 60.0),
            )
        try:
            resp.raise_for_status()
            payload = resp.json()
        except requests.HTTPError as exc:
            raise ProviderError(describe_request_error(self.name, exc)) from exc
        except ValueError as exc:
            raise ProviderError(f"{self.name} sent a response terminex couldn't read") from exc

        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise ProviderError(f"{self.name} sent an unexpected payload")

        quotes: list[Quote] = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("symbol"):
                continue
            price = _number(entry.get("price_usd"))
            if price is None or price <= 0:
                continue
            meta: dict = {}
            rank = entry.get("rank")
            if isinstance(rank, int) and not isinstance(rank, bool):
                meta["rank"] = rank
            change_7d = _number(entry.get("percent_change_7d"))
            if change_7d is not None:
                meta["change_7d_pct"] = change_7d
            quotes.append(
                Quote(
                    symbol=str(entry["symbol"]).upper(),
                    name=str(entry.get("name") or entry["symbol"]),
                    price=price,
                    quote_ccy="USD",
                    change_24h_pct=_number(entry.get("percent_change_24h")),
                    meta=meta,
                )
            )

        if not quotes:
            raise ProviderError(f"{self.name} returned no usable prices")

        return Snapshot(
            asset_class="crypto",
            quote_ccy="USD",
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_name=self.name,
        )


def _number(value: object) -> float | None:
    """CoinLore sends numbers as strings; accept only finite values."""
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    return finite_number(value)
