"""Render a Snapshot as a rich Table, asset-class aware."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from .quote import Snapshot

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
    if value >= 10000:
        return f"{value:,.2f}"
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.6f}"


def _format_pct(value: float | None) -> Text:
    if value is None:
        return Text("—", style="dim")
    if abs(value) < 1e-6:
        return Text("0.00%", style="dim")
    arrow = "▲" if value > 0 else "▼"
    style = "green" if value > 0 else "red"
    return Text(f"{arrow} {value:+.2f}%", style=style)


def _delta_cell(current: float, previous: float | None) -> Text:
    if previous is None or previous == 0:
        return Text("—", style="dim")
    diff = current - previous
    pct = (diff / previous) * 100.0
    if abs(pct) < 1e-6:
        return Text("0.0000%", style="dim")
    arrow = "▲" if diff > 0 else "▼"
    style = "green" if diff > 0 else "red"
    return Text(f"{arrow} {pct:+.4f}%", style=style)


def build_table(
    snapshot: Snapshot,
    previous: dict[str, float] | None = None,
) -> Table:
    asset = snapshot.asset_class
    ccy = snapshot.quote_ccy
    has_24h = any(q.change_24h_pct is not None for q in snapshot.quotes)

    title = f"terminex  ·  {_ASSET_TITLES[asset]} (quote {ccy})"

    caption_parts = [
        f"fetched {snapshot.fetched_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    ]
    if snapshot.provider_time is not None:
        caption_parts.append(
            f"provider {snapshot.provider_time.strftime('%Y-%m-%d %H:%M UTC')}"
        )
    if snapshot.provider_name:
        caption_parts.append(f"via {snapshot.provider_name}")
    caption_parts.append(r"\[1/2/3] tabs  \[r] refresh  \[q] quit")

    table = Table(
        title=title,
        caption="  ·  ".join(caption_parts),
        header_style="bold cyan",
        title_style="bold white",
        caption_style="dim",
        expand=False,
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column(_ASSET_SYMBOL_COLS[asset], style="bold")
    table.add_column(_ASSET_NAME_COLS[asset])
    table.add_column(
        _ASSET_PRICE_COLS[asset].format(ccy=ccy), justify="right"
    )
    if has_24h:
        table.add_column("24h %", justify="right")
    table.add_column("Δ since last", justify="right")

    for idx, q in enumerate(snapshot.quotes, start=1):
        if asset == "fx" and q.symbol == ccy:
            price_text = Text(f"1.0000  (base)", style="bold yellow")
            pct_text = Text("—", style="dim")
            delta_text = Text("—", style="dim")
        else:
            price_text = Text(_format_price(q.price))
            pct_text = _format_pct(q.change_24h_pct)
            prev_val = previous.get(q.symbol) if previous else None
            delta_text = _delta_cell(q.price, prev_val)

        row = [str(idx), q.symbol, q.name, price_text]
        if has_24h:
            row.append(pct_text)
        row.append(delta_text)
        table.add_row(*row)

    return table
