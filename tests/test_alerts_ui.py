"""Alert list formatting."""

from __future__ import annotations

import os
import time
import unittest

from terminex.alerts_ui import format_local_time


@unittest.skipUnless(hasattr(time, "tzset"), "needs time.tzset (POSIX)")
class TestLocalTime(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Los_Angeles"
        time.tzset()

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def test_utc_timestamp_shown_in_local_time(self):
        # 04:21 UTC on the 5th is 20:21 on the 4th in Los Angeles (PST).
        self.assertEqual(format_local_time("2026-11-05T04:21:55+00:00"), "2026-11-04 20:21")

    def test_missing_value(self):
        self.assertEqual(format_local_time(None), "—")


if __name__ == "__main__":
    unittest.main()
