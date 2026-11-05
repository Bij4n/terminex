"""Unicode block sparklines with a % change label, for the Trend column."""

from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text

from . import theme

BLOCKS = "▁▂▃▄▅▆▇█"

# The vertical scale never spans less than this share of the price, so a
# stablecoin drifting 0.04% draws as a flat line instead of a cliff.
MIN_SCALE_PCT = 0.5

# " +12.34%" — the label is right-aligned in a fixed width.
LABEL_WIDTH = 8


def sample(series: Sequence[float], width: int) -> list[float]:
    """Reduce ``series`` to at most ``width`` points, keeping the latest."""
    pts = list(series)
    n = len(pts)
    if n <= width:
        return pts
    return [pts[min(n - 1, (i + 1) * n // width - 1)] for i in range(width)]


def render(
    series: Sequence[float],
    width: int = 20,
    change_pct: float | None = None,
) -> Text:
    """Render ``series`` as ``width`` block glyphs plus a % change label.

    The scale is the series' own min to max, widened to at least
    ``MIN_SCALE_PCT`` of the midpoint and centred, so small moves stay
    near the middle. ``change_pct`` labels the line (e.g. the provider's
    7-day change); without it the label is first → last of the series.
    Colour follows the sign of the change.
    """
    pts = sample([p for p in series if p > 0], width)
    if len(pts) < 2:
        # One point is not a trend; a lone block only confuses.
        return Text("·".rjust(width) + " " * LABEL_WIDTH, style=theme.MUTED)

    lo, hi = min(pts), max(pts)
    mid = (lo + hi) / 2
    span = max(hi - lo, mid * MIN_SCALE_PCT / 100)
    bottom = mid - span / 2
    steps = len(BLOCKS) - 1
    body = "".join(
        BLOCKS[max(0, min(steps, round((v - bottom) / span * steps)))]
        for v in pts
    )

    if change_pct is None and len(pts) >= 2:
        change_pct = (pts[-1] - pts[0]) / pts[0] * 100
    if change_pct is None or abs(change_pct) < 0.005:
        style = theme.ACCENT
    else:
        style = theme.UP if change_pct > 0 else theme.DOWN

    label = _format_change(change_pct) if change_pct is not None else ""
    text = Text(" " * (width - len(pts)))
    text.append(body, style=style)
    text.append(label.rjust(LABEL_WIDTH), style=style)
    return text


def _format_change(pct: float) -> str:
    """Signed percentage that fits the label width (fewer decimals as it grows)."""
    if abs(pct) < 100:
        return f"{pct:+.2f}%"
    if abs(pct) < 1000:
        return f"{pct:+.1f}%"
    return f"{pct:+.0f}%"
