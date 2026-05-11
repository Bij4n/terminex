"""FX provider backed by open.er-api.com."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..currencies import NAMES, TOP_25
from ..quote import Quote, Snapshot
from .base import Provider, ProviderError

API_URL = "https://open.er-api.com/v6/latest/{base}"
TIMEOUT = 10.0


class FxERApi(Provider):
    name = "open.er-api.com"
    asset_class = "fx"
    # open.er-api.com free tier updates rates hourly; polling faster wastes quota.
    min_poll_interval: float = 300.0

    def __init__(self, base: str = "USD") -> None:
        self.base = base.upper()

    def fetch(self) -> Snapshot:
        url = API_URL.format(base=self.base)
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise ProviderError(f"request failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"invalid json: {exc}") from exc

        if payload.get("result") != "success":
            raise ProviderError(f"api returned: {payload.get('result')!r}")

        rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise ProviderError("missing 'rates' in payload")

        provider_time: datetime | None = None
        ts = payload.get("time_last_update_unix")
        if isinstance(ts, (int, float)):
            provider_time = datetime.fromtimestamp(ts, tz=timezone.utc)

        quotes: list[Quote] = []
        for code, _ in TOP_25:
            if code == self.base:
                price = 1.0
            else:
                val = rates.get(code)
                if val is None:
                    continue
                price = float(val)
            quotes.append(
                Quote(
                    symbol=code,
                    name=NAMES[code],
                    price=price,
                    quote_ccy=self.base,
                )
            )

        return Snapshot(
            asset_class="fx",
            quote_ccy=self.base,
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_time=provider_time,
            provider_name=self.name,
        )
