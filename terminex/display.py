"""Render a Snapshot as a rich Table, asset-class aware."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from rich.console import Console
from rich.measure import Measurement
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import theme

Variant = Literal["neutral", "warn", "error"]

_VARIANT_BORDER = {
    "neutral": theme.PANEL_BORDER_NEUTRAL,
    "warn": theme.PANEL_BORDER_WARN,
    "error": theme.PANEL_BORDER_ERROR,
}

_VARIANT_TEXT_STYLE = {
    "neutral": theme.DIM_TEXT,
    "warn": theme.WARN,
    "error": theme.ERROR,
}


def state_panel(
    message: str, *, title: str | None = None, variant: Variant = "neutral"
) -> Panel:
    return Panel(
        Text(message, style=_VARIANT_TEXT_STYLE[variant]),
        title=title,
        title_align="left",
        border_style=_VARIANT_BORDER[variant],
        padding=(1, 2),
    )
from .quote import Snapshot
from .sparkline import render as render_sparkline

SeriesGetter = Callable[[str, str], list]

TREND_WIDTH = 20

_ASSET_TITLES = {
    "fx": "top 25 FX rates",
    "crypto": "top cryptocurrencies by market cap",
    "commodity": "commodity futures",
}

_ASSET_PRICE_COLS = {
    "fx": "Rate (per 1 {ccy})",
    "crypto": "Price ({ccy})",
    "commodity": "Last ({ccy})",
}

_ASSET_SYMBOL_COLS = {
    "fx": "Code",
    "crypto": "Symbol",
    "commodity": "Symbol",
}

_ASSET_NAME_COLS = {
    "fx": "Currency",
    "crypto": "Name",
    "commodity": "Name",
}


def _format_price(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.5f}"


# Changes that would print as "+0.00%" / "-0.00%" are shown as no change.
_ZERO_PCT = 0.005


def _format_pct(value: float | None) -> Text:
    if value is None:
        return Text("·", style=theme.NEUTRAL)
    if abs(value) < _ZERO_PCT:
        return Text("·", style=theme.NEUTRAL)
    arrow = "▲" if value > 0 else "▼"
    return Text(f"{arrow} {value:+.2f}%", style=theme.pct_style(value))


def _delta_cell(current: float, previous: float | None) -> Text:
    if previous is None or previous == 0:
        return Text("·", style=theme.NEUTRAL)
    diff = current - previous
    pct = (diff / previous) * 100.0
    if abs(pct) < _ZERO_PCT:
        return Text("·", style=theme.NEUTRAL)
    arrow = "▲" if diff > 0 else "▼"
    return Text(f"{arrow} {pct:+.2f}%", style=theme.pct_style(diff))


def _trend_cell(q, asset: str, series_getter: SeriesGetter, is_watchlist: bool) -> Text:
    """Provider history (7 days) when available, else the live series."""
    history = q.meta.get("history")
    if history:
        return render_sparkline(
            history, width=TREND_WIDTH, change_pct=q.meta.get("change_7d_pct")
        )
    series = series_getter(asset, q.symbol)
    if is_watchlist and asset == "fx":
        # Watchlist shows USD per unit; the FX tab's series is per-base rates.
        series = [1.0 / v for v in series if v > 0]
    return render_sparkline(series, width=TREND_WIDTH)


# Columns that may be dropped to fit a narrow terminal, least useful first.
# Pointer, star, symbol, price and 24h % are never dropped.
_DROP_ORDER: tuple[str, ...] = ("delta", "rank", "name", "trend")


def build_table(
    snapshot: Snapshot,
    previous: dict[str, float] | None = None,
    selected_index: int | None = None,
    sort_indicator: str = "",
    pinned_set: set[tuple[str, str]] | None = None,
    current_tab_asset: str | None = None,
    is_watchlist: bool = False,
    series_getter: SeriesGetter | None = None,
    hidden: frozenset[str] = frozenset(),
    rows: slice | None = None,
) -> Table:
    """Render ``snapshot`` as a table.

    ``hidden`` names optional columns to leave out (see ``_DROP_ORDER``).
    ``rows`` limits the table to a window of quotes; numbering and
    ``selected_index`` stay absolute, and the caption says which rows show.
    """
    asset = snapshot.asset_class
    ccy = snapshot.quote_ccy
    pinned_set = pinned_set or set()
    total = len(snapshot.quotes)
    window = range(total)[rows] if rows is not None else range(total)

    if is_watchlist:
        title = f"terminex  ·  watchlist (quote {ccy})"
    else:
        title = f"terminex  ·  {_ASSET_TITLES[asset]} (quote {ccy})"

    caption_parts: list[str] = []
    if len(window) < total and len(window) > 0:
        caption_parts.append(f"rows {window[0] + 1}–{window[-1] + 1} of {total}")
    if snapshot.provider_name and not is_watchlist:
        caption_parts.append(f"via {snapshot.provider_name}")

    table = Table(
        title=title,
        caption="  ·  ".join(caption_parts) if caption_parts else None,
        header_style=theme.HEADER_STYLE,
        title_style=theme.TITLE_STYLE,
        caption_style=theme.CAPTION_STYLE,
        expand=False,
    )
    show_rank = "rank" not in hidden
    show_name = "name" not in hidden
    show_trend = series_getter is not None and "trend" not in hidden
    show_delta = "delta" not in hidden
    show_unit = asset == "commodity" and not is_watchlist

    # Every column is no_wrap so a row is always one line: the viewport
    # math in the app counts on it. Names truncate with an ellipsis.
    table.add_column(" ", justify="left", width=1)  # selected-row pointer
    table.add_column("★", justify="center", style=theme.STAR, width=1)
    if show_rank:
        table.add_column("#", justify="right", style=theme.MUTED, width=3, no_wrap=True)
    if is_watchlist:
        table.add_column("Asset", style=theme.MUTED, no_wrap=True)
        table.add_column("Symbol", style="bold", no_wrap=True)
        if show_name:
            table.add_column("Name", no_wrap=True, overflow="ellipsis")
        table.add_column(f"Price ({ccy})", justify="right", no_wrap=True)
    else:
        table.add_column(_ASSET_SYMBOL_COLS[asset], style="bold", no_wrap=True)
        if show_name:
            table.add_column(_ASSET_NAME_COLS[asset], no_wrap=True, overflow="ellipsis")
        table.add_column(
            _ASSET_PRICE_COLS[asset].format(ccy=ccy), justify="right", no_wrap=True
        )
        if show_unit:
            table.add_column("Unit", style=theme.MUTED, no_wrap=True)
    table.add_column("24h %", justify="right", no_wrap=True)
    if show_trend:
        has_history = any(q.meta.get("history") for q in snapshot.quotes)
        if is_watchlist:
            trend_title = "Trend"
        elif has_history:
            trend_title = "Trend (7d)"
        else:
            trend_title = "Trend (live)"
        table.add_column(trend_title, justify="left", no_wrap=True)
    if show_delta:
        table.add_column("Δ since last", justify="right", no_wrap=True)

    for i in window:
        q = snapshot.quotes[i]
        row_asset = q.meta.get("source_tab") if is_watchlist else current_tab_asset
        is_pinned = bool(row_asset) and (row_asset, q.symbol) in pinned_set
        star = "★" if is_pinned else ""

        is_pending = bool(q.meta.get("pending"))
        if is_pending:
            price_text = Text("loading…", style=theme.MUTED)
            pct_text = Text("·", style=theme.NEUTRAL)
            delta_text = Text("·", style=theme.NEUTRAL)
        elif (not is_watchlist) and asset == "fx" and q.symbol == ccy:
            price_text = Text("1.0000", style=theme.BASE)
            pct_text = Text("·", style=theme.NEUTRAL)
            delta_text = Text("·", style=theme.NEUTRAL)
        else:
            price_text = Text(_format_price(q.price))
            pct_text = _format_pct(q.change_24h_pct)
            prev_val = previous.get(q.symbol) if previous else None
            delta_text = _delta_cell(q.price, prev_val)

        is_selected = selected_index == i
        pointer = (
            Text("▍", style=f"bold {theme.POINTER}") if is_selected else ""
        )
        row: list = [pointer, star]
        if show_rank:
            row.append(str(i + 1))
        if is_watchlist:
            row.append(q.meta.get("source_label", "?"))
        row.append(q.symbol)
        if show_name:
            row.append(q.name)
        row.append(price_text)
        if show_unit:
            unit = q.meta.get("unit")
            row.append(f"/{unit}" if unit else "")
        row.append(pct_text)
        if show_trend:
            row.append(_trend_cell(q, row_asset or asset, series_getter, is_watchlist))
        if show_delta:
            row.append(delta_text)
        row_style = theme.HIGHLIGHT_ROW_STYLE if is_selected else None
        table.add_row(*row, style=row_style)

    return table


def fit_hidden(build: Callable[[frozenset[str]], Table], console: Console) -> frozenset[str]:
    """Fewest optional columns to drop so the table fits ``console.width``."""
    # Measure the natural width: Measurement clamps to options.max_width.
    unbounded = console.options.update_width(10_000)
    hidden: frozenset[str] = frozenset()
    for col in (None, *_DROP_ORDER):
        if col is not None:
            hidden = hidden | {col}
        width = Measurement.get(console, unbounded, build(hidden)).maximum
        if width <= console.width:
            break
    return hidden


def fit_table(build: Callable[[frozenset[str]], Table], console: Console) -> Table:
    """Build the widest table that fits the console (see ``fit_hidden``)."""
    return build(fit_hidden(build, console))


def scroll_offset(selected: int, offset: int, visible: int, total: int) -> int:
    """First row to show so ``selected`` stays inside a window of ``visible``."""
    if visible >= total:
        return 0
    offset = min(max(offset, selected - visible + 1), selected)
    return max(0, min(offset, total - visible))
