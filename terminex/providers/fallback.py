"""A provider that serves from the first healthy feed in an ordered chain.

Crypto uses CoinGecko → CoinLore (CoinCap first when a key is set);
commodities use Yahoo's query1 host → query2. A feed that fails rests
until its rate-limit window (Retry-After) or ``FEED_RETRY`` seconds pass,
so a dead or misconfigured feed isn't hit on every poll. The last feed
never rests: the app's own retry schedule decides when it is asked again.
``name`` and ``min_poll_interval`` follow whichever feed is serving, and
the snapshot's provider name lists the feeds that were skipped.
"""

from __future__ import annotations

import time
from dataclasses import replace

from ..quote import Snapshot
from .base import Provider, ProviderError, RateLimitError

FEED_RETRY = 300.0  # seconds a failed (non-final) feed rests before a retry


class FallbackProvider(Provider):
    def __init__(self, *providers: Provider) -> None:
        if len(providers) < 2:
            raise ValueError("a fallback chain needs at least two feeds")
        self.providers = list(providers)
        self.asset_class = providers[0].asset_class
        self._active = providers[0]
        self._rest_until = [0.0] * len(providers)  # monotonic, per feed

    @property  # type: ignore[override]
    def name(self) -> str:
        return self._active.name

    @property  # type: ignore[override]
    def min_poll_interval(self) -> float:
        return self._active.min_poll_interval

    def fetch(self) -> Snapshot:
        now = time.monotonic()
        last = len(self.providers) - 1
        errors: list[ProviderError] = []
        for i, provider in enumerate(self.providers):
            if i < last and now < self._rest_until[i]:
                continue
            try:
                snapshot = provider.fetch()
            except RateLimitError as exc:
                errors.append(exc)
                self._rest_until[i] = now + exc.retry_after
                continue
            except ProviderError as exc:
                errors.append(exc)
                self._rest_until[i] = now + FEED_RETRY
                continue
            self._active = provider
            if i == 0:
                return snapshot
            skipped = ", ".join(p.name for p in self.providers[:i])
            return replace(snapshot, provider_name=f"{provider.name} ({skipped} unavailable)")

        message = "; ".join(str(e) for e in errors)
        final = errors[-1]
        if isinstance(final, RateLimitError):
            raise RateLimitError(message, retry_after=final.retry_after) from final
        raise ProviderError(message) from final
