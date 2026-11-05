"""Tests for terminex.config value validation and CLI argument checks."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from terminex.app import parse_args
from terminex.config import Config, load


class TestConfigValues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.toml"
        # Keep a developer's real key out of the comparison.
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("TERMINEX_COINCAP_KEY", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _load(self, text: str) -> tuple[Config, str]:
        self.path.write_text(text)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cfg = load(self.path)
        return cfg, err.getvalue()

    def test_valid_values(self):
        cfg, err = self._load(
            'base_currency = "eur"\nrefresh_interval = 15\nactive_tab = "Crypto"\n'
        )
        self.assertEqual(cfg, Config("EUR", 15.0, "crypto", ""))
        self.assertEqual(err, "")

    def test_non_numeric_interval_falls_back_with_warning(self):
        cfg, err = self._load('refresh_interval = "ten"\n')
        self.assertEqual(cfg.refresh_interval, 10.0)
        self.assertIn("refresh_interval", err)

    def test_non_positive_interval_falls_back(self):
        cfg, err = self._load("refresh_interval = 0\n")
        self.assertEqual(cfg.refresh_interval, 10.0)
        self.assertIn("refresh_interval", err)

    def test_bool_interval_rejected(self):
        cfg, err = self._load("refresh_interval = true\n")
        self.assertEqual(cfg.refresh_interval, 10.0)
        self.assertIn("refresh_interval", err)

    def test_non_string_base_falls_back(self):
        cfg, err = self._load("base_currency = 5\n")
        self.assertEqual(cfg.base_currency, "USD")
        self.assertIn("base_currency", err)

    def test_malformed_base_falls_back(self):
        cfg, err = self._load('base_currency = "euro"\n')
        self.assertEqual(cfg.base_currency, "USD")
        self.assertIn("base_currency", err)

    def test_unknown_tab_falls_back(self):
        cfg, err = self._load('active_tab = "nope"\n')
        self.assertEqual(cfg.active_tab, "fx")
        self.assertIn("active_tab", err)

    def test_env_key_overrides_file(self):
        os.environ["TERMINEX_COINCAP_KEY"] = "from-env"
        cfg, _ = self._load('[providers.crypto]\napi_key = "from-file"\n')
        self.assertEqual(cfg.coincap_api_key, "from-env")

    def test_providers_not_a_table(self):
        cfg, err = self._load('providers = "x"\n')
        self.assertEqual(cfg.coincap_api_key, "")
        self.assertIn("providers", err)


class TestFxErrorMessages(unittest.TestCase):
    def test_unsupported_base_is_explained(self):
        from terminex.providers.base import ProviderError
        from terminex.providers.fx_erapi import FxERApi

        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"result": "error", "error-type": "unsupported-code"}
        with mock.patch("terminex.providers.fx_erapi.requests.get", return_value=resp):
            with self.assertRaises(ProviderError) as ctx:
                FxERApi(base="XYZ").fetch()
        self.assertIn("does not support base currency 'XYZ'", str(ctx.exception))


class TestParseArgs(unittest.TestCase):
    def _error(self, argv: list[str]) -> str:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            parse_args(argv)
        return err.getvalue()

    def test_interval_must_be_positive(self):
        self.assertIn("--interval", self._error(["--interval", "0"]))
        self.assertIn("--interval", self._error(["--interval=-5"]))

    def test_base_must_be_three_letters(self):
        self.assertIn("--base", self._error(["--base", "euro"]))
        self.assertIn("--base", self._error(["--base", "5"]))

    def test_base_is_uppercased(self):
        self.assertEqual(parse_args(["--base", "eur"]).base, "EUR")

    def test_valid_interval(self):
        self.assertEqual(parse_args(["--interval", "2.5"]).interval, 2.5)


if __name__ == "__main__":
    unittest.main()
