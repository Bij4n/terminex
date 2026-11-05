"""A provider that serves from the first healthy feed in an ordered chain.

Crypto uses CoinGecko → CoinLore (CoinCap first when a key is set);
commodities use Yahoo's query1 host → query2. Any rate-limited feed,
the last included, rests for its Retry-After. A feed that fails otherwise
rests ``FEED_RETRY`` seconds, but only when a later feed answered in the
same pass, so the last feed never rests for that: and if every feed fails
at once the problem is most likely our own connection, so nothing rests
and the first feed is tried again on the app's next retry.
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
        for i, provider in enumerate(self.providers):
            if now < self._rest_until[i]:
                continue
            try:
                snapshot = provider.fetch()
            except RateLimitError as exc:
                errors.append(exc)
                self._rest_until[i] = now + exc.retry_after
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
            # A later feed answered, so the network is fine and the earlier
            # failures are the feeds' own: rest them.
            for j in plain_failures:
                self._rest_until[j] = now + FEED_RETRY
            self._active = provider
            if i == 0:
                return snapshot
            skipped = ", ".join(p.name for p in self.providers[:i])
            return replace(snapshot, provider_name=f"{provider.name} ({skipped} unavailable)")

        if not errors:
            # Every feed is resting (rate limits): wait for the first.
            retry_after = max(1.0, min(self._rest_until) - now)
            raise RateLimitError(
                "every feed is rate limited — waiting for the first to free up",
                retry_after=retry_after,
            )
        message = "; ".join(str(e) for e in errors)
        if plain_failures:
            # Every feed failed in the same pass: most likely our own
            # connection. Rest nothing, so the first feed is tried again
            # as soon as the app retries.
            raise ProviderError(message) from errors[-1]
        # Every feed is rate limited or resting: wait for the first one to
        # become available again, not for the last one's window.
        retry_after = max(1.0, min(t - now for t in self._rest_until if t > now))
        raise RateLimitError(message, retry_after=retry_after) from errors[-1]
