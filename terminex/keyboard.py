"""Non-blocking single-keystroke reader for POSIX terminals."""

from __future__ import annotations

import queue
import select
import sys
import termios
import threading
import tty
from typing import Iterator

# How long to wait after reading ESC for a follow-up CSI byte. Arrow
# keys / function keys deliver ``\x1b[A``-style sequences in one burst,
# so a short window is enough to distinguish them from a bare Esc
# keypress.
_ESC_FOLLOWUP_TIMEOUT = 0.02

# Synthetic key tokens emitted for CSI sequences we care about.
KEY_UP = "<up>"
KEY_DOWN = "<down>"
KEY_LEFT = "<left>"
KEY_RIGHT = "<right>"

# Final byte → synthetic token for simple (no-parameter) CSI sequences.
_CSI_MAP: dict[str, str] = {
    "A": KEY_UP,
    "B": KEY_DOWN,
    "C": KEY_RIGHT,
    "D": KEY_LEFT,
}


class KeyboardListener:
    """Background thread that reads single keypresses from stdin.

    Arrow keys are decoded to synthetic tokens (``<up>``, ``<down>``,
    ``<left>``, ``<right>``). Other multi-byte CSI sequences are drained
    and discarded so they do not leak as stray keypresses.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._old_attrs: list | None = None
        self._fd: int | None = None

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        fd = sys.stdin.fileno()
        old_attrs = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
        except Exception:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
            raise
        self._fd = fd
        self._old_attrs = old_attrs
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._old_attrs is not None and self._fd is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)
            self._old_attrs = None

    def _run(self) -> None:
        fd = self._fd
        while not self._stop.is_set():
            try:
                ch = sys.stdin.read(1)
            except (OSError, ValueError):
                return
            if not ch:
                return
            if ch == "\x1b" and fd is not None:
                # Possible CSI/SS3 sequence (arrow keys, F-keys, etc).
                # Peek briefly; if more bytes arrive, decode the sequence.
                # Otherwise emit bare Esc.
                if _has_pending(fd, _ESC_FOLLOWUP_TIMEOUT):
                    token = _decode_csi(fd)
                    if token:
                        self._queue.put(token)
                    continue
            self._queue.put(ch)

    def drain(self) -> Iterator[str]:
        """Yield all pending keypresses without blocking."""
        while True:
            try:
                yield self._queue.get_nowait()
            except queue.Empty:
                return


def _has_pending(fd: int, timeout: float) -> bool:
    r, _, _ = select.select([fd], [], [], timeout)
    return bool(r)


def _decode_csi(fd: int) -> str | None:
    """Read a CSI (``\\x1b[…``) or SS3 (``\\x1bO…``) sequence.

    Returns a synthetic key token for recognized sequences, or None
    for unrecognized ones. Either way the bytes are consumed.
    """
    try:
        intro = sys.stdin.read(1)
    except (OSError, ValueError):
        return None
    if intro not in ("[", "O"):
        return None
    # Accumulate parameter/intermediate bytes (0x20-0x3F) up to the
    # final byte (0x40-0x7E). Cap to guard against pathological input.
    param = ""
    for _ in range(8):
        if not _has_pending(fd, _ESC_FOLLOWUP_TIMEOUT):
            break
        try:
            b = sys.stdin.read(1)
        except (OSError, ValueError):
            return None
        if not b:
            return None
        if 0x40 <= ord(b) <= 0x7E:
            # Simple sequences ([A, [B, [C, [D) have no parameter bytes.
            if not param:
                return _CSI_MAP.get(b)
            return None
        param += b
    return None
