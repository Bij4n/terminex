"""Centralized color and style tokens.

All color decisions for terminex live here. Other modules import these
tokens and compose styles — no ``rich`` color strings should appear
anywhere else in the codebase.
"""

from __future__ import annotations

# Semantic foreground colors
UP = "green"
DOWN = "red"
NEUTRAL = "dim"
ACCENT = "cyan"
WARN = "yellow"
ERROR = "red"

# Role-specific tokens
MUTED = "dim"
STAR = "yellow"
BASE = "bold yellow"
POINTER = "cyan"

# Background for highlighted (selected) row
HIGHLIGHT_BG = "grey15"
HIGHLIGHT_ROW_STYLE = f"on {HIGHLIGHT_BG}"

# Border styles for state panels
PANEL_BORDER_NEUTRAL = "cyan"
PANEL_BORDER_WARN = "yellow"
PANEL_BORDER_ERROR = "red"

# Text styling roles
HEADER_STYLE = "bold cyan"
TITLE_STYLE = "bold white"
CAPTION_STYLE = "dim"
DIM_TEXT = "dim"


def pct_style(value: float | None) -> str:
    """Return a style string for a signed percentage value."""
    if value is None:
        return NEUTRAL
    if value > 0:
        return UP
    if value < 0:
        return DOWN
    return NEUTRAL
