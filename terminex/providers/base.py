"""Provider ABC — all data sources implement this interface."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from ..quote import AssetClass, Snapshot


class ProviderError(RuntimeError):
    """Raised when a provider can't produce a snapshot."""


class RateLimitError(ProviderError):
    """Raised when a provider is rate-limited.

    ``retry_after`` is the number of seconds the caller should wait
    before retrying.
    """

    def __init__(self, message: str, retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


MAX_RETRY_AFTER = 3600.0


def finite_number(value: object) -> float | None:
    """``value`` as a float if it is a real, finite number, else None.

    API payloads are untrusted: booleans, strings, NaN and infinity must
    not reach prices, percentages or sparkline arithmetic.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def parse_retry_after(value: str | None, default: float) -> float:
    """Seconds to wait from a ``Retry-After`` header.

    Accepts delay-seconds or an HTTP date. Anything missing, malformed or
    non-finite falls back to ``default``; the result is kept between 1 s
    and an hour so a bad header can neither hammer nor stall a feed.
    """
    seconds: float | None = None
    if value:
        try:
            seconds = float(value)
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
            except (TypeError, ValueError, IndexError):
                when = None
            if when is not None:
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                seconds = (when - datetime.now(timezone.utc)).total_seconds()
    if seconds is None or not math.isfinite(seconds):
        seconds = default
    return max(1.0, min(MAX_RETRY_AFTER, seconds))


def describe_request_error(name: str, exc: Exception) -> str:
    """One plain sentence for a failed HTTP request to ``name``.

    The raw requests exception (pools, proxies, retries) is noise to a
    user; what matters is whether the host was unreachable, slow, or said no.
    """
    import requests

    if isinstance(exc, requests.Timeout):
        return f"{name} didn't answer in time"
    if isinstance(exc, requests.HTTPError):
        code = getattr(getattr(exc, "response", None), "status_code", None)
        return f"{name} returned HTTP {code}" if code else f"{name} returned an error"
    if isinstance(exc, requests.ConnectionError):
        return f"can't reach {name} — check your connection"
    return f"request to {name} failed ({type(exc).__name__})"


class Provider(ABC):
    name: str
    asset_class: AssetClass
    # Minimum seconds between fetches regardless of the user's interval.
    # 0 means no floor (follow the user's interval exactly).
    min_poll_interval: float = 0.0

    @abstractmethod
    def fetch(self) -> Snapshot:
        """Fetch a fresh snapshot. Raise ProviderError on failure."""
