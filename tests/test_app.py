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
        self.app = App(
            config=Config(active_tab="crypto"),
            interval=10.0,
            providers={t: FakeProvider(asset_class=t) for t in ("fx", "crypto", "commodity")},
            console=Console(file=io.StringIO(), width=self.width,
                            height=self.height, color_system=None),
        )

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


class TestRunOnceEmptyWatchlist(AppTestCase):
    def test_no_network_when_nothing_is_pinned(self):
        import contextlib
        self.app.active_tab = "watchlist"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.app.run_once(), 1)
        self.assertIn("no symbols pinned", err.getvalue())
        calls = sum(self.app.tabs[t].provider.calls for t in ("fx", "crypto", "commodity"))
        self.assertEqual(calls, 0)


class TestOverlaysSkipTheTable(AppTestCase):
    def test_help_and_modals_do_not_build_tables(self):
        self.app._refresh("crypto")
        with mock.patch("terminex.app.build_table") as build:
            self.app.show_help = True
            self.app._render()
            self.app.show_help = False
            self.app.input_mode = "converter"
            self.app._render()
        build.assert_not_called()


class TestCreatingAlerts(AppTestCase):
    def _create(self, op: str, threshold: str):
        from terminex import alerts as alerts_dao
        self.app._refresh("crypto")          # BTC at 80,000
        self.app._handle_key("a")
        draft = self.app.alert_draft
        draft["threshold_buffer"] = threshold
        draft["op"] = op
        self.app._handle_key("\r")
        return alerts_dao.list_all(self.app.store)[-1]

    def test_condition_already_true_starts_disarmed(self):
        self.assertFalse(self._create(">", "70000").armed)

    def test_condition_not_yet_true_starts_armed(self):
        self.assertTrue(self._create(">", "90000").armed)

    def test_uses_the_price_at_enter_not_when_the_modal_opened(self):
        from terminex import alerts as alerts_dao
        self.app._refresh("crypto")
        self.app._handle_key("a")                       # opened at 80,000
        self.app.tabs["crypto"].provider.quotes = [Quote("BTC", "Bitcoin", 95000.0, "USD")]
        self.app._refresh("crypto")                     # moved while typing
        self.app.alert_draft["threshold_buffer"] = "90000"
        self.app._handle_key("\r")
        self.assertFalse(alerts_dao.list_all(self.app.store)[-1].armed)

    def test_fx_alert_records_its_base(self):
        from terminex import alerts as alerts_dao
        self.app.tabs["fx"].provider = FakeProvider(asset_class="fx", quote_ccy="EUR", quotes=[
            Quote("EUR", "Euro", 1.0, "EUR"), Quote("JPY", "Yen", 177.0, "EUR")])
        self.app.tabs["fx"].provider.base = "EUR"
        self.app.active_tab = "fx"
        self.app._refresh("fx")
        self.app.tabs["fx"].selected_index = 1
        self.app._handle_key("a")
        self.app._handle_key("\r")
        self.assertEqual(alerts_dao.list_all(self.app.store)[-1].base, "EUR")


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



class TestFallbackChainInTheApp(AppTestCase):
    """A FallbackProvider driven through the app's refresh and backoff."""

    def setUp(self):
        super().setUp()
        from terminex.providers.fallback import FallbackProvider
        self.clock = Clock()
        for target in ("terminex.app.time.monotonic", "terminex.providers.fallback.time.monotonic"):
            patcher = mock.patch(target, self.clock)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.gecko = FakeProvider(floor=60.0)
        self.gecko.name = "coingecko.com"
        self.lore = FakeProvider(floor=60.0)
        self.lore.name = "coinlore.com"
        self.app.tabs["crypto"].provider = FallbackProvider(self.gecko, self.lore)

    def test_rate_limited_last_feed_does_not_freeze_the_tab(self):
        self.gecko.error = ProviderError("coingecko.com returned HTTP 503")
        self.lore.error = RateLimitError("coinlore.com rate limited", retry_after=1800)
        self.app._refresh("crypto")
        self.clock.now += 30
        self.assertTrue(self.app._needs_refresh("crypto"))   # not frozen for 1800 s

    def test_backoff_toast_does_not_blame_the_wrong_feed(self):
        self.gecko.error = RateLimitError("coingecko.com rate limited", retry_after=100)
        self.lore.error = RateLimitError("coinlore.com rate limited", retry_after=200)
        self.app._refresh("crypto")
        self.app._handle_key("r")
        # The serving feed's name isn't necessarily the one that is limited.
        self.assertRegex(self.app._active_toast(), r"^Rate limited — retrying in \d+s$")

    def test_delta_column_resets_when_the_serving_feed_changes(self):
        self.app._refresh("crypto")                          # served by CoinGecko
        self.gecko.error = ProviderError("down")
        self.lore.quotes = [Quote("BTC", "Bitcoin", 80100.0, "USD", 1.0)]
        self.clock.now += 60
        self.app._refresh("crypto")                          # now CoinLore
        self.assertIsNone(self.app.tabs["crypto"].previous_rates)


