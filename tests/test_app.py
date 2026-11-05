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


if __name__ == "__main__":
    unittest.main()
