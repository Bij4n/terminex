"""Unified single-line status bar at the bottom of the display."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.text import Text

from . import theme


def _sep(bar: Text) -> None:
    bar.append("  ·  ", style=theme.MUTED)


def format_age(fetched_at: datetime | None) -> str:
    if fetched_at is None:
        return "—"
    now = datetime.now(tz=timezone.utc)
    delta = (now - fetched_at).total_seconds()
    if delta < 2:
        return "just now"
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    return f"{int(delta // 3600)}h ago"


def render_status_bar(
    *,
    tab_label: str,
    visible_count: int,
    total_count: int,
    sort_key: str,
    sort_desc: bool,
    filter_query: str,
    fetched_at: datetime | None,
    active_alerts: int = 0,
) -> Text:
    bar = Text()
    bar.append(f" {tab_label} ", style=f"bold {theme.ACCENT}")

    if total_count:
        _sep(bar)
        if visible_count == total_count:
            bar.append(f"{total_count} rows", style=theme.MUTED)
        else:
            bar.append(
                f"{visible_count}/{total_count} shown", style=theme.MUTED
            )

    if sort_key != "default":
        _sep(bar)
        arrow = "↓" if sort_desc else "↑"
        bar.append("sort: ", style=theme.MUTED)
        bar.append(f"{sort_key} {arrow}", style=f"bold {theme.ACCENT}")

    if filter_query:
        _sep(bar)
        bar.append("filter: ", style=theme.MUTED)
        bar.append(filter_query, style=f"bold {theme.WARN}")

    if active_alerts > 0:
        _sep(bar)
        bar.append(f"{active_alerts} alert", style=f"bold {theme.WARN}")
        if active_alerts != 1:
            bar.append("s", style=f"bold {theme.WARN}")

    _sep(bar)
    bar.append(format_age(fetched_at), style=theme.MUTED)

    bar.append("    ", style="")
    bar.append("? for keys", style=theme.MUTED)
    return bar
