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

    def test_series_keys_point_trends_at_usd_prices(self):
        from terminex.series import FX_USD
        rows = self._fetch()
        self.assertEqual(rows["EUR"].meta["series_key"], (FX_USD, "EUR"))
        self.assertEqual(rows["BTC"].meta["series_key"], ("crypto", "BTC"))

    def test_placeholder_rows_keep_their_series_key(self):
        from terminex.series import FX_USD
        self.usd = {}  # FX loaded but no USD price yet -> placeholder row
        self.assertEqual(self._fetch()["EUR"].meta["series_key"], (FX_USD, "EUR"))
        agg = WatchlistAggregator(self.watchlist, lambda ac, sym: None,
                                  source_failed=lambda ac: True)
        rows = {q.symbol: q for q in agg.fetch().quotes}
        self.assertEqual(rows["EUR"].meta["series_key"], (FX_USD, "EUR"))

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

    def test_pin_missing_from_a_loaded_feed_is_unavailable_not_loading(self):
        agg = WatchlistAggregator(
            self.watchlist,
            lambda ac, sym: None if sym == "BTC" else self.quotes.get((ac, sym)),
            fx_usd_price=self.usd.get,
            source_loaded=lambda ac: True,
        )
        btc = {q.symbol: q for q in agg.fetch().quotes}["BTC"]
        self.assertTrue(btc.meta.get("unavailable"))
        self.assertEqual(btc.name, "(not in current Crypto feed)")

    def test_fx_pin_without_usd_price_is_pending(self):
        self.usd = {}
        self.assertTrue(self._fetch()["EUR"].meta.get("pending"))


if __name__ == "__main__":
    unittest.main()
