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

    def test_secondary_rate_limit_keeps_its_type(self):
        self.primary.error = ProviderError("down")
        self.secondary.error = RateLimitError("coingecko 429", retry_after=60)
        with self.assertRaises(RateLimitError) as ctx:
            self.feed.fetch()
        self.assertEqual(ctx.exception.retry_after, 60)


class TestDefaultCryptoChain(unittest.TestCase):
    def test_coincap_key_gets_coingecko_as_fallback(self):
        from terminex.app import default_providers
        from terminex.config import Config
        crypto = default_providers(Config(coincap_api_key="k"))["crypto"]
        self.assertIsInstance(crypto, FallbackProvider)
        self.assertEqual((crypto.primary.name, crypto.secondary.name), ("coincap.io", "coingecko.com"))


if __name__ == "__main__":
    unittest.main()
