"""Help overlay rendering."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

BINDINGS: list[tuple[str, str]] = [
    ("1 / 2 / 3 / 4", "switch to FX / Crypto / Commodities / Watchlist"),
    ("j / k", "move selected row down / up"),
    ("g / G", "jump to first / last row"),
    ("s", "cycle sort: default → 24h → price"),
    ("S", "toggle sort direction"),
    ("/", "filter by symbol or name substring"),
    ("Esc", "clear filter / close help"),
    ("w", "toggle watchlist pin for highlighted row"),
    ("~", "toggle sparkline column"),
    ("r", "force refresh the current tab"),
    ("?", "toggle this help overlay"),
    ("q / Ctrl-C", "quit"),
]


def render_help_panel() -> Panel:
    table = Table(
        show_header=False, box=None, padding=(0, 2), expand=False
    )
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Action")
    for key, action in BINDINGS:
        table.add_row(key, action)
    return Panel(
        table,
        title="terminex — keybindings",
        title_align="left",
        border_style="cyan",
        padding=(1, 2),
    )


def render_filter_bar(buffer: str) -> Text:
    """Inline input bar when user is typing a filter query."""
    line = Text()
    line.append(" / ", style="bold black on yellow")
    line.append(" ", style="")
    line.append(buffer, style="bold white")
    line.append("▏", style="bold yellow")
    line.append("  (Enter to apply · Esc to cancel)", style="dim")
    return line
