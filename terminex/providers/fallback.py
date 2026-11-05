"""A provider that falls back to a second feed while the first is down.

Used for crypto when a CoinCap key is set: CoinCap first, CoinGecko when
CoinCap fails. While the primary is down it is only retried after its
rate-limit window (Retry-After) or ``PRIMARY_RETRY`` seconds, so a dead
or misconfigured feed isn't hit on every poll. ``name`` and
``min_poll_interval`` follow whichever feed is serving, and the snapshot's
provider name says when the fallback is in use.
"""

from __future__ import annotations

import time
from dataclasses import replace

from ..quote import Snapshot
from .base import Provider, ProviderError, RateLimitError

PRIMARY_RETRY = 300.0  # seconds before retrying a primary that failed


class FallbackProvider(Provider):
    def __init__(self, primary: Provider, secondary: Provider) -> None:
        self.primary = primary
        self.secondary = secondary
        self.asset_class = primary.asset_class
        self._active = primary
        self._primary_retry_at = 0.0  # monotonic

    @property  # type: ignore[override]
    def name(self) -> str:
        return self._active.name

    @property  # type: ignore[override]
    def min_poll_interval(self) -> float:
        return self._active.min_poll_interval

    def fetch(self) -> Snapshot:
        primary_error: ProviderError | None = None
        now = time.monotonic()
        if now >= self._primary_retry_at:
            try:
                snapshot = self.primary.fetch()
            except RateLimitError as exc:
                primary_error = exc
                self._primary_retry_at = now + exc.retry_after
            except ProviderError as exc:
                primary_error = exc
                self._primary_retry_at = now + PRIMARY_RETRY
            else:
                self._active = self.primary
                return snapshot

        try:
            snapshot = self.secondary.fetch()
        except ProviderError as exc:
            if primary_error is None:
                raise
            message = f"{primary_error}; fallback: {exc}"
            if isinstance(exc, RateLimitError):
                raise RateLimitError(message, retry_after=exc.retry_after) from exc
            raise ProviderError(message) from exc
        self._active = self.secondary
        return replace(
            snapshot,
            provider_name=f"{self.secondary.name} ({self.primary.name} unavailable)",
        )
