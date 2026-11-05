"""Persistent user watchlist of pinned symbols across asset classes."""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .quote import AssetClass


@dataclass(frozen=True)
class Pin:
    asset_class: AssetClass
    symbol: str


@dataclass
class Watchlist:
    pins: list[Pin] = field(default_factory=list)

    def contains(self, asset_class: AssetClass, symbol: str) -> bool:
        return any(
            p.asset_class == asset_class and p.symbol == symbol
            for p in self.pins
        )

    def add(self, pin: Pin) -> bool:
        if self.contains(pin.asset_class, pin.symbol):
            return False
        self.pins.append(pin)
        return True

    def remove(self, asset_class: AssetClass, symbol: str) -> bool:
        for i, p in enumerate(self.pins):
            if p.asset_class == asset_class and p.symbol == symbol:
                del self.pins[i]
                return True
        return False

    def toggle(self, asset_class: AssetClass, symbol: str) -> bool:
        """Return True if the pin now exists, False if it was removed."""
        if self.contains(asset_class, symbol):
            self.remove(asset_class, symbol)
            return False
        self.pins.append(Pin(asset_class=asset_class, symbol=symbol))
        return True


def watchlist_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "terminex" / "watchlist.toml"


def load(path: Path | None = None) -> Watchlist:
    p = path or watchlist_path()
    if not p.exists():
        return Watchlist()
    try:
        with p.open("rb") as f:
            data = tomllib.load(f)
    except OSError as exc:
        print(f"terminex: could not read watchlist at {p}: {exc}", file=sys.stderr)
        return Watchlist()
    except tomllib.TOMLDecodeError as exc:
        # Keep the damaged file: the next pin rewrites watchlist.toml.
        backup = p.with_name(p.name + ".bak")
        try:
            shutil.copyfile(p, backup)
            kept = f"saved a copy as {backup}"
        except OSError as copy_exc:
            kept = f"could not save a copy ({copy_exc})"
        print(
            f"terminex: ignoring malformed watchlist at {p}: {exc}; {kept}",
            file=sys.stderr,
        )
        return Watchlist()

    pins_raw = data.get("pins") or []
    pins: list[Pin] = []
    for entry in pins_raw:
        ac = entry.get("asset_class")
        sym = entry.get("symbol")
        if ac in ("fx", "crypto", "commodity") and isinstance(sym, str):
            pins.append(Pin(asset_class=ac, symbol=sym))
    return Watchlist(pins=pins)


def save(wl: Watchlist, path: Path | None = None) -> None:
    p = path or watchlist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# terminex watchlist — edited automatically on pin/unpin", ""]
    for pin in wl.pins:
        lines.append("[[pins]]")
        lines.append(f'asset_class = "{pin.asset_class}"')
        lines.append(f'symbol = "{pin.symbol}"')
        lines.append("")
    # Write a temp file and rename it, so a crash mid-write can't leave a
    # truncated watchlist behind.
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
