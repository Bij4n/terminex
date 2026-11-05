"""Trend column rendering and live-series bookkeeping."""

from __future__ import annotations

import unittest
from unittest import mock

from terminex import theme
from terminex.series import SeriesStore
from terminex.sparkline import BLOCKS, render


def _bars(text) -> str:
    """The sparkline glyphs only (drop padding and the % label)."""
    return "".join(ch for ch in text.plain if ch in BLOCKS)


class TestRender(unittest.TestCase):
    def test_long_history_is_sampled_to_width(self):
        series = [float(i) for i in range(168)]
        bars = _bars(render(series, width=20))
        self.assertEqual(len(bars), 20)
        self.assertEqual(bars[0], BLOCKS[0])
        self.assertEqual(bars[-1], BLOCKS[-1])  # last point is the latest price

    def test_tiny_moves_stay_flat(self):
        # A stablecoin wandering 0.04% must not fill the full height.
        series = [1.0000, 1.0004, 0.9999, 1.0002, 1.0001]
        bars = _bars(render(series, width=20))
        self.assertTrue(set(bars) <= {BLOCKS[3], BLOCKS[4]}, bars)

    def test_real_moves_use_full_height(self):
        bars = _bars(render([100.0, 90.0, 110.0], width=20))
        self.assertIn(BLOCKS[0], bars)
        self.assertIn(BLOCKS[-1], bars)

    def test_label_uses_given_change(self):
        self.assertTrue(render([1.0, 2.0], change_pct=4.99).plain.endswith("+4.99%"))

    def test_label_falls_back_to_first_last(self):
        self.assertTrue(render([100.0, 101.0]).plain.endswith("+1.00%"))

    def test_width_is_constant(self):
        widths = {
            len(render(s, width=20).plain)
            for s in ([], [1.0], [1.0, 2.0], [float(i) for i in range(200)])
        }
        self.assertEqual(len(widths), 1, widths)

    def test_single_point_is_a_placeholder_not_a_block(self):
        text = render([1.1237], width=20)
        self.assertEqual(_bars(text), "")
        self.assertEqual(text.plain.strip(), "·")

    def test_colour_follows_direction(self):
        self.assertEqual(render([1.0, 2.0]).spans[-1].style, theme.UP)
        self.assertEqual(render([2.0, 1.0]).spans[-1].style, theme.DOWN)


class TestSeriesStore(unittest.TestCase):
    def test_repeated_price_is_not_stored_twice(self):
        store = SeriesStore()
        for price in (10.0, 10.0, 10.0, 11.0, 11.0, 10.0):
            store.append("crypto", "BTC", price)
        self.assertEqual(store.get("crypto", "BTC"), [10.0, 11.0, 10.0])


class TestCoinGeckoHistory(unittest.TestCase):
    def test_week_of_prices_and_7d_change_in_meta(self):
        from terminex.providers.crypto_coingecko import CryptoCoinGecko

        resp = mock.Mock(status_code=200, headers={})
        resp.raise_for_status.return_value = None
        resp.json.return_value = [{
            "symbol": "btc", "name": "Bitcoin", "current_price": 80000,
            "price_change_percentage_24h": 4.8, "market_cap_rank": 1,
            "price_change_percentage_7d_in_currency": 0.78,
            "sparkline_in_7d": {"price": [79000.0, None, 80500.0]},
        }]
        with mock.patch(
            "terminex.providers.crypto_coingecko.requests.get", return_value=resp
        ) as get:
            quote = CryptoCoinGecko().fetch().quotes[0]
        self.assertEqual(get.call_args.kwargs["params"]["sparkline"], "true")
        self.assertEqual(quote.meta["history"], [79000.0, 80500.0])
        self.assertEqual(quote.meta["change_7d_pct"], 0.78)


if __name__ == "__main__":
    unittest.main()
