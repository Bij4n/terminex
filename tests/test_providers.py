"""Provider behaviour tests (no network: requests.get is mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from terminex.providers.base import (
    ProviderError,
    RateLimitError,
    describe_request_error,
    parse_retry_after,
)
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

    def test_provider_time_is_the_latest_data_point(self):
        # `end` marks the end of the *first* session in the range; the
        # latest quote time is the last timestamp.
        payload = {"GC=F": {"close": [4000.0, 4040.0], "timestamp": [1793300000, 1793856524],
                            "end": 1793332740}}
        snap, _ = self._fetch(payload=payload)
        self.assertEqual(int(snap.provider_time.timestamp()), 1793856524)

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

    def test_malformed_entries_are_skipped_not_fatal(self):
        payload = {
            "GC=F": {"close": 3},                                   # not a list
            "ZW=F": {"close": [True, float("nan"), float("inf")]},  # no usable numbers
            "SI=F": {"close": [50.0, 51.0], "previousClose": "x",
                     "chartPreviousClose": float("inf"), "timestamp": [1, 10**20]},
        }
        snap, _ = self._fetch(payload=payload)
        self.assertEqual([q.symbol for q in snap.quotes], ["SI.F"])
        silver = snap.quotes[0]
        self.assertEqual(silver.price, 51.0)
        self.assertIsNone(silver.change_24h_pct)
        self.assertNotIn("change_7d_pct", silver.meta)
        self.assertIsNone(snap.provider_time)

    def test_only_malformed_entries_is_a_provider_error(self):
        with self.assertRaises(ProviderError):
            self._fetch(payload={"GC=F": {"close": "4040"}})


class TestFxPayloads(unittest.TestCase):
    def test_non_numeric_rate_is_skipped(self):
        from terminex.providers.fx_erapi import FxERApi
        resp = _response(200, {"result": "success", "rates": {"EUR": "abc", "JPY": 158.0, "GBP": None}})
        with mock.patch("terminex.providers.fx_erapi.requests.get", return_value=resp):
            symbols = [q.symbol for q in FxERApi().fetch().quotes]
        self.assertIn("JPY", symbols)
        self.assertNotIn("EUR", symbols)


class TestCoinCapPayloads(unittest.TestCase):
    def test_strings_nan_and_bad_entries(self):
        from terminex.providers.crypto_coincap import CryptoCoinCap
        resp = _response(200, {"timestamp": 10**30, "data": [
            "junk",
            {"symbol": "BTC", "name": "Bitcoin", "priceUsd": "nan"},
            {"symbol": "ETH", "name": "Ethereum", "priceUsd": "2400.5", "changePercent24Hr": "inf"},
        ]})
        with mock.patch("terminex.providers.crypto_coincap.requests.get", return_value=resp):
            snap = CryptoCoinCap(api_key="k").fetch()
        self.assertEqual([(q.symbol, q.price, q.change_24h_pct) for q in snap.quotes], [("ETH", 2400.5, None)])
        self.assertIsNone(snap.provider_time)


class TestEmptyResultsAreErrors(unittest.TestCase):
    def test_every_provider_rejects_an_empty_result(self):
        from terminex.providers.crypto_coincap import CryptoCoinCap
        from terminex.providers.fx_erapi import FxERApi
        cases = [
            ("crypto_coingecko", CryptoCoinGecko(), []),
            ("crypto_coincap", CryptoCoinCap(api_key="k"), {"data": []}),
            ("fx_erapi", FxERApi(), {"result": "success", "rates": {"XXX": 1.0}}),
            ("commodities_yahoo", CommoditiesYahoo(), {}),
        ]
        for module, provider, payload in cases:
            with self.subTest(provider=provider.name):
                with mock.patch(f"terminex.providers.{module}.requests.get",
                                return_value=_response(200, payload)):
                    with self.assertRaises(ProviderError):
                        provider.fetch()


class TestCoinGeckoPayloads(unittest.TestCase):
    def test_non_finite_values_are_dropped(self):
        resp = _response(200, [
            {"symbol": "btc", "name": "Bitcoin", "current_price": float("inf")},
            {"symbol": "eth", "name": "Ethereum", "current_price": 2400,
             "sparkline_in_7d": {"price": [2300, float("nan"), True, 2400]}},
        ])
        with mock.patch("terminex.providers.crypto_coingecko.requests.get", return_value=resp):
            quotes = CryptoCoinGecko().fetch().quotes
        self.assertEqual([q.symbol for q in quotes], ["ETH"])
        self.assertEqual(quotes[0].meta["history"], [2300.0, 2400.0])



class TestRetryAfter(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(parse_retry_after("30", default=60), 30.0)

    def test_missing_or_garbage_uses_default(self):
        self.assertEqual(parse_retry_after(None, default=60), 60.0)
        self.assertEqual(parse_retry_after("soon", default=60), 60.0)

    def test_http_date(self):
        from email.utils import format_datetime
        from datetime import datetime, timedelta, timezone
        when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=90), usegmt=True)
        self.assertAlmostEqual(parse_retry_after(when, default=60), 90.0, delta=3)

    def test_non_finite_and_extremes_are_bounded(self):
        self.assertEqual(parse_retry_after("inf", default=60), 60.0)
        self.assertEqual(parse_retry_after("nan", default=60), 60.0)
        self.assertEqual(parse_retry_after("0", default=60), 1.0)
        self.assertEqual(parse_retry_after("999999", default=60), 3600.0)

    def test_coingecko_survives_a_date_header(self):
        resp = _response(429, None, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        with mock.patch("terminex.providers.crypto_coingecko.requests.get", return_value=resp):
            with self.assertRaises(RateLimitError):
                CryptoCoinGecko().fetch()



class TestRequestErrorMessages(unittest.TestCase):
    def test_plain_sentences(self):
        import requests
        name = "open.er-api.com"
        self.assertEqual(
            describe_request_error(name, requests.ConnectionError("HTTPSConnectionPool(...) NameResolutionError")),
            "can't reach open.er-api.com — check your connection",
        )
        self.assertEqual(describe_request_error(name, requests.Timeout("read timeout")),
                         "open.er-api.com didn't answer in time")
        resp = mock.Mock(status_code=503)
        self.assertEqual(describe_request_error(name, requests.HTTPError("503", response=resp)),
                         "open.er-api.com returned HTTP 503")

    def test_provider_uses_it(self):
        import requests
        from terminex.providers.fx_erapi import FxERApi
        with mock.patch("terminex.providers.fx_erapi.requests.get",
                        side_effect=requests.ConnectionError("Max retries exceeded ... ProxyError(...)")):
            with self.assertRaises(ProviderError) as ctx:
                FxERApi().fetch()
        self.assertEqual(str(ctx.exception), "can't reach open.er-api.com — check your connection")


if __name__ == "__main__":
    unittest.main()
