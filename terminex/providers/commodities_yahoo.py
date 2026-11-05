"""Commodity futures provider backed by Yahoo Finance's v8 spark endpoint.

One request returns the latest price, the previous session's close and
about a week of intraday closes for every symbol, so it also feeds the
7-day trend column. The endpoint is public but undocumented: it rejects
the default ``python-requests`` User-Agent, so we send one that names
terminex. Grains and softs are quoted in US cents; they are converted to
dollars here so every commodity price is USD per unit.

Stooq's CSV endpoint, used up to 0.4.0, was removed in 2026.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

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

API_URL = "https://query1.finance.yahoo.com/v8/finance/spark"
TIMEOUT = 10.0
DEFAULT_RETRY_AFTER = 120.0

# (Yahoo symbol, display name, unit, quoted in US cents). Order is table order.
SYMBOLS: list[tuple[str, str, str, bool]] = [
    ("GC=F", "Gold", "oz", False),
    ("SI=F", "Silver", "oz", False),
    ("PL=F", "Platinum", "oz", False),
    ("PA=F", "Palladium", "oz", False),
    ("HG=F", "Copper", "lb", False),
    ("CL=F", "WTI Crude", "bbl", False),
    ("BZ=F", "Brent Crude", "bbl", False),
    ("NG=F", "Natural Gas", "MMBtu", False),
    ("ZW=F", "Wheat", "bu", True),
    ("ZC=F", "Corn", "bu", True),
    ("ZS=F", "Soybeans", "bu", True),
    ("KC=F", "Coffee", "lb", True),
    ("SB=F", "Sugar", "lb", True),
    ("CT=F", "Cotton", "lb", True),
]


def _user_agent() -> str:
    try:
        ver = version("terminex")
    except PackageNotFoundError:
        ver = "dev"
    return (
        f"Mozilla/5.0 (compatible; terminex/{ver}; "
        "+https://github.com/Bij4n/terminex)"
    )


def display_symbol(yahoo_symbol: str) -> str:
    """``GC=F`` → ``GC.F``, the name pins and alerts have always used."""
    return yahoo_symbol.replace("=", ".")


class CommoditiesYahoo(Provider):
    name = "finance.yahoo.com"
    asset_class = "commodity"
    # Futures quotes are delayed ~10 minutes; there is nothing to gain from
    # polling the unofficial endpoint more often than this.
    min_poll_interval: float = 120.0

    def __init__(
        self, symbols: list[tuple[str, str, str, bool]] | None = None
    ) -> None:
        self.symbols = symbols or SYMBOLS

    def fetch(self) -> Snapshot:
        try:
            resp = requests.get(
                API_URL,
                params={
                    "symbols": ",".join(sym for sym, *_ in self.symbols),
                    "range": "7d",
                    "interval": "1h",
                },
                headers={"User-Agent": _user_agent()},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(describe_request_error(self.name, exc)) from exc

        if resp.status_code == 429:
            raise RateLimitError(
                f"{self.name} rate limited this connection.",
                retry_after=parse_retry_after(
                    resp.headers.get("Retry-After"), DEFAULT_RETRY_AFTER
                ),
            )
        try:
            resp.raise_for_status()
            payload = resp.json()
        except requests.HTTPError as exc:
            raise ProviderError(describe_request_error(self.name, exc)) from exc
        except ValueError as exc:
            raise ProviderError(f"{self.name} sent a response terminex couldn't read") from exc

        if not isinstance(payload, dict):
            raise ProviderError(f"{self.name} sent an unexpected payload")

        quotes: list[Quote] = []
        latest: datetime | None = None
        for yahoo_sym, name, unit, in_cents in self.symbols:
            entry = payload.get(yahoo_sym)
            if not isinstance(entry, dict):
                continue
            closes = entry.get("close")
            if not isinstance(closes, list):
                continue
            scale = 0.01 if in_cents else 1.0
            history = [
                n * scale
                for n in (finite_number(c) for c in closes)
                if n is not None and n > 0
            ]
            if not history:
                continue
            price = history[-1]
            prev = _positive(entry.get("previousClose"), scale)
            week_ago = _positive(entry.get("chartPreviousClose"), scale)
            stamps = entry.get("timestamp")
            last = _timestamp(stamps[-1]) if isinstance(stamps, list) and stamps else None
            if last is not None and (latest is None or last > latest):
                latest = last
            meta: dict = {"unit": unit, "history": history}
            if week_ago:
                meta["change_7d_pct"] = (price - week_ago) / week_ago * 100.0
            quotes.append(
                Quote(
                    symbol=display_symbol(yahoo_sym),
                    name=name,
                    price=price,
                    quote_ccy="USD",
                    change_24h_pct=(
                        (price - prev) / prev * 100.0 if prev else None
                    ),
                    meta=meta,
                )
            )

        if not quotes:
            raise ProviderError(f"{self.name} returned no usable prices")

        return Snapshot(
            asset_class="commodity",
            quote_ccy="USD",
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_time=latest,
            provider_name=self.name,
        )


def _positive(value: object, scale: float) -> float | None:
    number = finite_number(value)
    return number * scale if number is not None and number > 0 else None


def _timestamp(value: object) -> datetime | None:
    seconds = finite_number(value)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
