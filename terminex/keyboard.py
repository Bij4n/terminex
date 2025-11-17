"""Non-blocking single-keystroke reader for POSIX terminals."""

from __future__ import annotations

import queue
import sys
import termios
import threading
import tty
from typing import Iterator


class KeyboardListener:
    """Background thread that reads single keypresses from stdin."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._old_attrs: list | None = None
        self._fd: int | None = None

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        self._fd = sys.stdin.fileno()
        self._old_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._old_attrs is not None and self._fd is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)
            self._old_attrs = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ch = sys.stdin.read(1)
            except (OSError, ValueError):
                return
            if not ch:
                return
            self._queue.put(ch)

    def drain(self) -> Iterator[str]:
        """Yield all pending keypresses without blocking."""
        while True:
            try:
                yield self._queue.get_nowait()
            except queue.Empty:
                return
