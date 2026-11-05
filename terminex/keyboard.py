"""Non-blocking single-keystroke reader for POSIX terminals."""

from __future__ import annotations

import codecs
import os
import queue
import select
import sys
import termios
import threading
import tty
from typing import Iterator

# How long to wait for the rest of an escape sequence when a read ends
# mid-sequence. Terminals send ``\x1b[A``-style sequences in one write,
# so this only matters on slow links (ssh) and for telling a bare Esc
# keypress apart from the start of a sequence.
_ESC_FOLLOWUP_TIMEOUT = 0.05

# How often the reader thread wakes to check for stop().
_POLL_INTERVAL = 0.1

# Synthetic key tokens emitted for CSI sequences we care about.
KEY_UP = "<up>"
KEY_DOWN = "<down>"
KEY_LEFT = "<left>"
KEY_RIGHT = "<right>"

# Final byte → synthetic token for simple (no-parameter) CSI/SS3 sequences.
_CSI_MAP: dict[str, str] = {
    "A": KEY_UP,
    "B": KEY_DOWN,
    "C": KEY_RIGHT,
    "D": KEY_LEFT,
}


def split_keys(text: str) -> list[str]:
    """Split decoded terminal input into key tokens.

    Arrow keys (``ESC [ A`` or ``ESC O A``) become ``<up>``-style tokens.
    Other CSI/SS3 sequences are dropped so they don't leak as stray
    keypresses. A bare ESC (or ESC followed by a non-sequence character)
    is emitted as ``"\\x1b"``.
    """
    keys: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != "\x1b" or i + 1 >= n or text[i + 1] not in "[O":
            keys.append(ch)
            i += 1
            continue
        # ESC [ … or ESC O …: parameter/intermediate bytes (0x20-0x3F)
        # up to a final byte (0x40-0x7E).
        j = i + 2
        while j < n and 0x20 <= ord(text[j]) <= 0x3F:
            j += 1
        if j >= n:
            # Unterminated sequence: drop what we have.
            break
        final = text[j]
        params = text[i + 2:j]
        if not params and final in _CSI_MAP:
            keys.append(_CSI_MAP[final])
        i = j + 1
    return keys


def _incomplete_sequence(text: str) -> bool:
    """True if ``text`` ends partway through an escape sequence."""
    esc = text.rfind("\x1b")
    if esc == -1:
        return False
    tail = text[esc + 1:]
    if tail == "":
        return True
    if tail[0] not in "[O":
        return False
    return all(0x20 <= ord(c) <= 0x3F for c in tail[1:])


class KeyboardListener:
    """Background thread that reads single keypresses from a terminal.

    Reads raw bytes with ``os.read`` rather than ``sys.stdin.read``:
    Python's buffered stdin pulls a whole ``\\x1b[A`` burst into its own
    buffer, so a ``select()`` on the file descriptor sees nothing left
    and the sequence used to leak out as ESC, ``[``, ``A``.
    """

    def __init__(self, fd: int | None = None) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._old_attrs: list | None = None
        self._fd: int | None = None
        self._requested_fd = fd

    def start(self) -> None:
        fd = self._requested_fd
        if fd is None:
            if not sys.stdin.isatty():
                return
            fd = sys.stdin.fileno()
        elif not os.isatty(fd):
            return
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
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)
            except termios.error:
                pass
            self._old_attrs = None
        if self._thread is not None:
            self._thread.join(timeout=2 * _POLL_INTERVAL)
            self._thread = None

    def _read(self, fd: int) -> bytes:
        try:
            return os.read(fd, 1024)
        except OSError:
            return b""

    def _run(self) -> None:
        fd = self._fd
        if fd is None:
            return
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while not self._stop.is_set():
            if not _has_pending(fd, _POLL_INTERVAL):
                continue
            data = self._read(fd)
            if not data:
                return
            text = decoder.decode(data)
            # A read can end mid-sequence (or on a bare Esc). Give the
            # rest a brief window to arrive before deciding.
            while _incomplete_sequence(text) and _has_pending(
                fd, _ESC_FOLLOWUP_TIMEOUT
            ):
                more = self._read(fd)
                if not more:
                    break
                text += decoder.decode(more)
            for key in split_keys(text):
                self._queue.put(key)

    def drain(self) -> Iterator[str]:
        """Yield all pending keypresses without blocking."""
        while True:
            try:
                yield self._queue.get_nowait()
            except queue.Empty:
                return


def _has_pending(fd: int, timeout: float) -> bool:
    try:
        r, _, _ = select.select([fd], [], [], timeout)
    except (OSError, ValueError):
        return False
    return bool(r)
