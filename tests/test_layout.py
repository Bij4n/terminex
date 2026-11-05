"""Viewport scrolling and narrow-terminal column fitting."""

from __future__ import annotations

import io
import re
import unittest
from datetime import datetime, timezone

from rich.console import Console

from terminex.display import build_table, fit_table, scroll_offset
from terminex.quote import Quote, Snapshot


def _snap(n: int = 25) -> Snapshot:
    quotes = [
        Quote(
            f"C{i:02d}", f"Coin number {i}", 80595.0 - i, "USD", 4.52,
            meta={"history": [70000.0 + j * 50 for j in range(168)], "change_7d_pct": 0.78},
        )
        for i in range(n)
    ]
    return Snapshot("crypto", "USD", quotes, datetime.now(tz=timezone.utc), provider_name="test")


def _text(renderable, width: int) -> str:
    console = Console(width=width, file=io.StringIO(), color_system=None, legacy_windows=False)
    console.print(renderable)
    return console.file.getvalue()


class TestScrollOffset(unittest.TestCase):
    def test_everything_fits(self):
        self.assertEqual(scroll_offset(selected=20, offset=5, visible=25, total=25), 0)

    def test_follows_selection_down(self):
        self.assertEqual(scroll_offset(selected=20, offset=0, visible=15, total=25), 6)

    def test_follows_selection_up(self):
        self.assertEqual(scroll_offset(selected=3, offset=8, visible=15, total=25), 3)

    def test_keeps_offset_while_selection_visible(self):
        self.assertEqual(scroll_offset(selected=10, offset=4, visible=15, total=25), 4)

    def test_never_past_the_end(self):
        self.assertEqual(scroll_offset(selected=24, offset=20, visible=15, total=25), 10)


class TestBuildTable(unittest.TestCase):
    def test_hidden_columns_are_omitted(self):
        table = build_table(_snap(3), hidden=frozenset({"delta", "rank"}))
        headers = [str(c.header) for c in table.columns]
        self.assertNotIn("Δ since last", headers)
        self.assertNotIn("#", headers)

    def test_row_offset_numbers_and_selection(self):
        out = _text(build_table(_snap(25), selected_index=12, rows=slice(10, 13)), 120)
        self.assertEqual(re.findall(r"│\s+(\d+) │ C\d\d", out), ["11", "12", "13"])
        self.assertEqual(out.count("▍"), 1)
        self.assertIn("rows 11–13 of 25", out)


class TestFitTable(unittest.TestCase):
    def _fit(self, width: int, trend: bool = True) -> str:
        snap = _snap(5)
        getter = (lambda a, s: []) if trend else None
        table = fit_table(
            lambda hidden: build_table(snap, series_getter=getter, hidden=hidden),
            Console(width=width, file=io.StringIO()),
        )
        return _text(table, width)

    def test_prices_never_truncated_at_80_columns_with_trend(self):
        out = self._fit(80)
        self.assertIn("80,595.00", out)
        self.assertNotIn("…", out.split("Price")[1].split("\n")[2])

    def test_prices_survive_60_columns(self):
        out = self._fit(60, trend=False)
        self.assertIn("80,595.00", out)
        self.assertIn("+4.52%", out)

    def test_wide_terminal_keeps_every_column(self):
        out = self._fit(160)
        self.assertIn("Δ since last", out)
        self.assertIn("Coin number 1", out)

    def test_rows_stay_one_line(self):
        lines = [l for l in self._fit(60, trend=False).splitlines() if "C0" in l]
        self.assertEqual(len(lines), 5)


if __name__ == "__main__":
    unittest.main()
