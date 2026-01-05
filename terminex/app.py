"""terminex app controller — tabs, live loop, keyboard dispatch."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, replace

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from .config import Config, load as load_config
from .display import build_table, state_panel
from .help import render_filter_bar, render_help_panel
from .keyboard import KeyboardListener
from .statusbar import render_status_bar
from .providers.base import Provider, ProviderError
from .providers.commodities_stooq import CommoditiesStooq
from .providers.crypto_coincap import CryptoCoinCap
from .providers.fx_erapi import FxERApi
from .providers.watchlist_agg import WatchlistAggregator
from .quote import AssetClass, Quote, Snapshot
from .series import SeriesStore
from .watchlist import Pin, load as load_watchlist, save as save_watchlist

SORT_KEYS = ["default", "24h", "price"]


def _sort_quotes(
    quotes: list[Quote], key: str, desc: bool
) -> list[Quote]:
    if key == "default":
        return list(quotes)
    inf = float("inf")
    if key == "24h":
        keyfn = lambda q: (  # noqa: E731
            q.change_24h_pct if q.change_24h_pct is not None else -inf
        )
    elif key == "price":
        keyfn = lambda q: q.price  # noqa: E731
    else:
        return list(quotes)
    return sorted(quotes, key=keyfn, reverse=desc)


def _filter_quotes(quotes: list[Quote], query: str) -> list[Quote]:
    if not query:
        return list(quotes)
    q = query.lower()
    return [
        quote for quote in quotes
        if q in quote.symbol.lower() or q in quote.name.lower()
    ]


def _format_sort_indicator(key: str, desc: bool) -> str:
    if key == "default":
        return ""
    arrow = "↓" if desc else "↑"
    return f"sort: {key} {arrow}"

TAB_KEYS = {"1": "fx", "2": "crypto", "3": "commodity", "4": "watchlist"}
TAB_ORDER = ["fx", "crypto", "commodity", "watchlist"]
TAB_LABELS = {
    "fx": "FX",
    "crypto": "Crypto",
    "commodity": "Cmdty",
    "watchlist": "Watch",
}
SOURCE_TABS: list[str] = ["fx", "crypto", "commodity"]
# Map tab name → AssetClass for watchlist pins
TAB_TO_ASSET_CLASS = {"fx": "fx", "crypto": "crypto", "commodity": "commodity"}


@dataclass
class TabState:
    provider: Provider
    last_snapshot: Snapshot | None = None
    previous_rates: dict[str, float] | None = None
    last_error: str | None = None
    last_fetch_attempt: float = 0.0
    selected_index: int = 0
    sort_key: str = "default"
    sort_desc: bool = True
    filter_query: str = ""

    def clamp_selection(self, visible_count: int | None = None) -> None:
        if visible_count is None:
            if self.last_snapshot is None:
                self.selected_index = 0
                return
            visible_count = len(self.last_snapshot.quotes)
        if visible_count <= 0:
            self.selected_index = 0
        else:
            self.selected_index = max(
                0, min(self.selected_index, visible_count - 1)
            )


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
        self.watchlist = load_watchlist()
        self.tabs["watchlist"] = TabState(
            WatchlistAggregator(self.watchlist, self._lookup_pinned_quote)
        )
        self.console = Console()
        self.should_quit = False
        self._toast: tuple[str, float] | None = None  # (message, expires_at)
        self.show_help = False
        self.input_mode: str = "normal"  # "normal" | "filter" | "converter"
        self.filter_buffer: str = ""
        self.converter_buffer: str = ""
        self.converter_history: list[str] = []
        self.converter_error: str | None = None
        self.series = SeriesStore()
        self.show_sparklines = False
        self._last_age: str = ""

    def _lookup_pinned_quote(
        self, asset_class: AssetClass, symbol: str
    ) -> Quote | None:
        snap = self.tabs[asset_class].last_snapshot
        if snap is None:
            return None
        for q in snap.quotes:
            if q.symbol == symbol:
                return q
        return None

    def _set_toast(self, message: str, seconds: float = 2.0) -> None:
        self._toast = (message, time.monotonic() + seconds)

    def _age_changed(self) -> bool:
        from .statusbar import format_age
        state = self.tabs[self.active_tab]
        fetched_at = (
            state.last_snapshot.fetched_at
            if state.last_snapshot is not None
            else None
        )
        current = format_age(fetched_at)
        if current != self._last_age:
            self._last_age = current
            return True
        return False

    def _active_toast(self) -> str | None:
        if self._toast is None:
            return None
        message, expires = self._toast
        if time.monotonic() >= expires:
            self._toast = None
            return None
        return message

    def _current_row(self) -> tuple[str, str] | None:
        """Return (asset_class, symbol) for the currently-selected row, or None."""
        state = self.tabs[self.active_tab]
        if state.last_snapshot is None:
            return None
        # apply filter + sort to match what's on screen
        filtered = _filter_quotes(
            state.last_snapshot.quotes, state.filter_query
        )
        sorted_quotes = _sort_quotes(
            filtered, state.sort_key, state.sort_desc
        )
        if not sorted_quotes:
            return None
        idx = max(0, min(state.selected_index, len(sorted_quotes) - 1))
        q = sorted_quotes[idx]
        if self.active_tab == "watchlist":
            ac = q.meta.get("source_tab")
            return (ac, q.symbol) if ac else None
        ac = TAB_TO_ASSET_CLASS.get(self.active_tab)
        return (ac, q.symbol) if ac else None

    def _toggle_pin(self) -> None:
        row = self._current_row()
        if row is None:
            return
        ac, sym = row
        now_pinned = self.watchlist.toggle(ac, sym)
        save_watchlist(self.watchlist)
        if now_pinned:
            self._set_toast(f"pinned {sym}")
        else:
            self._set_toast(f"unpinned {sym}")

    # ---- fetch / tab machinery ----

    def _refresh(self, tab_name: str) -> None:
        # Watchlist reads from source tabs' already-fetched data.
        # Ensure each source tab has at least attempted a fetch.
        if tab_name == "watchlist":
            for src in SOURCE_TABS:
                src_state = self.tabs[src]
                if src_state.last_snapshot is None and src_state.last_error is None:
                    self._refresh(src)
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
        # Append prices to per-symbol series (source tabs only — the
        # watchlist is a derived view and would double-count).
        if tab_name in SOURCE_TABS:
            self.series.extend_from_snapshot(tab_name, snap.quotes)
        # A source-tab refresh invalidates any existing watchlist snapshot.
        if (
            tab_name in SOURCE_TABS
            and "watchlist" in self.tabs
            and self.tabs["watchlist"].last_snapshot is not None
        ):
            self.tabs["watchlist"].last_fetch_attempt = 0.0

    def _needs_refresh(self, tab_name: str) -> bool:
        state = self.tabs[tab_name]
        if state.last_snapshot is None and state.last_error is None:
            return True
        return (time.monotonic() - state.last_fetch_attempt) >= self.interval

    # ---- rendering ----

    def _header(self) -> Text:
        from . import theme
        header = Text()
        for i, tab in enumerate(TAB_ORDER, start=1):
            if tab == self.active_tab:
                header.append(f" [{i}] ", style=theme.MUTED)
                header.append(
                    TAB_LABELS[tab], style=f"bold {theme.ACCENT} underline"
                )
            else:
                header.append(f" [{i}] ", style=theme.MUTED)
                header.append(TAB_LABELS[tab], style=theme.MUTED)
            header.append("   ", style="")
        return header

    def _render(self):
        state = self.tabs[self.active_tab]
        header = self._header()

        is_watchlist_tab = self.active_tab == "watchlist"
        empty_watchlist = is_watchlist_tab and not self.watchlist.pins

        if empty_watchlist:
            body = state_panel(
                "No symbols pinned.\n"
                "Navigate to FX, Crypto, or Commodities, highlight a row "
                "with j/k, and press w to pin.",
                title="Watch",
                variant="neutral",
            )
        elif state.last_snapshot is not None:
            filtered = _filter_quotes(
                state.last_snapshot.quotes, state.filter_query
            )
            state.clamp_selection(visible_count=len(filtered))
            if state.filter_query and not filtered:
                body = state_panel(
                    f"no matches for '{state.filter_query}'",
                    variant="warn",
                )
                sorted_quotes = None
            else:
                sorted_quotes = _sort_quotes(
                    filtered, state.sort_key, state.sort_desc
                )
                display_snap = replace(
                    state.last_snapshot, quotes=sorted_quotes
                )
                sort_indicator = _format_sort_indicator(
                    state.sort_key, state.sort_desc
                )
                pinned_set = {
                    (p.asset_class, p.symbol) for p in self.watchlist.pins
                }
                current_tab_asset = TAB_TO_ASSET_CLASS.get(self.active_tab)
                body = build_table(
                    display_snap,
                    state.previous_rates,
                    selected_index=state.selected_index,
                    sort_indicator=sort_indicator,
                    pinned_set=pinned_set,
                    current_tab_asset=current_tab_asset,
                    is_watchlist=is_watchlist_tab,
                    series_getter=(
                        self.series.get if self.show_sparklines else None
                    ),
                )
        elif state.last_error is not None:
            body = state_panel(
                state.last_error,
                title=f"{TAB_LABELS[self.active_tab]} fetch error",
                variant="error",
            )
        else:
            body = state_panel("loading…", variant="neutral")

        if self.show_help:
            return Group(header, Text(""), render_help_panel())

        status_line = self._build_status_line(state)
        return Group(header, Text(""), body, Text(""), status_line)

    def _build_status_line(self, state: TabState):
        from . import theme
        # Single status line at the bottom. Priority (highest first):
        # filter input > toast > stale error > normal status bar.
        if self.input_mode == "filter":
            return render_filter_bar(self.filter_buffer)
        toast = self._active_toast()
        if toast:
            return Text(f" {toast}", style=f"bold {theme.WARN}")
        if (
            state.last_error is not None
            and state.last_snapshot is not None
        ):
            return Text(
                f" stale — {state.last_error}", style=theme.ERROR
            )
        total = (
            len(state.last_snapshot.quotes)
            if state.last_snapshot is not None
            else 0
        )
        visible = total
        if total and state.filter_query:
            from .app import _filter_quotes as _fq
            visible = len(_fq(state.last_snapshot.quotes, state.filter_query))
        return render_status_bar(
            tab_label=TAB_LABELS[self.active_tab],
            visible_count=visible,
            total_count=total,
            sort_key=state.sort_key,
            sort_desc=state.sort_desc,
            filter_query=state.filter_query,
            fetched_at=(
                state.last_snapshot.fetched_at
                if state.last_snapshot is not None
                else None
            ),
        )

    # ---- keyboard ----

    def _handle_key(self, ch: str) -> bool:
        """Return True if the display should re-render immediately."""
        if self.input_mode == "filter":
            return self._handle_filter_key(ch)
        if self.input_mode == "converter":
            return self._handle_converter_key(ch)
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
        state = self.tabs[self.active_tab]
        if ch == "j":
            state.selected_index += 1
            state.clamp_selection()
            return True
        if ch == "k":
            state.selected_index -= 1
            state.clamp_selection()
            return True
        if ch == "g":
            state.selected_index = 0
            return True
        if ch == "G":
            if state.last_snapshot is not None:
                state.selected_index = len(state.last_snapshot.quotes) - 1
                state.clamp_selection()
            return True
        if ch == "s":
            i = SORT_KEYS.index(state.sort_key)
            state.sort_key = SORT_KEYS[(i + 1) % len(SORT_KEYS)]
            state.selected_index = 0
            return True
        if ch == "S":
            state.sort_desc = not state.sort_desc
            return True
        if ch in ("w", "W"):
            self._toggle_pin()
            # Force a watchlist refresh so the next render reflects the change.
            if self.tabs["watchlist"].last_snapshot is not None:
                self.tabs["watchlist"].last_fetch_attempt = 0.0
            return True
        if ch == "?":
            self.show_help = not self.show_help
            return True
        if ch == "~":
            self.show_sparklines = not self.show_sparklines
            return True
        if ch == "/":
            self.input_mode = "filter"
            self.filter_buffer = state.filter_query
            return True
        if ch == "c":
            self.input_mode = "converter"
            self.converter_buffer = ""
            self.converter_error = None
            return True
        if ch == "\x1b":  # Esc clears any active filter
            if state.filter_query:
                state.filter_query = ""
                state.selected_index = 0
                return True
        return False

    def _handle_converter_key(self, ch: str) -> bool:
        from .converter import (
            ParseError,
            ResolveError,
            build_usd_lookup,
            evaluate,
            format_result,
        )
        if ch == "\x1b":  # Esc exits
            self.input_mode = "normal"
            self.converter_buffer = ""
            self.converter_error = None
            return True
        if ch == "\x03":  # Ctrl-C quits
            self.should_quit = True
            return True
        if ch in ("\r", "\n"):  # Enter evaluates
            expr = self.converter_buffer.strip()
            if not expr:
                return False
            lookup = build_usd_lookup(
                {
                    "fx": self.tabs["fx"].last_snapshot,
                    "crypto": self.tabs["crypto"].last_snapshot,
                    "commodity": self.tabs["commodity"].last_snapshot,
                }
            )
            try:
                result = evaluate(expr, lookup)
            except (ParseError, ResolveError) as exc:
                self.converter_error = str(exc)
                return True
            self.converter_error = None
            self.converter_history.insert(0, format_result(result))
            self.converter_history = self.converter_history[:5]
            self.converter_buffer = ""
            return True
        if ch in ("\x7f", "\x08"):  # backspace
            self.converter_buffer = self.converter_buffer[:-1]
            self.converter_error = None
            return True
        if ch.isprintable() and len(ch) == 1:
            self.converter_buffer += ch
            self.converter_error = None
            return True
        return False

    def _handle_filter_key(self, ch: str) -> bool:
        state = self.tabs[self.active_tab]
        if ch == "\x1b":  # Esc cancels, clears filter
            self.filter_buffer = ""
            state.filter_query = ""
            state.selected_index = 0
            self.input_mode = "normal"
            return True
        if ch in ("\r", "\n"):  # Enter commits (keeps filter, exits mode)
            state.filter_query = self.filter_buffer
            self.input_mode = "normal"
            return True
        if ch in ("\x7f", "\x08"):  # backspace/DEL
            self.filter_buffer = self.filter_buffer[:-1]
            state.filter_query = self.filter_buffer
            state.selected_index = 0
            return True
        if ch == "\x03":  # Ctrl-C while filtering → quit
            self.should_quit = True
            return True
        if ch.isprintable() and len(ch) == 1:
            self.filter_buffer += ch
            state.filter_query = self.filter_buffer
            state.selected_index = 0
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
                    # toast expiration forces a redraw
                    if self._toast is not None and self._active_toast() is None:
                        dirty = True
                    # refresh-age label changes force a redraw
                    if not dirty and self._age_changed():
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
