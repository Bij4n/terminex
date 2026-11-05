"""A provider that serves from the first healthy feed in an ordered chain.

Crypto uses CoinGecko → CoinLore (CoinCap first when a key is set);
commodities use Yahoo's query1 host → query2. Any rate-limited feed,
the last included, rests for its Retry-After. A feed that fails otherwise
rests ``FEED_RETRY`` seconds, but only when some other feed gave a real
answer in the same pass (data, or a 429): if no feed answers at all the
problem is most likely our own connection, so nothing rests and the first
feed is tried again on the app's next retry. When every feed fails, the
chain reports a rate limit lasting until the first feed is free again.
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
        errors: list[ProviderError] = []
        plain_failures: list[int] = []
        connected = False  # did any feed give a real answer (data or a 429)?
        for i, provider in enumerate(self.providers):
            if now < self._rest_until[i]:
                continue
            try:
                snapshot = provider.fetch()
            except RateLimitError as exc:
                errors.append(exc)
                self._rest_until[i] = now + exc.retry_after
                connected = True
                continue
            except ProviderError as exc:
                errors.append(exc)
                plain_failures.append(i)
                continue
            except Exception as exc:  # a provider bug: treat like any failure
                errors.append(ProviderError(
                    f"{provider.name} sent something terminex couldn't read "
                    f"({type(exc).__name__}: {exc})"
                ))
                plain_failures.append(i)
                continue
            self._rest(plain_failures, now)
            self._active = provider
            if i == 0:
                return snapshot
            skipped = ", ".join(p.name for p in self.providers[:i])
            return replace(snapshot, provider_name=f"{provider.name} ({skipped} unavailable)")

        message = "; ".join(str(e) for e in errors) or (
            "every feed is rate limited — waiting for the first to free up"
        )
        if plain_failures and not connected:
            # No feed answered at all: most likely our own connection.
            # Rest nothing, so the first feed is tried on the app's next retry.
            raise ProviderError(message) from errors[-1]
        # Some feed answered (a 429 is an answer), so the ordinary failures
        # are the feeds' own: rest them, and wait for the first feed to free
        # up rather than for the longest rate-limit window.
        self._rest(plain_failures, now)
        retry_after = max(1.0, min(t - now for t in self._rest_until if t > now))
        raise RateLimitError(message, retry_after=retry_after)

    def _rest(self, indices: list[int], now: float) -> None:
        for i in indices:
            self._rest_until[i] = now + FEED_RETRY
