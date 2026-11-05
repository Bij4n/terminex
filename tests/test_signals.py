"""SIGTERM/SIGHUP must unwind normally so the terminal is restored."""

from __future__ import annotations

import os
import signal
import unittest

from terminex.app import _exit_on_signals


class TestExitOnSignals(unittest.TestCase):
    def test_sigterm_becomes_system_exit(self):
        cleaned_up = []
        with self.assertRaises(SystemExit) as ctx:
            with _exit_on_signals():
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                    for _ in range(1000):  # give the handler a chance to run
                        pass
                finally:
                    cleaned_up.append(True)
        self.assertEqual(ctx.exception.code, 128 + signal.SIGTERM)
        self.assertEqual(cleaned_up, [True])

    def test_sighup_becomes_system_exit(self):
        with self.assertRaises(SystemExit) as ctx:
            with _exit_on_signals():
                os.kill(os.getpid(), signal.SIGHUP)
                for _ in range(1000):
                    pass
        self.assertEqual(ctx.exception.code, 128 + signal.SIGHUP)

    def test_previous_handlers_restored(self):
        before = signal.getsignal(signal.SIGTERM)
        with _exit_on_signals():
            self.assertNotEqual(signal.getsignal(signal.SIGTERM), before)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)


if __name__ == "__main__":
    unittest.main()
