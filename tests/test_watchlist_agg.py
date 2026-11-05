"""Watchlist rows must show USD per unit for every asset class."""

from __future__ import annotations

import unittest

from terminex.providers.watchlist_agg import WatchlistAggregator
from terminex.quote import Quote
from terminex.watchlist import Pin, Watchlist


class TestWatchlistPrices(unittest.TestCase):
    def setUp(self):
        self.quotes = {
            ("fx", "EUR"): Quote("EUR", "Euro", 0.889912, "USD"),
            ("crypto", "BTC"): Quote("BTC", "Bitcoin", 80000.0, "USD", 4.8),
        }
        self.usd = {"EUR": 1.0 / 0.889912}
        self.watchlist = Watchlist(pins=[Pin("fx", "EUR"), Pin("crypto", "BTC")])

    def _fetch(self):
        agg = WatchlistAggregator(
            self.watchlist,
            lambda ac, sym: self.quotes.get((ac, sym)),
            fx_usd_price=self.usd.get,
        )
        return {q.symbol: q for q in agg.fetch().quotes}

    def test_fx_pin_shows_usd_per_unit(self):
        self.assertAlmostEqual(self._fetch()["EUR"].price, 1.1237, places=4)

    def test_fx_pin_keeps_original_rate_in_meta(self):
        self.assertEqual(self._fetch()["EUR"].meta["fx_rate"], 0.889912)

    def test_crypto_pin_unchanged(self):
        btc = self._fetch()["BTC"]
        self.assertEqual((btc.price, btc.change_24h_pct), (80000.0, 4.8))

    def test_pin_from_a_failed_feed_says_unavailable(self):
        agg = WatchlistAggregator(
            self.watchlist, lambda ac, sym: None,
            source_failed=lambda ac: ac == "crypto",
        )
        rows = {q.symbol: q for q in agg.fetch().quotes}
        self.assertTrue(rows["BTC"].meta.get("unavailable"))
        self.assertEqual(rows["BTC"].name, "(Crypto unavailable)")
        self.assertTrue(rows["EUR"].meta.get("pending"))  # FX still loading

    def test_fx_pin_without_usd_price_is_pending(self):
        self.usd = {}
        self.assertTrue(self._fetch()["EUR"].meta.get("pending"))


if __name__ == "__main__":
    unittest.main()
