"""Tests for terminex.watchlist."""

from __future__ import annotations

import contextlib
import io
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
            with contextlib.redirect_stderr(io.StringIO()):
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



class TestCorruptWatchlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "watchlist.toml"
        self.broken = '[[pins]]\nasset_class = "crypto"\nsymbol = \n[[pins'
        self.path.write_text(self.broken)

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            wl = load(self.path)
        return wl, err.getvalue()

    def test_warns_and_backs_up(self):
        wl, err = self._load()
        self.assertEqual(wl.pins, [])
        self.assertIn("watchlist", err)
        self.assertIn(".bak", err)
        self.assertEqual(self.path.with_suffix(".toml.bak").read_text(), self.broken)

    def test_next_save_keeps_the_backup(self):
        wl, _ = self._load()
        wl.add(Pin("fx", "USD"))
        save(wl, self.path)
        self.assertEqual(self.path.with_suffix(".toml.bak").read_text(), self.broken)
        self.assertEqual(load(self.path).pins, [Pin("fx", "USD")])


class TestAtomicSave(unittest.TestCase):
    def test_no_temp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "watchlist.toml"
            save(Watchlist(pins=[Pin("crypto", "BTC")]), path)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["watchlist.toml"])


if __name__ == "__main__":
    unittest.main()
