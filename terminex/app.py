"""terminex app controller — tabs, live loop, keyboard dispatch."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .config import Config, load as load_config
from .display import build_table
from .keyboard import KeyboardListener
from .providers.base import Provider, ProviderError
from .providers.commodities_stooq import CommoditiesStooq
from .providers.crypto_coincap import CryptoCoinCap
from .providers.fx_erapi import FxERApi
from .quote import Snapshot

TAB_KEYS = {"1": "fx", "2": "crypto", "3": "commodity"}
TAB_ORDER = ["fx", "crypto", "commodity"]
TAB_LABELS = {"fx": "FX", "crypto": "Crypto", "commodity": "Commodities"}


@dataclass
class TabState:
    provider: Provider
    last_snapshot: Snapshot | None = None
    previous_rates: dict[str, float] | None = None
    last_error: str | None = None
    last_fetch_attempt: float = 0.0
    selected_index: int = 0

    def clamp_selection(self) -> None:
        if self.last_snapshot is None:
            self.selected_index = 0
            return
        n = len(self.last_snapshot.quotes)
        if n == 0:
            self.selected_index = 0
        else:
            self.selected_index = max(0, min(self.selected_index, n - 1))


class App:
    def __init__(self, config: Config, interval: float) -> None:
        self.config = config
        self.interval = interval
        self.active_tab = (
            config.active_tab if config.active_tab in TAB_ORDER else "fx"
        )
        self.tabs: dict[str, TabState] = {
            "fx": TabState(FxERApi(base=config.base_currency)),
            "crypto": TabState(
                CryptoCoinCap(api_key=config.coincap_api_key or None)
            ),
            "commodity": TabState(CommoditiesStooq()),
        }
        self.console = Console()
        self.should_quit = False

    # ---- fetch / tab machinery ----

    def _refresh(self, tab_name: str) -> None:
        state = self.tabs[tab_name]
        state.last_fetch_attempt = time.monotonic()
        try:
            snap = state.provider.fetch()
        except ProviderError as exc:
            state.last_error = str(exc)
            return
        # rotate previous → current
        if state.last_snapshot is not None:
            state.previous_rates = state.last_snapshot.as_rate_map()
        state.last_snapshot = snap
        state.last_error = None

    def _needs_refresh(self, tab_name: str) -> bool:
        state = self.tabs[tab_name]
        if state.last_snapshot is None and state.last_error is None:
            return True
        return (time.monotonic() - state.last_fetch_attempt) >= self.interval

    # ---- rendering ----

    def _header(self) -> Text:
        parts: list[tuple[str, str]] = []
        for i, tab in enumerate(TAB_ORDER, start=1):
            label = f" {i} {TAB_LABELS[tab]} "
            style = "black on cyan" if tab == self.active_tab else "cyan"
            parts.append((label, style))
            parts.append(("  ", ""))
        header = Text()
        for text, style in parts:
            header.append(text, style=style)
        header.append(
            f"  ·  refresh every {self.interval:g}s", style="dim"
        )
        return header

    def _render(self):
        state = self.tabs[self.active_tab]
        header = self._header()

        if state.last_snapshot is not None:
            body = build_table(state.last_snapshot, state.previous_rates)
        elif state.last_error is not None:
            body = Panel(
                Text(state.last_error, style="red"),
                title=f"terminex — {TAB_LABELS[self.active_tab]} fetch error",
                border_style="red",
            )
        else:
            body = Panel(
                Text("loading...", style="dim"),
                border_style="dim",
            )

        if state.last_error is not None and state.last_snapshot is not None:
            err = Text(
                f"stale — last refresh failed: {state.last_error}",
                style="red",
            )
            return Group(header, Text(""), body, Text(""), err)
        return Group(header, Text(""), body)

    # ---- keyboard ----

    def _handle_key(self, ch: str) -> bool:
        """Return True if the display should re-render immediately."""
        if ch in ("q", "Q", "\x03", "\x04"):  # q, Q, Ctrl-C, Ctrl-D
            self.should_quit = True
            return True
        if ch in TAB_KEYS:
            new_tab = TAB_KEYS[ch]
            if new_tab != self.active_tab:
                self.active_tab = new_tab
                # trigger an immediate fetch if we've never loaded this tab
                if self.tabs[new_tab].last_snapshot is None:
                    self._refresh(new_tab)
                return True
        if ch in ("r", "R"):
            self._refresh(self.active_tab)
            return True
        return False

    # ---- main loop ----

    def run(self) -> int:
        # eager first fetch for the active tab
        self._refresh(self.active_tab)

        kb = KeyboardListener()
        kb.start()
        try:
            with Live(
                self._render(),
                console=self.console,
                refresh_per_second=8,
                screen=False,
            ) as live:
                while not self.should_quit:
                    time.sleep(0.1)
                    dirty = False
                    for ch in kb.drain():
                        if self._handle_key(ch):
                            dirty = True
                        if self.should_quit:
                            break
                    if self.should_quit:
                        break
                    if self._needs_refresh(self.active_tab):
                        self._refresh(self.active_tab)
                        dirty = True
                    if dirty:
                        live.update(self._render())
        except KeyboardInterrupt:
            pass
        finally:
            kb.stop()
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="terminex",
        description=(
            "Live multi-asset dashboard: FX (top 25), crypto (top 25 by "
            "mcap), and commodity futures."
        ),
    )
    parser.add_argument("--base", default=None, help="FX base currency")
    parser.add_argument(
        "--interval", type=float, default=None, help="refresh interval (s)"
    )
    parser.add_argument(
        "--tab",
        choices=TAB_ORDER,
        default=None,
        help="tab to launch on (fx/crypto/commodity)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config()
    if args.base:
        config = Config(
            base_currency=args.base.upper(),
            refresh_interval=config.refresh_interval,
            active_tab=config.active_tab,
            coincap_api_key=config.coincap_api_key,
        )
    if args.tab:
        config = Config(
            base_currency=config.base_currency,
            refresh_interval=config.refresh_interval,
            active_tab=args.tab,
            coincap_api_key=config.coincap_api_key,
        )
    interval = args.interval if args.interval is not None else config.refresh_interval
    app = App(config=config, interval=interval)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
