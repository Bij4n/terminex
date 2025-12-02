"""Unicode block sparklines for price series."""

from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text

BLOCKS = "▁▂▃▄▅▆▇█"


def render(series: Sequence[float], width: int = 20) -> Text:
    """Render a sparkline from a price series.

    Trailing ``width`` points are used. Scaling is local to the series
    (min → ▁, max → █). An all-equal series renders as a flat middle bar.
    Color tracks net direction from first to last point.
    """
    pts = list(series)[-width:]
    if not pts:
        return Text(" " * width, style="dim")

    # Pad left with spaces so newly-started series don't stretch horizontally.
    pad = " " * (width - len(pts))

    lo = min(pts)
    hi = max(pts)
    if hi - lo < 1e-12:
        body = BLOCKS[len(BLOCKS) // 2] * len(pts)
    else:
        span = hi - lo
        steps = len(BLOCKS) - 1
        body = "".join(
            BLOCKS[int(round(((v - lo) / span) * steps))] for v in pts
        )

    if len(pts) >= 2:
        first, last = pts[0], pts[-1]
        if last > first:
            style = "green"
        elif last < first:
            style = "red"
        else:
            style = "cyan"
    else:
        style = "cyan"

    return Text(pad + body, style=style)
