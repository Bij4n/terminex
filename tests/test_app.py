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

    def __init__(self, asset_class="crypto", quotes=None, error=None, floor=0.0):
        self.asset_class = asset_class
        self.quotes = quotes if quotes is not None else [Quote("BTC", "Bitcoin", 80000.0, "USD", 1.0)]
        self.error = error
        self.min_poll_interval = floor
        self.calls = 0

    def fetch(self) -> Snapshot:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Snapshot(self.asset_class, "USD", list(self.quotes),
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

    def test_scheduled_polling_waits_for_the_floor(self):
        self.app._refresh("crypto")
        self.clock.now += 59
        self.assertFalse(self.app._needs_refresh("crypto"))
        self.clock.now += 1
        self.assertTrue(self.app._needs_refresh("crypto"))


if __name__ == "__main__":
    unittest.main()
