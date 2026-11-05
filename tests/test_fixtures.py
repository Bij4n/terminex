"""Providers against recorded real responses (tests/fixtures/*.json).

The fixtures are real API responses, trimmed, captured by
scripts/record_fixtures.py. If a provider changes its format, re-record
and these tests show what moved.
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from terminex.providers.base import ProviderError
from terminex.providers.commodities_yahoo import CommoditiesYahoo
from terminex.providers.crypto_coingecko import CryptoCoinGecko
from terminex.providers.crypto_coinlore import CryptoCoinLore
from terminex.providers.fx_erapi import FxERApi

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def fetch_with(module: str, provider, payload):
    resp = mock.Mock(status_code=200, headers={})
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    with mock.patch(f"terminex.providers.{module}.requests.get", return_value=resp):
        return provider.fetch()


def assert_sane_prices(case: unittest.TestCase, snap) -> None:
    for q in snap.quotes:
        case.assertTrue(math.isfinite(q.price) and q.price > 0, q)


class TestErApiFixture(unittest.TestCase):
    def setUp(self):
        self.fixture = load("erapi")

    def test_parses_all_top_25(self):
        snap = fetch_with("fx_erapi", FxERApi(), self.fixture["payload"])
        self.assertEqual(len(snap.quotes), 25)
        self.assertEqual({q.symbol for q in snap.quotes} >= {"USD", "EUR", "JPY", "GBP"}, True)
        assert_sane_prices(self, snap)
        self.assertIsNotNone(snap.provider_time)

    def test_missing_rates_is_an_error_not_an_empty_table(self):
        payload = copy.deepcopy(self.fixture["payload"])
        payload["conversion_rates"] = payload.pop("rates")   # a renamed field
        with self.assertRaises(ProviderError):
            fetch_with("fx_erapi", FxERApi(), payload)


class TestCoinGeckoFixture(unittest.TestCase):
    def setUp(self):
        self.fixture = load("coingecko")

    def test_parses_prices_history_and_changes(self):
        snap = fetch_with("crypto_coingecko", CryptoCoinGecko(), self.fixture["payload"])
        self.assertEqual(len(snap.quotes), 5)
        self.assertEqual(snap.quotes[0].symbol, "BTC")
        assert_sane_prices(self, snap)
        for q in snap.quotes:
            self.assertIsNotNone(q.change_24h_pct)
            self.assertGreater(len(q.meta["history"]), 100)   # ~168 hourly points
            self.assertIn("change_7d_pct", q.meta)
            self.assertIn("rank", q.meta)

    def test_renamed_price_field_is_an_error_not_an_empty_table(self):
        payload = copy.deepcopy(self.fixture["payload"])
        for coin in payload:
            coin["price"] = coin.pop("current_price")
        with self.assertRaises(ProviderError):
            fetch_with("crypto_coingecko", CryptoCoinGecko(), payload)


class TestCoinLoreFixture(unittest.TestCase):
    def test_parses_prices_rank_and_changes(self):
        snap = fetch_with("crypto_coinlore", CryptoCoinLore(), load("coinlore")["payload"])
        self.assertEqual(len(snap.quotes), 5)
        self.assertEqual(snap.quotes[0].symbol, "BTC")
        assert_sane_prices(self, snap)
        for q in snap.quotes:
            self.assertIsNotNone(q.change_24h_pct)
            self.assertIn("rank", q.meta)
            self.assertIn("change_7d_pct", q.meta)


class TestYahooFixture(unittest.TestCase):
    def setUp(self):
        self.fixture = load("yahoo_spark")

    def test_parses_futures_in_usd_with_history(self):
        snap = fetch_with("commodities_yahoo", CommoditiesYahoo(), self.fixture["payload"])
        by_symbol = {q.symbol: q for q in snap.quotes}
        self.assertEqual(set(by_symbol), {"GC.F", "SI.F", "ZW.F"})
        assert_sane_prices(self, snap)
        self.assertGreater(by_symbol["GC.F"].price, 500)       # gold, $/oz
        self.assertLess(by_symbol["ZW.F"].price, 50)            # wheat converted from cents
        for q in snap.quotes:
            self.assertIsNotNone(q.change_24h_pct)
            self.assertGreater(len(q.meta["history"]), 10)
        recorded = datetime.fromisoformat(self.fixture["recorded_at"])
        self.assertLess(abs(recorded - snap.provider_time), timedelta(days=4))  # latest point, not range start


if __name__ == "__main__":
    unittest.main()
