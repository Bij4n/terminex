"""Tests for terminex.watchlist."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from terminex.watchlist import Pin, Watchlist, load, save


class TestWatchlistInMemory(unittest.TestCase):
    def test_add_and_contains(self):
        wl = Watchlist()
        self.assertFalse(wl.contains("fx", "EUR"))
        self.assertTrue(wl.add(Pin("fx", "EUR")))
        self.assertTrue(wl.contains("fx", "EUR"))

    def test_add_is_idempotent(self):
        wl = Watchlist()
        wl.add(Pin("fx", "EUR"))
        self.assertFalse(wl.add(Pin("fx", "EUR")))
        self.assertEqual(len(wl.pins), 1)

    def test_remove(self):
        wl = Watchlist(pins=[Pin("fx", "EUR")])
        self.assertTrue(wl.remove("fx", "EUR"))
        self.assertFalse(wl.contains("fx", "EUR"))
        self.assertFalse(wl.remove("fx", "EUR"))  # second time

    def test_toggle(self):
        wl = Watchlist()
        self.assertTrue(wl.toggle("fx", "EUR"))
        self.assertTrue(wl.contains("fx", "EUR"))
        self.assertFalse(wl.toggle("fx", "EUR"))
        self.assertFalse(wl.contains("fx", "EUR"))

    def test_cross_class_distinction(self):
        wl = Watchlist(pins=[Pin("fx", "USD")])
        self.assertFalse(wl.contains("crypto", "USD"))


class TestWatchlistPersistence(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wl.toml"
            original = Watchlist(
                pins=[
                    Pin("fx", "EUR"),
                    Pin("crypto", "BTC"),
                    Pin("commodity", "GC.F"),
                ]
            )
            save(original, p)
            loaded = load(p)
            self.assertEqual(loaded.pins, original.pins)

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            loaded = load(Path(d) / "nonexistent.toml")
            self.assertEqual(loaded.pins, [])

    def test_malformed_toml_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.toml"
            p.write_text("this is = not = valid")
            loaded = load(p)
            self.assertEqual(loaded.pins, [])

    def test_invalid_asset_class_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.toml"
            p.write_text(
                '[[pins]]\nasset_class = "bogus"\nsymbol = "X"\n'
                '[[pins]]\nasset_class = "fx"\nsymbol = "EUR"\n'
            )
            loaded = load(p)
            self.assertEqual(len(loaded.pins), 1)
            self.assertEqual(loaded.pins[0].symbol, "EUR")


if __name__ == "__main__":
    unittest.main()
