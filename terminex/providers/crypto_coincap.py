"""Crypto provider backed by CoinCap v3."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

from ..quote import Quote, Snapshot
from .base import (
    Provider,
    ProviderError,
    describe_request_error,
    RateLimitError,
    finite_number,
    parse_retry_after,
)

API_URL = "https://rest.coincap.io/v3/assets"
TIMEOUT = 10.0
ENV_KEY = "TERMINEX_COINCAP_KEY"


class CryptoCoinCap(Provider):
    name = "coincap.io"
    asset_class = "crypto"

    def __init__(self, limit: int = 25, api_key: str | None = None) -> None:
        self.limit = limit
        self.api_key = api_key or os.environ.get(ENV_KEY, "")

    def fetch(self) -> Snapshot:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.get(
                API_URL,
                params={"limit": self.limit},
                headers=headers,
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(describe_request_error(self.name, exc)) from exc

        if resp.status_code == 429:
            retry_after = parse_retry_after(resp.headers.get("Retry-After"), 60.0)
            raise RateLimitError(
                "CoinCap rate limited this connection.",
                retry_after=retry_after,
            )

        try:
            resp.raise_for_status()
            payload = resp.json()
        except requests.HTTPError as exc:
            raise ProviderError(describe_request_error(self.name, exc)) from exc
        except ValueError as exc:
            raise ProviderError(f"{self.name} sent a response terminex couldn't read") from exc

        assets = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(assets, list):
            raise ProviderError("missing 'data' in payload")

        provider_time: datetime | None = None
        ts = finite_number(payload.get("timestamp"))
        if ts is not None:
            try:
                provider_time = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                provider_time = None

        quotes: list[Quote] = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            price = _number(asset.get("priceUsd"))
            if price is None or price <= 0:
                continue
            change = _number(asset.get("changePercent24Hr"))
            rank_str = asset.get("rank")
            try:
                rank = int(rank_str) if rank_str is not None else None
            except (TypeError, ValueError):
                rank = None
            quotes.append(
                Quote(
                    symbol=str(asset.get("symbol", "?")),
                    name=str(asset.get("name", "?")),
                    price=price,
                    quote_ccy="USD",
                    change_24h_pct=change,
                    meta={"rank": rank} if rank is not None else {},
                )
            )

        if not quotes:
            # An empty table would look like a quiet market; say the feed
            # sent nothing usable (usually a format change upstream).
            raise ProviderError(f"{self.name} returned no usable prices")

        return Snapshot(
            asset_class="crypto",
            quote_ccy="USD",
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_time=provider_time,
            provider_name=self.name,
        )


def _number(value: object) -> float | None:
    """CoinCap sends numbers as strings; accept only finite values."""
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    return finite_number(value)
