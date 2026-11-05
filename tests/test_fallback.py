"""FallbackProvider: use the secondary feed while the primary is down."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

from terminex.providers.base import Provider, ProviderError, RateLimitError
from terminex.providers.fallback import FallbackProvider
from terminex.quote import Quote, Snapshot


class Feed(Provider):
    asset_class = "crypto"

    def __init__(self, name, floor=0.0):
        self.name = name
        self.min_poll_interval = floor
        self.error = None
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error:
            raise self.error
        return Snapshot("crypto", "USD", [Quote("BTC", "Bitcoin", 80000.0, "USD")],
                        datetime.now(tz=timezone.utc), provider_name=self.name)


class TestFallbackProvider(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        patcher = mock.patch("terminex.providers.fallback.time.monotonic", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.primary = Feed("coincap.io", floor=0.0)
        self.secondary = Feed("coingecko.com", floor=60.0)
        self.feed = FallbackProvider(self.primary, self.secondary)

    def test_healthy_primary_is_used(self):
        snap = self.feed.fetch()
        self.assertEqual(snap.provider_name, "coincap.io")
        self.assertEqual(self.feed.name, "coincap.io")
        self.assertEqual(self.secondary.calls, 0)

    def test_failed_primary_falls_back_and_says_so(self):
        self.primary.error = ProviderError("coincap.io returned HTTP 401")
        snap = self.feed.fetch()
        self.assertEqual(snap.provider_name, "coingecko.com (coincap.io unavailable)")
        self.assertEqual(self.feed.name, "coingecko.com")
        self.assertEqual(self.feed.min_poll_interval, 60.0)   # follows the active feed

    def test_primary_is_not_hammered_while_down(self):
        self.primary.error = ProviderError("down")
        self.feed.fetch()
        self.now += 60
        self.feed.fetch()
        self.assertEqual(self.primary.calls, 1)
        self.assertEqual(self.secondary.calls, 2)

    def test_switches_back_when_primary_recovers(self):
        self.primary.error = ProviderError("down")
        self.feed.fetch()
        self.primary.error = None
        self.now += 300
        self.assertEqual(self.feed.fetch().provider_name, "coincap.io")
        self.assertEqual(self.feed.min_poll_interval, 0.0)

    def test_primary_rate_limit_sets_the_retry_window(self):
        self.primary.error = RateLimitError("429", retry_after=120)
        self.feed.fetch()
        self.primary.error = None
        self.now += 119
        self.feed.fetch()
        self.assertEqual(self.primary.calls, 1)
        self.now += 1
        self.feed.fetch()
        self.assertEqual(self.primary.calls, 2)

    def test_both_down_reports_both(self):
        self.primary.error = ProviderError("coincap.io returned HTTP 401")
        self.secondary.error = ProviderError("can't reach coingecko.com")
        with self.assertRaises(ProviderError) as ctx:
            self.feed.fetch()
        self.assertIn("coincap.io returned HTTP 401", str(ctx.exception))
        self.assertIn("can't reach coingecko.com", str(ctx.exception))

    def test_a_rate_limit_proves_the_connection_so_the_down_feed_rests(self):
        self.primary.error = ProviderError("coincap.io returned HTTP 503")
        self.secondary.error = RateLimitError("coingecko 429", retry_after=1800)
        with self.assertRaises(RateLimitError) as ctx:
            self.feed.fetch()
        # The 429 was a real answer, so the 503 is the feed's own: it rests
        # 300 s, and the chain waits for that, not the 1800 s window.
        self.assertEqual(ctx.exception.retry_after, 300)
        self.now += 60
        with self.assertRaises(RateLimitError):
            self.feed.fetch()
        self.assertEqual((self.primary.calls, self.secondary.calls), (1, 1))  # nothing hammered

    def test_only_rate_limits_left_reports_a_rate_limit(self):
        self.primary.error = RateLimitError("coincap 429", retry_after=120)
        self.secondary.error = RateLimitError("coingecko 429", retry_after=60)
        with self.assertRaises(RateLimitError) as ctx:
            self.feed.fetch()
        self.assertEqual(ctx.exception.retry_after, 60)


class TestLongerChains(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        patcher = mock.patch("terminex.providers.fallback.time.monotonic", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.a, self.b, self.c = Feed("coincap.io"), Feed("coingecko.com", 60.0), Feed("coinlore.com", 60.0)
        self.feed = FallbackProvider(self.a, self.b, self.c)

    def test_caption_lists_every_skipped_feed(self):
        self.a.error = ProviderError("401")
        self.b.error = RateLimitError("429", retry_after=60)
        snap = self.feed.fetch()
        self.assertEqual(snap.provider_name, "coinlore.com (coincap.io, coingecko.com unavailable)")

    def test_after_a_total_failure_every_feed_is_retried(self):
        for feed in (self.a, self.b, self.c):
            feed.error = ProviderError("down")
        with self.assertRaises(ProviderError):
            self.feed.fetch()
        self.c.error = None
        self.now += 30                      # the app's 30 s error retry
        self.assertEqual(self.feed.fetch().provider_name,
                         "coinlore.com (coincap.io, coingecko.com unavailable)")
        self.assertEqual((self.a.calls, self.b.calls, self.c.calls), (2, 2, 2))

    def test_last_feed_never_rests_after_an_ordinary_error(self):
        self.a.error = ProviderError("down")
        self.b.error = None
        self.feed.fetch()                   # a rests (b answered)
        self.b.error = ProviderError("down")
        self.c.error = ProviderError("down")
        with self.assertRaises(ProviderError):
            self.feed.fetch()
        self.c.error = None
        self.now += 30
        self.assertEqual(self.feed.fetch().provider_name,
                         "coinlore.com (coincap.io, coingecko.com unavailable)")

    def test_network_blip_does_not_strand_the_chain_on_its_fallback(self):
        for feed in (self.a, self.b, self.c):
            feed.error = ProviderError("can't reach host — check your connection")
        with self.assertRaises(ProviderError):
            self.feed.fetch()                       # everything failed: likely us, not them
        for feed in (self.a, self.b, self.c):
            feed.error = None
        self.now += 30
        self.assertEqual(self.feed.fetch().provider_name, "coincap.io")

    def test_all_rate_limited_backs_off_until_the_earliest_window(self):
        self.a.error = RateLimitError("a 429", retry_after=100)
        self.b.error = RateLimitError("b 429", retry_after=50)
        self.c.error = RateLimitError("c 429", retry_after=1800)
        with self.assertRaises(RateLimitError) as ctx:
            self.feed.fetch()
        self.assertEqual(ctx.exception.retry_after, 50)

    def test_mixed_failures_wait_for_the_earliest_feed(self):
        self.a.error = ProviderError("401")
        self.b.error = ProviderError("503")
        self.c.error = RateLimitError("c 429", retry_after=1800)
        with self.assertRaises(RateLimitError) as ctx:
            self.feed.fetch()
        self.assertEqual(ctx.exception.retry_after, 300)      # not frozen for 1800 s

    def test_unexpected_exception_falls_back_and_rests_the_feed(self):
        self.a.error = KeyError("price")             # a provider bug, not a ProviderError
        snap = self.feed.fetch()
        self.assertEqual(snap.provider_name, "coingecko.com (coincap.io unavailable)")
        self.now += 60
        self.feed.fetch()
        self.assertEqual(self.a.calls, 1)            # rested like any failed feed

    def test_needs_two_feeds(self):
        with self.assertRaises(ValueError):
            FallbackProvider(self.a)


class TestDefaultChains(unittest.TestCase):
    def names(self, provider):
        return [p.name for p in provider.providers]

    def test_crypto_chains(self):
        from terminex.app import default_providers
        from terminex.config import Config
        self.assertEqual(self.names(default_providers(Config())["crypto"]),
                         ["coingecko.com", "coinlore.com"])
        self.assertEqual(self.names(default_providers(Config(coincap_api_key="k"))["crypto"]),
                         ["coincap.io", "coingecko.com", "coinlore.com"])

    def test_commodities_chain(self):
        from terminex.app import default_providers
        from terminex.config import Config
        self.assertEqual(self.names(default_providers(Config())["commodity"]),
                         ["query1.finance.yahoo.com", "query2.finance.yahoo.com"])


if __name__ == "__main__":
    unittest.main()
