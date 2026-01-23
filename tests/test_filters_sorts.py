"""Tests for terminex.app filter/sort helpers and terminex.statusbar.format_age."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from terminex.app import _filter_quotes, _sort_quotes
from terminex.quote import Quote
from terminex.statusbar import format_age


def _q(symbol: str, name: str, price: float, change: float | None = None) -> Quote:
    return Quote(symbol, name, price, "USD", change_24h_pct=change)


class TestFilterQuotes(unittest.TestCase):
    def setUp(self):
        self.quotes = [
            _q("USD", "US Dollar", 1.0),
            _q("EUR", "Euro", 0.87),
            _q("GBP", "British Pound", 0.75),
            _q("AUD", "Australian Dollar", 1.45),
        ]

    def test_empty_query_returns_all(self):
        self.assertEqual(len(_filter_quotes(self.quotes, "")), 4)

    def test_symbol_match(self):
        result = _filter_quotes(self.quotes, "EUR")
        self.assertEqual([q.symbol for q in result], ["EUR"])

    def test_name_match(self):
        result = _filter_quotes(self.quotes, "Dollar")
        symbols = {q.symbol for q in result}
        self.assertEqual(symbols, {"USD", "AUD"})

    def test_case_insensitive(self):
        self.assertEqual(
            len(_filter_quotes(self.quotes, "dollar")),
            len(_filter_quotes(self.quotes, "DOLLAR")),
        )

    def test_no_match(self):
        self.assertEqual(_filter_quotes(self.quotes, "zzzzz"), [])


class TestSortQuotes(unittest.TestCase):
    def setUp(self):
        self.quotes = [
            _q("A", "A", 10.0, 2.0),
            _q("B", "B", 5.0, -1.0),
            _q("C", "C", 20.0, None),
            _q("D", "D", 1.0, 0.5),
        ]

    def test_default_preserves_order(self):
        self.assertEqual(
            [q.symbol for q in _sort_quotes(self.quotes, "default", True)],
            ["A", "B", "C", "D"],
        )

    def test_price_desc(self):
        self.assertEqual(
            [q.symbol for q in _sort_quotes(self.quotes, "price", True)],
            ["C", "A", "B", "D"],
        )

    def test_price_asc(self):
        self.assertEqual(
            [q.symbol for q in _sort_quotes(self.quotes, "price", False)],
            ["D", "B", "A", "C"],
        )

    def test_24h_desc_puts_none_at_bottom(self):
        # desc = reverse=True, None is mapped to -inf → ends up last
        result = [q.symbol for q in _sort_quotes(self.quotes, "24h", True)]
        self.assertEqual(result[0], "A")  # +2.0
        self.assertEqual(result[-1], "C")  # None


class TestFormatAge(unittest.TestCase):
    def test_none(self):
        self.assertEqual(format_age(None), "—")

    def test_just_now(self):
        now = datetime.now(tz=timezone.utc)
        self.assertEqual(format_age(now), "just now")
        self.assertEqual(format_age(now - timedelta(seconds=1)), "just now")

    def test_seconds(self):
        now = datetime.now(tz=timezone.utc)
        self.assertEqual(format_age(now - timedelta(seconds=5)), "5s ago")
        self.assertEqual(format_age(now - timedelta(seconds=59)), "59s ago")

    def test_minutes(self):
        now = datetime.now(tz=timezone.utc)
        self.assertEqual(format_age(now - timedelta(minutes=1)), "1m ago")
        self.assertEqual(format_age(now - timedelta(minutes=45)), "45m ago")

    def test_hours(self):
        now = datetime.now(tz=timezone.utc)
        self.assertEqual(format_age(now - timedelta(hours=3)), "3h ago")


if __name__ == "__main__":
    unittest.main()
