"""Rendering for alert creation modal and alert list view."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import theme
from .alerts import Alert


def render_alert_new_panel(draft: dict) -> Panel:
    table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    table.add_column("")

    asset_class = draft["asset_class"]
    symbol = draft["symbol"]
    current = draft["current_price"]

    table.add_row(
        Text(
            f"Create alert on {asset_class.upper()}:{symbol}  "
            f"(current: {_fmt(current)})",
            style=f"bold {theme.ACCENT}",
        )
    )
    table.add_row("")

    # threshold line
    line = Text()
    line.append("  Condition:  price is  ", style=theme.MUTED)
    line.append(draft["op"], style=f"bold {theme.WARN}")
    line.append("  ", style="")
    line.append(draft["threshold_buffer"], style="bold white")
    line.append("▏", style=f"bold {theme.WARN}")
    table.add_row(line)

    recurring_line = Text()
    recurring_line.append("  Recurring: ", style=theme.MUTED)
    recurring_line.append(
        "yes" if draft["recurring"] else "no",
        style=f"bold {theme.ACCENT}" if draft["recurring"] else theme.MUTED,
    )
    table.add_row(recurring_line)

    table.add_row("")
    if draft.get("error"):
        table.add_row(Text(draft["error"], style=theme.ERROR))
        table.add_row("")
    table.add_row(
        Text(
            "0-9 . edit threshold  ·  < >  toggle op  ·  r  toggle recurring",
            style=theme.MUTED,
        )
    )
    table.add_row(
        Text("Enter to create · Esc to cancel", style=theme.MUTED)
    )
    return Panel(
        table,
        title="terminex — new alert",
        title_align="left",
        border_style=theme.PANEL_BORDER_WARN,
        padding=(1, 2),
    )


def render_alert_list_panel(
    alerts: list[Alert], delete_buffer: str = ""
) -> Panel:
    if not alerts:
        inner: Table | Text = Text("No alerts defined.", style=theme.MUTED)
    else:
        tbl = Table(show_header=True, box=None, padding=(0, 2), expand=False)
        tbl.add_column("#", style=theme.MUTED, justify="right")
        tbl.add_column("Status", style=theme.MUTED)
        tbl.add_column("Asset", style=theme.MUTED)
        tbl.add_column("Symbol", style="bold")
        tbl.add_column("Condition")
        tbl.add_column("Mode", style=theme.MUTED)
        tbl.add_column("Last fired", style=theme.MUTED)
        for a in alerts:
            status = Text(
                "active" if a.active else "done",
                style=theme.UP if a.active else theme.MUTED,
            )
            condition = Text(
                f"{a.op} {a.threshold:g}", style=f"bold {theme.WARN}"
            )
            mode = "recurring" if a.recurring else "once"
            last = a.last_fired_at.split("T")[0] if a.last_fired_at else "—"
            tbl.add_row(
                str(a.id), status, a.asset_class, a.symbol, condition, mode, last
            )
        inner = tbl

    body = Table(show_header=False, box=None, padding=(0, 0), expand=False)
    body.add_column("")
    body.add_row(inner)
    body.add_row("")
    # delete prompt
    prompt = Text()
    prompt.append("delete ID:  ", style=f"bold {theme.ACCENT}")
    prompt.append(delete_buffer, style="bold white")
    prompt.append("▏", style=f"bold {theme.WARN}")
    body.add_row(prompt)
    body.add_row("")
    body.add_row(
        Text(
            "digits build ID  ·  Enter deletes  ·  Esc to close",
            style=theme.MUTED,
        )
    )
    return Panel(
        body,
        title="terminex — alerts",
        title_align="left",
        border_style=theme.PANEL_BORDER_NEUTRAL,
        padding=(1, 2),
    )


def _fmt(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"
