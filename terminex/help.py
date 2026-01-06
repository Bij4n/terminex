"""Help overlay rendering."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import theme

SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Navigation",
        [
            ("1 / 2 / 3 / 4", "switch tab: FX / Crypto / Cmdty / Watch"),
            ("j / k", "move selected row down / up"),
            ("g / G", "jump to first / last row"),
        ],
    ),
    (
        "Sort & filter",
        [
            ("s", "cycle sort: default → 24h → price"),
            ("S", "toggle sort direction"),
            ("/", "filter by symbol or name substring"),
            ("Esc", "clear filter / close help"),
        ],
    ),
    (
        "Watchlist & view",
        [
            ("w", "toggle watchlist pin for highlighted row"),
            ("~", "toggle sparkline column"),
            ("?", "toggle this help overlay"),
        ],
    ),
    (
        "Converter",
        [
            ("c", "open cross-rate calculator"),
        ],
    ),
    (
        "System",
        [
            ("r", "force refresh the current tab"),
            ("q / Ctrl-C", "quit"),
        ],
    ),
]


def render_help_panel() -> Panel:
    table = Table(
        show_header=False, box=None, padding=(0, 2), expand=False
    )
    table.add_column("Key", style=theme.HEADER_STYLE, no_wrap=True)
    table.add_column("Action")

    for idx, (section_name, bindings) in enumerate(SECTIONS):
        if idx > 0:
            table.add_row("", "")  # spacer between sections
        table.add_row(
            "",
            Text(section_name.upper(), style=f"bold {theme.ACCENT}"),
        )
        for key, action in bindings:
            table.add_row(key, action)

    return Panel(
        table,
        title="terminex — keybindings",
        title_align="left",
        border_style=theme.PANEL_BORDER_NEUTRAL,
        padding=(1, 2),
    )


def render_filter_bar(buffer: str) -> Text:
    """Inline input bar when user is typing a filter query."""
    line = Text()
    line.append(" / ", style=f"bold black on {theme.WARN}")
    line.append(" ", style="")
    line.append(buffer, style="bold white")
    line.append("▏", style=f"bold {theme.WARN}")
    line.append("  (Enter to apply · Esc to cancel)", style=theme.MUTED)
    return line
