"""Provider behaviour tests (no network: requests.get is mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from terminex.providers.base import ProviderError, RateLimitError
from terminex.providers.commodities_yahoo import CommoditiesYahoo
from terminex.providers.crypto_coingecko import CryptoCoinGecko


class TestPollFloors(unittest.TestCase):
    def test_coingecko_polls_no_faster_than_its_cache(self):
        # The public API caches ~60s; faster polling repeats prices and
        # trips the per-IP rate limit.
        self.assertGreaterEqual(CryptoCoinGecko.min_poll_interval, 60.0)

    def test_yahoo_has_a_poll_floor(self):
        self.assertGreaterEqual(CommoditiesYahoo.min_poll_interval, 60.0)


def _response(status=200, payload=None, headers=None):
    resp = mock.Mock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.json.return_value = payload
    if status >= 400:
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    else:
        resp.raise_for_status.return_value = None
    return resp


# Invented numbers in the shape of Yahoo's v8 spark response.
SPARK = {
    "GC=F": {
        "symbol": "GC=F", "previousClose": 4000.0, "chartPreviousClose": 3900.0,
        "timestamp": [1, 2, 3, 4], "close": [3950.0, None, 4010.0, 4040.0],
        "end": 1793853379,
    },
    "ZW=F": {
        "symbol": "ZW=F", "previousClose": 600.0, "chartPreviousClose": 590.0,
        "timestamp": [1, 2], "close": [595.0, 612.0], "end": 1793853370,
    },
    "SI=F": {
        "symbol": "SI=F", "previousClose": 50.0, "chartPreviousClose": 52.0,
        "timestamp": [1], "close": [None], "end": 1793853386,
    },
}


class TestCommoditiesYahoo(unittest.TestCase):
    def _fetch(self, payload=SPARK, status=200, headers=None):
        provider = CommoditiesYahoo(
            symbols=[("GC=F", "Gold", "oz", False),
                     ("ZW=F", "Wheat", "bu", True),
                     ("SI=F", "Silver", "oz", False)]
        )
        with mock.patch(
            "terminex.providers.commodities_yahoo.requests.get",
            return_value=_response(status, payload, headers),
        ) as get:
            snap = provider.fetch()
        return snap, get

    def test_symbols_keep_dotted_names_for_existing_pins(self):
        snap, _ = self._fetch()
        self.assertEqual([q.symbol for q in snap.quotes], ["GC.F", "ZW.F"])

    def test_last_price_and_24h_change(self):
        gold = self._fetch()[0].quotes[0]
        self.assertEqual(gold.price, 4040.0)
        self.assertAlmostEqual(gold.change_24h_pct, 1.0)

    def test_cents_are_converted_to_dollars(self):
        wheat = self._fetch()[0].quotes[1]
        self.assertAlmostEqual(wheat.price, 6.12)
        self.assertEqual(wheat.meta["unit"], "bu")

    def test_history_and_7d_change_in_meta(self):
        gold = self._fetch()[0].quotes[0]
        self.assertEqual(gold.meta["history"], [3950.0, 4010.0, 4040.0])
        self.assertAlmostEqual(gold.meta["change_7d_pct"], (4040 / 3900 - 1) * 100)

    def test_symbol_without_prices_is_skipped(self):
        snap, _ = self._fetch()
        self.assertNotIn("SI.F", [q.symbol for q in snap.quotes])

    def test_identifies_itself(self):
        _, get = self._fetch()
        ua = get.call_args.kwargs["headers"]["User-Agent"]
        self.assertIn("terminex", ua)

    def test_rate_limit(self):
        with self.assertRaises(RateLimitError) as ctx:
            self._fetch(status=429, headers={"Retry-After": "30"})
        self.assertEqual(ctx.exception.retry_after, 30.0)

    def test_empty_payload(self):
        with self.assertRaises(ProviderError):
            self._fetch(payload={})

    def test_http_error(self):
        with self.assertRaises(ProviderError):
            self._fetch(status=404, payload=None)


if __name__ == "__main__":
    unittest.main()
