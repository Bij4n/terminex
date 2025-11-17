"""Commodity futures provider backed by stooq.com CSV.

Yahoo Finance's v7 quote endpoint now rate-limits unauthenticated requests
aggressively. Stooq's CSV batch endpoint covers the same 14 commodities
with no API key, using ``+`` (URL-encoded space) as the batch separator.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import requests

from ..quote import Quote, Snapshot
from .base import Provider, ProviderError

API_URL_TEMPLATE = "https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcv&h&e=csv"
TIMEOUT = 10.0

# (stooq symbol, display name). Order determines table ordering.
SYMBOLS: list[tuple[str, str]] = [
    ("gc.f", "Gold"),
    ("si.f", "Silver"),
    ("pl.f", "Platinum"),
    ("pa.f", "Palladium"),
    ("hg.f", "Copper"),
    ("cl.f", "WTI Crude Oil"),
    ("ng.f", "Natural Gas"),
    ("zw.f", "Wheat"),
    ("zc.f", "Corn"),
    ("zs.f", "Soybeans"),
    ("kc.f", "Coffee"),
    ("sb.f", "Sugar"),
    ("ct.f", "Cotton"),
]


class CommoditiesStooq(Provider):
    name = "stooq.com"
    asset_class = "commodity"

    def __init__(self, symbols: list[tuple[str, str]] | None = None) -> None:
        self.symbols = symbols or SYMBOLS

    def fetch(self) -> Snapshot:
        names = {sym.upper(): name for sym, name in self.symbols}
        # stooq's batch separator is `+` (space in form-encoding). Requests
        # URL-encodes `+` to `%2B`, which stooq rejects, so we build the
        # URL manually.
        query = "+".join(sym for sym, _ in self.symbols)
        url = API_URL_TEMPLATE.format(symbols=query)
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"request failed: {exc}") from exc

        reader = csv.DictReader(io.StringIO(resp.text))
        quotes: list[Quote] = []
        latest_ts: datetime | None = None
        for row in reader:
            sym = (row.get("Symbol") or "").upper()
            close = row.get("Close")
            if not sym or close in (None, "", "N/D"):
                continue
            try:
                price = float(close)
            except ValueError:
                continue
            open_ = _maybe_float(row.get("Open"))
            change_pct = None
            if open_ is not None and open_ != 0:
                change_pct = (price - open_) / open_ * 100.0
            ts = _parse_stooq_ts(row.get("Date"), row.get("Time"))
            if ts is not None and (latest_ts is None or ts > latest_ts):
                latest_ts = ts
            quotes.append(
                Quote(
                    symbol=sym,
                    name=names.get(sym, sym),
                    price=price,
                    quote_ccy="USD",
                    change_24h_pct=change_pct,
                )
            )

        if not quotes:
            raise ProviderError("stooq returned no usable rows")

        order = {sym.upper(): i for i, (sym, _) in enumerate(self.symbols)}
        quotes.sort(key=lambda q: order.get(q.symbol, 999))

        return Snapshot(
            asset_class="commodity",
            quote_ccy="USD",
            quotes=quotes,
            fetched_at=datetime.now(tz=timezone.utc),
            provider_time=latest_ts,
            provider_name=self.name,
        )


def _maybe_float(value: str | None) -> float | None:
    if value in (None, "", "N/D"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_stooq_ts(date_str: str | None, time_str: str | None) -> datetime | None:
    if not date_str or not time_str or date_str == "N/D":
        return None
    try:
        return datetime.strptime(
            f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
