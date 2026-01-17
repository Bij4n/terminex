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


class KeyboardListener:
    """Background thread that reads single keypresses from stdin.

    Arrow keys and other multi-byte CSI sequences are drained and
    dropped so they do not masquerade as a sequence of ordinary
    keypresses (e.g. ``\\x1b`` + ``[`` + ``A``).
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
            # Restore on partial init so we don't leave the terminal
            # mode half-changed.
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
                # Peek briefly; if more bytes arrive, drain the sequence
                # and drop it. Otherwise emit bare Esc.
                if _has_pending(fd, _ESC_FOLLOWUP_TIMEOUT):
                    _drain_csi(fd)
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


def _drain_csi(fd: int) -> None:
    """Drain a CSI (``\\x1b[…letter``) or SS3 (``\\x1bO…letter``) sequence.

    Reads one introducer byte then continues reading until a final byte
    (``0x40``..``0x7E``) is seen or the input stalls. Bytes are consumed
    and discarded.
    """
    try:
        intro = sys.stdin.read(1)
    except (OSError, ValueError):
        return
    if intro not in ("[", "O"):
        # Not a recognized CSI/SS3 — put the unknown byte on the queue
        # as-is by ignoring it (safer than emitting a stray char).
        return
    # Read terminator (parameter/intermediate bytes range 0x20-0x3F,
    # final byte 0x40-0x7E). Cap at a few bytes to avoid pathological
    # input.
    for _ in range(8):
        if not _has_pending(fd, _ESC_FOLLOWUP_TIMEOUT):
            return
        try:
            b = sys.stdin.read(1)
        except (OSError, ValueError):
            return
        if not b:
            return
        if 0x40 <= ord(b) <= 0x7E:
            return
