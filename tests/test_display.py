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


if __name__ == "__main__":
    unittest.main()
