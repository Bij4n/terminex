"""Tests for terminex.keyboard key decoding and the pty-backed listener."""

from __future__ import annotations

import os
import time
import unittest

from terminex.keyboard import (
    KEY_DOWN,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_UP,
    KeyboardListener,
    split_keys,
)


class TestSplitKeys(unittest.TestCase):
    def test_plain_keys(self):
        self.assertEqual(split_keys("jk/"), ["j", "k", "/"])

    def test_csi_arrows(self):
        self.assertEqual(
            split_keys("\x1b[A\x1b[B\x1b[C\x1b[D"),
            [KEY_UP, KEY_DOWN, KEY_RIGHT, KEY_LEFT],
        )

    def test_ss3_arrows(self):
        # Terminals in application-cursor mode send ESC O A.
        self.assertEqual(split_keys("\x1bOA\x1bOB"), [KEY_UP, KEY_DOWN])

    def test_arrow_between_plain_keys(self):
        self.assertEqual(split_keys("j\x1b[Bk"), ["j", KEY_DOWN, "k"])

    def test_bare_escape(self):
        self.assertEqual(split_keys("\x1b"), ["\x1b"])

    def test_unknown_sequence_is_dropped(self):
        # Ctrl-Up (params) and F5 must not leak as stray keypresses.
        self.assertEqual(split_keys("\x1b[1;5A\x1b[15~q"), ["q"])

    def test_escape_then_plain_key(self):
        self.assertEqual(split_keys("\x1bj"), ["\x1b", "j"])

    def test_unicode(self):
        self.assertEqual(split_keys("é"), ["é"])


class TestListenerOverPty(unittest.TestCase):
    """Regression for arrow keys arriving as ESC, '[', 'A' (0.4.0)."""

    def setUp(self):
        self.master, self.slave = os.openpty()
        self.kb = KeyboardListener(fd=self.slave)
        self.kb.start()

    def tearDown(self):
        self.kb.stop()
        os.close(self.master)
        os.close(self.slave)

    def _drain_after(self, data: bytes) -> list[str]:
        os.write(self.master, data)
        deadline = time.monotonic() + 1.0
        keys: list[str] = []
        while time.monotonic() < deadline:
            keys.extend(self.kb.drain())
            if keys:
                time.sleep(0.1)  # let any stray trailing tokens arrive
                keys.extend(self.kb.drain())
                break
            time.sleep(0.01)
        return keys

    def test_up_arrow_in_one_burst(self):
        self.assertEqual(self._drain_after(b"\x1b[A"), [KEY_UP])

    def test_down_arrow_in_one_burst(self):
        self.assertEqual(self._drain_after(b"\x1b[B"), [KEY_DOWN])

    def test_bare_escape(self):
        self.assertEqual(self._drain_after(b"\x1b"), ["\x1b"])

    def test_multibyte_utf8(self):
        self.assertEqual(self._drain_after("é".encode()), ["é"])



class TestStartupInterrupted(unittest.TestCase):
    """A signal landing mid-start must not leave the tty in cbreak mode."""

    def test_system_exit_right_after_setcbreak_restores_the_tty(self):
        import termios
        import tty
        from unittest import mock

        master, slave = os.openpty()
        try:
            before = termios.tcgetattr(slave)
            real_setcbreak = tty.setcbreak

            def setcbreak_then_signal(fd, *args):
                real_setcbreak(fd, *args)
                raise SystemExit(143)

            kb = KeyboardListener(fd=slave)
            with mock.patch("terminex.keyboard.tty.setcbreak", setcbreak_then_signal):
                with self.assertRaises(SystemExit):
                    kb.start()
            self.assertEqual(termios.tcgetattr(slave), before)
        finally:
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