class TestWatchlistKeepsPolling(AppTestCase):
    """Staying on the watchlist must keep its pinned feeds fresh."""

    def setUp(self):
        super().setUp()
        self.clock = Clock()
        patcher = mock.patch("terminex.app.time.monotonic", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app.watchlist.toggle("fx", "EUR")
        self.fx = FakeProvider(asset_class="fx", error=ProviderError("can't reach fake.example"),
                               floor=300.0)
        self.app.tabs["fx"].provider = self.fx
        self.app.active_tab = "watchlist"

    def _row(self):
        return {q.symbol: q for q in self.app.tabs["watchlist"].last_snapshot.quotes}["EUR"]

    def test_failed_feed_recovers_while_on_the_watchlist(self):
        self.app._poll()
        self.assertTrue(self._row().meta.get("unavailable"))
        self.fx.error = None
        self.fx.quotes = [Quote("USD", "US Dollar", 1.0, "USD"), Quote("EUR", "Euro", 0.89, "USD")]
        self.clock.now += 30
        self.app._poll()
        self.assertAlmostEqual(self._row().price, 1 / 0.89)

    def test_prices_update_while_on_the_watchlist(self):
        self.fx.error = None
        self.fx.quotes = [Quote("USD", "US Dollar", 1.0, "USD"), Quote("EUR", "Euro", 0.89, "USD")]
        self.app._poll()
        self.fx.quotes = [Quote("USD", "US Dollar", 1.0, "USD"), Quote("EUR", "Euro", 0.80, "USD")]
        self.clock.now += 300
        self.app._poll()
        self.assertAlmostEqual(self._row().price, 1 / 0.80)

    def test_unpinned_feeds_are_not_polled(self):
        crypto = FakeProvider()
        self.app.tabs["crypto"].provider = crypto
        self.app._poll()
        self.clock.now += 300
        self.app._poll()
        self.assertEqual(crypto.calls, 0)



class FakeKeyboard:
    """Stands in for KeyboardListener: replays scripted keys."""

    def __init__(self, keys=()):
        self.keys = list(keys)
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def drain(self):
        while self.keys:
            yield self.keys.pop(0)


class TestInjection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {
            "HOME": self.tmp.name,
            "XDG_CONFIG_HOME": os.path.join(self.tmp.name, "config"),
            "XDG_DATA_HOME": os.path.join(self.tmp.name, "data"),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_default_providers_follow_the_config(self):
        from terminex.app import default_providers
        self.assertEqual(default_providers(Config())["crypto"].name, "coingecko.com")
        self.assertEqual(default_providers(Config(coincap_api_key="k"))["crypto"].name, "coincap.io")
        self.assertEqual(default_providers(Config(base_currency="EUR"))["fx"].base, "EUR")

    def test_app_uses_what_it_is_given(self):
        from terminex.store import connect_memory
        providers = {t: FakeProvider(asset_class=t) for t in ("fx", "crypto", "commodity")}
        store = connect_memory()
        console = Console(file=io.StringIO(), width=100, height=30)
        app = App(Config(), 10.0, providers=providers, store=store, console=console)
        self.assertIs(app.tabs["crypto"].provider, providers["crypto"])
        self.assertIs(app.store, store)
        self.assertIs(app.console, console)
        store.close()

    def test_main_loop_quits_on_q_and_cleans_up(self):
        from terminex.store import connect_memory
        keyboard = FakeKeyboard(["j", "q"])
        app = App(
            Config(active_tab="crypto"), 10.0,
            providers={t: FakeProvider(asset_class=t) for t in ("fx", "crypto", "commodity")},
            store=connect_memory(),
            console=Console(file=io.StringIO(), width=100, height=30),
            keyboard=lambda: keyboard,
        )
        self.assertEqual(app.run(), 0)
        self.assertTrue(keyboard.started and keyboard.stopped)
        self.assertIn("BTC", app.console.file.getvalue())


if __name__ == "__main__":
    unittest.main()
