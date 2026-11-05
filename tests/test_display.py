"""Price formatting and rank numbering in the table."""

from __future__ import annotations

import io
import re
import unittest
from datetime import datetime, timezone

from rich.console import Console

from terminex.display import _format_price, build_table
from terminex.quote import Quote, Snapshot


class TestFormatPrice(unittest.TestCase):
    def test_crypto_at_or_above_one_uses_cents(self):
        self.assertEqual(_format_price(713.63, "crypto"), "713.63")
        self.assertEqual(_format_price(95.9, "crypto"), "95.90")
        self.assertEqual(_format_price(80376.0, "crypto"), "80,376.00")

    def test_crypto_below_one_keeps_four_significant_digits(self):
        self.assertEqual(_format_price(0.07668, "crypto"), "0.07668")
        self.assertEqual(_format_price(0.99934, "crypto"), "0.9993")
        self.assertEqual(_format_price(0.00001234, "crypto"), "0.00001234")

    def test_fx_rates_keep_their_precision(self):
        self.assertEqual(_format_price(158.3779, "fx"), "158.3779")
        self.assertEqual(_format_price(0.889912, "fx"), "0.88991")
        self.assertEqual(_format_price(18132.17, "fx"), "18,132.17")

    def test_tiny_values_keep_four_significant_digits(self):
        # Watchlist FX pins are USD per unit: 1 IDR is about $0.0000613.
        self.assertEqual(_format_price(0.0000613, "fx"), "0.00006130")
        self.assertEqual(_format_price(0.000746, "fx"), "0.0007460")
        self.assertEqual(_format_price(0.18470, "commodity"), "0.18470")

    def test_commodities_keep_four_decimals(self):
        self.assertEqual(_format_price(6.0075, "commodity"), "6.0075")


def _render(table) -> str:
    console = Console(width=140, file=io.StringIO(), color_system=None)
    console.print(table)
    return console.file.getvalue()


class TestRankColumn(unittest.TestCase):
    def test_sorted_rows_keep_market_cap_rank(self):
        quotes = [
            Quote("ZEC", "Zcash", 1312.0, "USD", 9.1, meta={"rank": 10}),
            Quote("BTC", "Bitcoin", 80000.0, "USD", 4.7, meta={"rank": 1}),
        ]
        snap = Snapshot("crypto", "USD", quotes, datetime.now(tz=timezone.utc))
        out = _render(build_table(snap))
        self.assertEqual(re.findall(r"│\s+(\d+) │ (ZEC|BTC)", out), [("10", "ZEC"), ("1", "BTC")])

    def test_rank_map_used_when_provider_has_no_rank(self):
        quotes = [Quote("JPY", "Yen", 158.0, "USD"), Quote("EUR", "Euro", 0.89, "USD")]
        snap = Snapshot("fx", "USD", quotes, datetime.now(tz=timezone.utc))
        out = _render(build_table(snap, ranks={"EUR": 2, "JPY": 3}))
        self.assertEqual(re.findall(r"│\s+(\d+) │ (JPY|EUR)", out), [("3", "JPY"), ("2", "EUR")])



class TestWatchlistRankColumn(unittest.TestCase):
    def test_watchlist_numbers_rows_by_pin_order(self):
        quotes = [
            Quote("EUR", "Euro", 1.12, "USD", meta={"source_tab": "fx", "source_label": "FX"}),
            Quote("BTC", "Bitcoin", 80000.0, "USD", meta={"source_tab": "crypto", "source_label": "Crypto", "rank": 1}),
            Quote("GC.F", "Gold", 4150.0, "USD", meta={"source_tab": "commodity", "source_label": "Cmdty"}),
        ]
        snap = Snapshot("fx", "USD", quotes, datetime.now(tz=timezone.utc))
        out = _render(build_table(snap, is_watchlist=True, ranks={"EUR": 1, "BTC": 2, "GC.F": 3}))
        self.assertEqual(re.findall(r"│\s+(\d) │ \w+\s+│ (EUR|BTC|GC\.F)", out),
                         [("1", "EUR"), ("2", "BTC"), ("3", "GC.F")])


class TestWatchlistTrendSource(unittest.TestCase):
    def test_fx_pins_draw_the_usd_series(self):
        asked = []

        def getter(asset, symbol):
            asked.append((asset, symbol))
            return [1.10, 1.12]

        quotes = [Quote("EUR", "Euro", 1.12, "USD", meta={"source_tab": "fx", "source_label": "FX"})]
        snap = Snapshot("fx", "USD", quotes, datetime.now(tz=timezone.utc))
        out = _render(build_table(snap, is_watchlist=True, series_getter=getter))
        self.assertEqual(asked, [("fx_usd", "EUR")])
        self.assertIn("+1.82%", out)  # 1.10 → 1.12, no inversion


if __name__ == "__main__":
    unittest.main()
