"""Tests for terminex.converter (parser + USD-pivot engine)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from terminex.converter import (
    ParseError,
    ResolveError,
    build_usd_lookup,
    convert,
    evaluate,
    parse_query,
)
from terminex.quote import Quote, Snapshot


def _snap(asset_class, quote_ccy, rows):
    return Snapshot(
        asset_class=asset_class,
        quote_ccy=quote_ccy,
        quotes=[Quote(sym, sym, price, quote_ccy) for sym, price in rows],
        fetched_at=datetime.now(tz=timezone.utc),
    )


class TestParseQuery(unittest.TestCase):
    def test_basic(self):
        q = parse_query("1 BTC in EUR")
        self.assertEqual((q.amount, q.from_symbol, q.to_symbol), (1.0, "BTC", "EUR"))

    def test_case_insensitive(self):
        q = parse_query("500 eur in jpy")
        self.assertEqual(q.from_symbol, "EUR")
        self.assertEqual(q.to_symbol, "JPY")

    def test_decimal_amount(self):
        self.assertEqual(parse_query("1.5 GC.F in EUR").amount, 1.5)

    def test_thousand_separator(self):
        self.assertEqual(parse_query("1,000 USD in JPY").amount, 1000.0)

    def test_alt_connectors(self):
        for conn in ("in", "to", "->", "→"):
            q = parse_query(f"1 EUR {conn} USD")
            self.assertEqual(q.from_symbol, "EUR")
            self.assertEqual(q.to_symbol, "USD")

    def test_commodity_symbol_with_dot(self):
        q = parse_query("1 GC.F in EUR")
        self.assertEqual(q.from_symbol, "GC.F")

    def test_rejects_garbage(self):
        for bad in ("foo", "1 BTC", "1 in EUR", "BTC in EUR"):
            with self.assertRaises(ParseError):
                parse_query(bad)

    def test_rejects_nonpositive(self):
        for bad in ("0 BTC in EUR", "-5 BTC in EUR"):
            with self.assertRaises(ParseError):
                parse_query(bad)


class TestBuildUsdLookup(unittest.TestCase):
    def test_fx_inverts_price(self):
        # EUR price 0.8 means 0.8 EUR per 1 USD → 1 EUR = 1.25 USD
        snaps = {"fx": _snap("fx", "USD", [("USD", 1.0), ("EUR", 0.8)])}
        lookup = build_usd_lookup(snaps)
        self.assertAlmostEqual(lookup["EUR"], 1.25)
        self.assertEqual(lookup["USD"], 1.0)

    def test_crypto_price_is_usd(self):
        snaps = {
            "fx": None,
            "crypto": _snap("crypto", "USD", [("BTC", 65000.0)]),
        }
        lookup = build_usd_lookup(snaps)
        self.assertEqual(lookup["BTC"], 65000.0)

    def test_preference_order_fx_wins(self):
        # Same symbol in fx and crypto — fx should win
        snaps = {
            "fx": _snap("fx", "USD", [("USD", 1.0), ("XXX", 2.0)]),
            "crypto": _snap("crypto", "USD", [("XXX", 999.0)]),
        }
        lookup = build_usd_lookup(snaps)
        self.assertAlmostEqual(lookup["XXX"], 0.5)  # fx inverts: 1/2

    def test_skips_zero_prices(self):
        snaps = {"crypto": _snap("crypto", "USD", [("ZERO", 0.0)])}
        lookup = build_usd_lookup(snaps)
        self.assertNotIn("ZERO", lookup)

    def test_handles_missing_snapshots(self):
        snaps = {"fx": None, "crypto": None, "commodity": None}
        self.assertEqual(build_usd_lookup(snaps), {})


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.lookup = {"USD": 1.0, "EUR": 1.25, "JPY": 0.00625, "BTC": 65000.0}

    def test_usd_to_eur(self):
        r = convert(parse_query("100 USD in EUR"), self.lookup)
        self.assertAlmostEqual(r.result, 80.0)

    def test_round_trip(self):
        # 1 EUR → USD → EUR should land back at 1
        step1 = convert(parse_query("1 EUR in USD"), self.lookup)
        step2 = convert(
            parse_query(f"{step1.result} USD in EUR"), self.lookup
        )
        self.assertAlmostEqual(step2.result, 1.0)

    def test_cross_asset(self):
        r = convert(parse_query("1 BTC in EUR"), self.lookup)
        self.assertAlmostEqual(r.result, 65000.0 / 1.25)

    def test_unknown_symbol_raises(self):
        with self.assertRaises(ResolveError):
            convert(parse_query("1 XYZ in USD"), self.lookup)
        with self.assertRaises(ResolveError):
            convert(parse_query("1 USD in XYZ"), self.lookup)


class TestEvaluate(unittest.TestCase):
    def test_parse_errors_propagate(self):
        with self.assertRaises(ParseError):
            evaluate("bogus", {})
        with self.assertRaises(ResolveError):
            evaluate("1 A in B", {"A": 1.0})


if __name__ == "__main__":
    unittest.main()
