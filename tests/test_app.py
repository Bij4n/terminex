"""App-level behaviour with fake providers (no network, temporary home)."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from rich.console import Console

from terminex.app import App
from terminex.config import Config
from terminex.providers.base import Provider, ProviderError, RateLimitError
from terminex.quote import Quote, Snapshot


class FakeProvider(Provider):
    name = "fake.example"

    def __init__(self, asset_class="crypto", quotes=None, error=None, floor=0.0, quote_ccy="USD"):
        self.asset_class = asset_class
        self.quote_ccy = quote_ccy
        self.quotes = quotes if quotes is not None else [Quote("BTC", "Bitcoin", 80000.0, "USD", 1.0)]
        self.error = error
        self.min_poll_interval = floor
        self.calls = 0

    def fetch(self) -> Snapshot:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Snapshot(self.asset_class, self.quote_ccy, list(self.quotes),
                        datetime.now(tz=timezone.utc), provider_name=self.name)


class AppTestCase(unittest.TestCase):
    """Builds an App whose config, data and providers are all throwaway."""

    width = 120
    height = 36

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {
            "HOME": self.tmp.name,
            "XDG_CONFIG_HOME": os.path.join(self.tmp.name, "config"),
            "XDG_DATA_HOME": os.path.join(self.tmp.name, "data"),
        }
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.app = App(config=Config(active_tab="crypto"), interval=10.0)
        self.app.console = Console(file=io.StringIO(), width=self.width,
                                   height=self.height, color_system=None)
        for name, asset in (("fx", "fx"), ("crypto", "crypto"), ("commodity", "commodity")):
            self.app.tabs[name].provider = FakeProvider(asset_class=asset)

    def tearDown(self):
        self.app.store.close()
        self.env.stop()
        self.tmp.cleanup()

    def frame(self) -> list[str]:
        self.app.console.file = io.StringIO()
        self.app.console.print(self.app._render())
        return self.app.console.file.getvalue().splitlines()


class TestOfflineMessages(AppTestCase):
    def test_error_panel_says_when_it_retries(self):
        crypto = FakeProvider(error=ProviderError("can't reach fake.example — check your connection"), floor=60.0)
        self.app.tabs["crypto"].provider = crypto
        self.app._refresh("crypto")
        text = "\n".join(self.frame())
        self.assertIn("can't reach fake.example", text)
        self.assertRegex(text, r"retrying in (29|30)s")  # errors retry within 30s

    def test_converter_names_the_missing_feed(self):
        self.app.tabs["crypto"].provider = FakeProvider(error=ProviderError("can't reach fake.example"))
        self.app.tabs["fx"].provider = FakeProvider(asset_class="fx", quotes=[
            Quote("USD", "US Dollar", 1.0, "USD"), Quote("EUR", "Euro", 0.89, "USD")])
        self.app.tabs["commodity"].provider = FakeProvider(asset_class="commodity", quotes=[
            Quote("GC.F", "Gold", 4150.0, "USD")])
        for tab in ("crypto", "fx", "commodity"):
            self.app._refresh(tab)
        self.app._handle_key("c")
        for ch in "1 BTC in EUR\r":
            self.app._handle_key(ch)
        self.assertEqual(self.app.converter_error,
                         "unknown symbol: 'BTC' — crypto prices aren't loaded")

    def test_several_missing_feeds_read_naturally(self):
        from terminex.app import _join_names
        self.assertEqual(_join_names(["FX", "crypto", "commodity"]), "FX, crypto and commodity")
        self.assertEqual(_join_names(["FX", "crypto"]), "FX and crypto")


class TestUnexpectedProviderErrors(AppTestCase):
    def test_bug_in_a_provider_becomes_an_error_panel(self):
        self.app.tabs["crypto"].provider = FakeProvider(error=TypeError("'int' object is not iterable"))
        self.app._refresh("crypto")  # must not raise
        self.assertIn("fake.example", self.app.tabs["crypto"].last_error)
        self.assertIn("fetch error", "\n".join(self.frame()))



class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestRateLimitsAndFloors(AppTestCase):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        patcher = mock.patch("terminex.app.time.monotonic", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.crypto = FakeProvider(floor=60.0)
        self.app.tabs["crypto"].provider = self.crypto

    def test_tab_switching_does_not_bypass_backoff(self):
        self.crypto.error = RateLimitError("slow down", retry_after=60)
        self.app._refresh("crypto")
        for _ in range(5):
            self.app._handle_key("1")
            self.app._handle_key("2")
        self.assertEqual(self.crypto.calls, 1)

    def test_manual_refresh_respects_backoff(self):
        self.crypto.error = RateLimitError("slow down", retry_after=60)
        self.app._refresh("crypto")
        self.clock.now += 20
        self.app._handle_key("r")
        self.assertEqual(self.crypto.calls, 1)
        self.assertIn("40s", self.app._active_toast())

    def test_manual_refresh_respects_the_provider_floor(self):
        self.app._refresh("crypto")
        self.clock.now += 15
        self.app._handle_key("r")
        self.assertEqual(self.crypto.calls, 1)
        self.assertIn("45s", self.app._active_toast())

    def test_manual_refresh_retries_after_an_ordinary_error(self):
        self.crypto.error = ProviderError("could not reach fake.example")
        self.app._refresh("crypto")
        self.crypto.error = None
        self.clock.now += 2
        self.app._handle_key("r")
        self.assertEqual(self.crypto.calls, 2)
        self.assertIsNone(self.app.tabs["crypto"].last_error)

    def test_failed_fetch_retries_within_30s_even_with_a_long_floor(self):
        fx = FakeProvider(asset_class="fx", error=ProviderError("can't reach fake.example"), floor=300.0)
        self.app.tabs["fx"].provider = fx
        self.app._refresh("fx")
        self.clock.now += 29
        self.assertFalse(self.app._needs_refresh("fx"))
        self.clock.now += 1
        self.assertTrue(self.app._needs_refresh("fx"))

    def test_scheduled_polling_waits_for_the_floor(self):
        self.app._refresh("crypto")
        self.clock.now += 59
        self.assertFalse(self.app._needs_refresh("crypto"))
        self.clock.now += 1
        self.assertTrue(self.app._needs_refresh("crypto"))



class TestWatchlistFxTrendNonUsdBase(AppTestCase):
    def test_usd_series_recorded_per_snapshot(self):
        fx = FakeProvider(asset_class="fx", quote_ccy="EUR", quotes=[
            Quote("EUR", "Euro", 1.0, "EUR"), Quote("USD", "US Dollar", 1.10, "EUR"),
            Quote("GBP", "Pound", 0.85, "EUR"),
        ])
        self.app.tabs["fx"].provider = fx
        self.app._refresh("fx")
        fx.quotes = [Quote("EUR", "Euro", 1.0, "EUR"), Quote("USD", "US Dollar", 1.12, "EUR"),
                     Quote("GBP", "Pound", 0.85, "EUR")]
        self.app._refresh("fx")
        get = self.app.series.get
        self.assertEqual(get("fx_usd", "USD"), [1.0])  # a dollar is always a dollar
        self.assertEqual(get("fx_usd", "EUR"), [1.10, 1.12])
        self.assertAlmostEqual(get("fx_usd", "GBP")[-1], 1.12 / 0.85)



def _coins(n=25):
    return [
        Quote(f"C{i:02d}", f"Coin number {i}", 80595.0 - i, "USD", 4.52,
              meta={"rank": i + 1, "history": [70000.0 + j * 50 for j in range(168)],
                    "change_7d_pct": 0.78})
        for i in range(n)
    ]


class FrameSizeMixin:
    """Render a whole frame at a given terminal size and check it fits."""

    def setUp(self):
        super().setUp()
        self.app.tabs["crypto"].provider = FakeProvider(quotes=_coins())
        self.app._refresh("crypto")
        self.app.show_sparklines = True

    def assert_fits(self, lines):
        self.assertLessEqual(len(lines), self.height, "\n".join(lines))
        self.assertTrue(all(len(l) <= self.width for l in lines))


class TestFrame120x36(FrameSizeMixin, AppTestCase):
    width, height = 120, 36

    def test_everything_shows(self):
        lines = self.frame()
        self.assert_fits(lines)
        text = "\n".join(lines)
        self.assertIn("Coin number 0", text)
        self.assertIn("? for keys", text)


class TestFrame80x24(FrameSizeMixin, AppTestCase):
    width, height = 80, 24

    def test_fits_with_whole_prices_and_status(self):
        self.app.tabs["crypto"].selected_index = 24
        lines = self.frame()
        self.assert_fits(lines)
        text = "\n".join(lines)
        self.assertIn("80,571.00", text)          # row 25, scrolled into view
        self.assertIn("? for keys", lines[-1])
        self.assertNotIn("…", text)


class TestFrame40x24(FrameSizeMixin, AppTestCase):
    width, height = 40, 24

    def test_wrapped_header_and_status_still_fit(self):
        lines = self.frame()
        self.assert_fits(lines)
        self.assertNotIn("80,5…", "\n".join(lines))


class TestFrameTooShort(FrameSizeMixin, AppTestCase):
    width, height = 60, 9

    def test_too_small_message_instead_of_a_cropped_table(self):
        lines = self.frame()
        self.assert_fits(lines)
        self.assertIn("too small", "\n".join(lines))


class TestFrameTooNarrow(FrameSizeMixin, AppTestCase):
    width, height = 28, 24

    def test_too_small_message_instead_of_truncated_prices(self):
        lines = self.frame()
        self.assert_fits(lines)
        text = "\n".join(lines)
        self.assertIn("too small", text)
        self.assertNotIn("80,5…", text)



class TestRunOnce(AppTestCase):
    def test_prints_the_table_and_exits_zero(self):
        self.assertEqual(self.app.run_once(), 0)
        out = self.app.console.file.getvalue()
        self.assertIn("BTC", out)
        self.assertIn("80,000.00", out)
        self.assertNotIn("? for keys", out)
        self.assertNotIn("since last", out)

    def test_failure_goes_to_stderr_with_exit_one(self):
        import contextlib
        self.app.tabs["crypto"].provider = FakeProvider(error=ProviderError("can't reach fake.example"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.app.run_once(), 1)
        self.assertIn("can't reach fake.example", err.getvalue())

    def test_alerts_are_not_evaluated(self):
        from terminex import alerts as alerts_dao
        alerts_dao.create(self.app.store, asset_class="crypto", symbol="BTC",
                          op=">", threshold=1.0, recurring=True)
        self.app.run_once()
        import sqlite3
        from terminex.store import db_path
        with sqlite3.connect(db_path()) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM fires").fetchone()[0], 0)


class TestOnceRouting(unittest.TestCase):
    def test_once_flag_or_non_terminal_output(self):
        from terminex.app import _wants_once, parse_args

        class Out:
            def __init__(self, tty):
                self.tty = tty

            def isatty(self):
                return self.tty

        self.assertTrue(_wants_once(parse_args(["--once"]), Out(True)))
        self.assertTrue(_wants_once(parse_args([]), Out(False)))
        self.assertFalse(_wants_once(parse_args([]), Out(True)))



class TestHelpAt80x24(AppTestCase):
    width, height = 80, 24

    def test_every_key_is_visible(self):
        self.app.show_help = True
        lines = self.frame()
        self.assertLessEqual(len(lines), 24, "\n".join(lines))
        text = "\n".join(lines)
        for key in ("← / →", "j k / ↓ ↑", "/", "w", "~", "c", "A", "r", "q"):
            self.assertIn(key, text)


if __name__ == "__main__":
    unittest.main()
