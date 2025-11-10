"""Render a RateSnapshot as a rich Table."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from .currencies import NAMES, TOP_25
from .fetcher import RateSnapshot


def _format_rate(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.6f}"


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
    snapshot: RateSnapshot,
    previous: dict[str, float] | None = None,
) -> Table:
    title = f"terminex  ·  top 25 FX rates (base {snapshot.base})"
    caption_parts = [
        f"fetched {snapshot.fetched_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    ]
    if snapshot.provider_time is not None:
        caption_parts.append(
            f"provider {snapshot.provider_time.strftime('%Y-%m-%d %H:%M UTC')}"
        )
    caption_parts.append("ctrl-c to quit")

    table = Table(
        title=title,
        caption="  ·  ".join(caption_parts),
        header_style="bold cyan",
        title_style="bold white",
        caption_style="dim",
        expand=False,
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Code", style="bold")
    table.add_column("Currency")
    table.add_column(f"Rate (per 1 {snapshot.base})", justify="right")
    table.add_column("Δ since last", justify="right")

    for idx, (code, _) in enumerate(TOP_25, start=1):
        name = NAMES[code]
        if code == snapshot.base:
            rate_text = Text("1.0000  (base)", style="bold yellow")
            delta_text = Text("—", style="dim")
        else:
            rate_value = snapshot.rates.get(code)
            if rate_value is None:
                rate_text = Text("n/a", style="dim red")
                delta_text = Text("—", style="dim")
            else:
                rate_text = Text(_format_rate(rate_value))
                prev_val = previous.get(code) if previous else None
                delta_text = _delta_cell(rate_value, prev_val)

        table.add_row(str(idx), code, name, rate_text, delta_text)

    return table
