"""Crypto provider backed by CoinCap v3."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

from ..quote import Quote, Snapshot
from .base import Provider, ProviderError

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
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise ProviderError(f"request failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"invalid json: {exc}") from exc

        assets = payload.get("data")
        if not isinstance(assets, list):
            raise ProviderError("missing 'data' in payload")

        provider_time: datetime | None = None
        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)):
            provider_time = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)

        quotes: list[Quote] = []
        for asset in assets:
            price_str = asset.get("priceUsd")
            if price_str is None:
                continue
            try:
                price = float(price_str)
            except (TypeError, ValueError):
                continue
            change_str = asset.get("changePercent24Hr")
            try:
                change = float(change_str) if change_str is not None else None
            except (TypeError, ValueError):
                change = None
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

        return Snapshot(
            asset_class="crypto",
            quote_ccy="USD",
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_time=provider_time,
            provider_name=self.name,
        )
