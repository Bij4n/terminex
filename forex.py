#!/usr/bin/env python3
"""terminex — live FX rates for the 25 most-traded currencies."""

from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from terminex.display import build_table
from terminex.fetcher import FetchError, RateSnapshot, fetch_rates


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="terminex",
        description="Live FX rates for the top 25 most-traded currencies.",
    )
    parser.add_argument(
        "--base",
        default="USD",
        help="base currency code (default: USD)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="refresh interval in seconds (default: 10)",
    )
    return parser.parse_args(argv)


def _error_panel(message: str) -> Panel:
    return Panel(
        Text(message, style="red"),
        title="terminex — fetch error",
        border_style="red",
    )


def run(base: str, interval: float) -> int:
    console = Console()
    previous: dict[str, float] | None = None
    last_snapshot: RateSnapshot | None = None

    try:
        snapshot = fetch_rates(base)
    except FetchError as exc:
        console.print(_error_panel(f"initial fetch failed: {exc}"))
        return 1

    with Live(
        build_table(snapshot, previous=None),
        console=console,
        refresh_per_second=4,
        screen=False,
    ) as live:
        previous = dict(snapshot.rates)
        last_snapshot = snapshot

        while True:
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                break

            try:
                snapshot = fetch_rates(base)
            except FetchError as exc:
                if last_snapshot is not None:
                    stale = build_table(last_snapshot, previous=previous)
                    live.update(stale)
                console.print(_error_panel(f"refresh failed: {exc}"))
                continue

            live.update(build_table(snapshot, previous=previous))
            previous = dict(snapshot.rates)
            last_snapshot = snapshot

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args.base, args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
