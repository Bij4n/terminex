"""Provider behaviour tests (no network: requests.get is mocked)."""

from __future__ import annotations

import unittest

from terminex.providers.crypto_coingecko import CryptoCoinGecko


class TestPollFloors(unittest.TestCase):
    def test_coingecko_polls_no_faster_than_its_cache(self):
        # The public API caches ~60s; faster polling repeats prices and
        # trips the per-IP rate limit.
        self.assertGreaterEqual(CryptoCoinGecko.min_poll_interval, 60.0)


if __name__ == "__main__":
    unittest.main()
