"""HTTP client for fetching FX rates from open.er-api.com."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests

API_URL = "https://open.er-api.com/v6/latest/{base}"
TIMEOUT = 10.0


class FetchError(RuntimeError):
    """Raised when rates can't be fetched or parsed."""


@dataclass(frozen=True)
class RateSnapshot:
    base: str
    rates: dict[str, float]
    fetched_at: datetime
    provider_time: datetime | None


def fetch_rates(base: str = "USD") -> RateSnapshot:
    """Fetch the latest rate table for ``base`` against all currencies."""
    url = API_URL.format(base=base.upper())
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"request failed: {exc}") from exc

    try:
        payload = resp.json()
    except ValueError as exc:
        raise FetchError(f"invalid json: {exc}") from exc

    if payload.get("result") != "success":
        raise FetchError(f"api returned: {payload.get('result')!r}")

    rates = payload.get("rates")
    if not isinstance(rates, dict):
        raise FetchError("missing 'rates' in payload")

    provider_time: datetime | None = None
    ts = payload.get("time_last_update_unix")
    if isinstance(ts, (int, float)):
        provider_time = datetime.fromtimestamp(ts, tz=timezone.utc)

    return RateSnapshot(
        base=base.upper(),
        rates={code: float(val) for code, val in rates.items()},
        fetched_at=datetime.now(tz=timezone.utc),
        provider_time=provider_time,
    )
