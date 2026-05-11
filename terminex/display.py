"""Render a Snapshot as a rich Table, asset-class aware."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

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


def _format_pct(value: float | None) -> Text:
    if value is None:
        return Text("·", style=theme.NEUTRAL)
    if abs(value) < 1e-4:
        return Text("·", style=theme.NEUTRAL)
    arrow = "▲" if value > 0 else "▼"
    return Text(f"{arrow} {value:+.2f}%", style=theme.pct_style(value))


def _delta_cell(current: float, previous: float | None) -> Text:
    if previous is None or previous == 0:
        return Text("·", style=theme.NEUTRAL)
    diff = current - previous
    pct = (diff / previous) * 100.0
    if abs(pct) < 1e-4:
        return Text("·", style=theme.NEUTRAL)
    arrow = "▲" if diff > 0 else "▼"
    return Text(f"{arrow} {pct:+.2f}%", style=theme.pct_style(diff))


def build_table(
    snapshot: Snapshot,
    previous: dict[str, float] | None = None,
    selected_index: int | None = None,
    sort_indicator: str = "",
    pinned_set: set[tuple[str, str]] | None = None,
    current_tab_asset: str | None = None,
    is_watchlist: bool = False,
    series_getter: SeriesGetter | None = None,
) -> Table:
    asset = snapshot.asset_class
    ccy = snapshot.quote_ccy
    pinned_set = pinned_set or set()

    if is_watchlist:
        title = f"terminex  ·  watchlist (quote {ccy})"
    else:
        title = f"terminex  ·  {_ASSET_TITLES[asset]} (quote {ccy})"

    caption_parts: list[str] = []
    if snapshot.provider_name and not is_watchlist:
        caption_parts.append(f"via {snapshot.provider_name}")
    has_unit_notes = any(q.meta.get("unit_note") for q in snapshot.quotes)
    if has_unit_notes:
        caption_parts.append("† exchange pts (not USD/unit)")

    table = Table(
        title=title,
        caption="  ·  ".join(caption_parts) if caption_parts else None,
        header_style=theme.HEADER_STYLE,
        title_style=theme.TITLE_STYLE,
        caption_style=theme.CAPTION_STYLE,
        expand=False,
    )
    table.add_column(" ", justify="left", width=1)  # selected-row pointer
    table.add_column("★", justify="center", style=theme.STAR, width=1)
    table.add_column("#", justify="right", style=theme.MUTED, width=3)
    if is_watchlist:
        table.add_column("Asset", style=theme.MUTED)
        table.add_column("Symbol", style="bold")
        table.add_column("Name")
        table.add_column(f"Price ({ccy})", justify="right")
    else:
        table.add_column(_ASSET_SYMBOL_COLS[asset], style="bold")
        table.add_column(_ASSET_NAME_COLS[asset])
        table.add_column(
            _ASSET_PRICE_COLS[asset].format(ccy=ccy), justify="right"
        )
    table.add_column("24h %", justify="right")
    if series_getter is not None:
        table.add_column("Trend", justify="left", no_wrap=True)
    table.add_column("Δ since last", justify="right")

    for idx, q in enumerate(snapshot.quotes, start=1):
        # decide pin glyph
        row_asset = q.meta.get("source_tab") if is_watchlist else current_tab_asset
        is_pinned = (
            bool(row_asset) and (row_asset, q.symbol) in pinned_set
        )
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
            price_str = _format_price(q.price)
            if q.meta.get("unit_note"):
                price_str += " †"
            price_text = Text(price_str)
            pct_text = _format_pct(q.change_24h_pct)
            prev_val = previous.get(q.symbol) if previous else None
            delta_text = _delta_cell(q.price, prev_val)

        is_selected = selected_index == idx - 1
        pointer = (
            Text("▍", style=f"bold {theme.POINTER}") if is_selected else ""
        )
        row: list = [pointer, star, str(idx)]
        if is_watchlist:
            row.append(q.meta.get("source_label", "?"))
        row += [q.symbol, q.name, price_text, pct_text]
        if series_getter is not None:
            series_key_asset = row_asset or asset
            series = series_getter(series_key_asset, q.symbol)
            row.append(render_sparkline(series, width=20))
        row.append(delta_text)
        row_style = theme.HIGHLIGHT_ROW_STYLE if is_selected else None
        table.add_row(*row, style=row_style)

    return table
