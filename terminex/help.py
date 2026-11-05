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
            ("1 – 4", "switch tab"),
            ("← / →", "previous / next tab"),
            ("j k / ↓ ↑", "move down / up"),
            ("g / G", "first / last row"),
        ],
    ),
    (
        "Sort & filter",
        [
            ("s", "cycle sort: 24h, price"),
            ("S", "reverse the sort"),
            ("/", "filter by symbol or name"),
            ("Esc", "clear filter / close"),
        ],
    ),
    (
        "Watchlist & view",
        [
            ("w", "pin / unpin the row"),
            ("~", "trend column"),
            ("?", "this help"),
        ],
    ),
    (
        "Converter & alerts",
        [
            ("c", "cross-rate converter"),
            ("a", "new alert on the row"),
            ("A", "list / delete alerts"),
        ],
    ),
    (
        "System",
        [
            ("r", "refresh now"),
            ("q", "quit (also Ctrl-C)"),
        ],
    ),
]

# Below this width the sections stack in one column.
_TWO_COLUMN_WIDTH = 76


def _section(name: str, bindings: list[tuple[str, str]]) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    table.add_column("Key", style=theme.HEADER_STYLE, no_wrap=True, min_width=9)
    table.add_column("Action")
    table.add_row("", Text(name.upper(), style=f"bold {theme.ACCENT}"))
    for key, action in bindings:
        table.add_row(key, action)
    return table


def render_help_panel(width: int = 120) -> Panel:
    """Keybindings, in two columns when there's room (fits 80×24)."""
    sections = [_section(name, bindings) for name, bindings in SECTIONS]
    columns = 2 if width >= _TWO_COLUMN_WIDTH else 1
    grid = Table.grid(padding=(0, 3))
    for _ in range(columns):
        grid.add_column()
    for i in range(0, len(sections), columns):
        if i:
            grid.add_row(*([""] * columns))  # spacer between section rows
        row = sections[i:i + columns]
        grid.add_row(*row, *([""] * (columns - len(row))))
    return Panel(
        grid,
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
