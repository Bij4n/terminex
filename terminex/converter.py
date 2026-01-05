"""Cross-asset-class conversion via USD pivot.

Parses expressions like ``1 BTC in EUR`` or ``500 EUR in JPY`` and
evaluates them against the rates in currently-loaded snapshots from
the fx / crypto / commodity tabs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import theme
from .quote import Snapshot

# Case-insensitive. Amount allows commas as thousand-separators and a
# decimal point. Symbols are word chars plus ``.`` (for stooq futures
# like ``GC.F``) and ``_``.
_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<amount>[\d][\d,]*(?:\.\d+)?)
    \s+
    (?P<from>[A-Za-z][A-Za-z0-9._]*)
    \s+(?:in|to|→|->)\s+
    (?P<to>[A-Za-z][A-Za-z0-9._]*)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


class ParseError(ValueError):
    """Raised when a conversion expression can't be parsed."""


class ResolveError(ValueError):
    """Raised when a symbol isn't in any loaded snapshot."""


@dataclass(frozen=True)
class ParsedQuery:
    amount: float
    from_symbol: str
    to_symbol: str


@dataclass(frozen=True)
class ConversionResult:
    amount: float
    from_symbol: str
    to_symbol: str
    result: float


def parse_query(expression: str) -> ParsedQuery:
    match = _PATTERN.match(expression)
    if not match:
        raise ParseError(
            "expected form: <amount> <from> in <to>  "
            "(e.g. '1 BTC in EUR')"
        )
    amount_str = match.group("amount").replace(",", "")
    try:
        amount = float(amount_str)
    except ValueError as exc:
        raise ParseError(f"invalid amount: {amount_str!r}") from exc
    if amount <= 0:
        raise ParseError("amount must be positive")
    return ParsedQuery(
        amount=amount,
        from_symbol=match.group("from").upper(),
        to_symbol=match.group("to").upper(),
    )


def build_usd_lookup(snapshots: dict[str, Snapshot | None]) -> dict[str, float]:
    """Build ``{symbol: usd_per_unit}`` from loaded source snapshots.

    Preference on collision: fx > crypto > commodity (currency symbols
    win for the most natural interpretation).
    """
    lookup: dict[str, float] = {}

    def add(asset_class: str, symbol: str, price: float, base: str) -> None:
        sym = symbol.upper()
        if sym in lookup:
            return  # first-write-wins (preference order)
        if price <= 0:
            return
        if asset_class == "fx":
            # FX price is "foreign per 1 USD" when base==USD.
            # 1 unit of foreign currency = 1/price USD.
            if sym == base:
                lookup[sym] = 1.0
            else:
                lookup[sym] = 1.0 / price
        else:
            # crypto + commodity: quote is in USD per unit already.
            lookup[sym] = price

    # preference order
    for asset_class in ("fx", "crypto", "commodity"):
        snap = snapshots.get(asset_class)
        if snap is None:
            continue
        base = snap.quote_ccy
        for q in snap.quotes:
            add(asset_class, q.symbol, q.price, base)

    return lookup


def convert(query: ParsedQuery, lookup: dict[str, float]) -> ConversionResult:
    if query.from_symbol not in lookup:
        raise ResolveError(
            f"unknown symbol: {query.from_symbol!r}"
        )
    if query.to_symbol not in lookup:
        raise ResolveError(
            f"unknown symbol: {query.to_symbol!r}"
        )
    usd_from = lookup[query.from_symbol]
    usd_to = lookup[query.to_symbol]
    if usd_to == 0:
        raise ResolveError(f"zero rate for {query.to_symbol!r}")
    result = query.amount * usd_from / usd_to
    return ConversionResult(
        amount=query.amount,
        from_symbol=query.from_symbol,
        to_symbol=query.to_symbol,
        result=result,
    )


def evaluate(expression: str, lookup: dict[str, float]) -> ConversionResult:
    """Parse + convert in one call. Raises ParseError or ResolveError."""
    return convert(parse_query(expression), lookup)


def format_result(r: ConversionResult) -> str:
    """Short, human-readable result string for the history pane."""
    return (
        f"{_fmt(r.amount)} {r.from_symbol}  =  "
        f"{_fmt(r.result)} {r.to_symbol}"
    )


def _fmt(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def render_converter_panel(
    buffer: str,
    history: list[str],
    error: str | None,
) -> Panel:
    table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    table.add_column("")
    if history:
        for line in reversed(history):
            table.add_row(Text(line, style=theme.MUTED))
        table.add_row("")
    # input line
    input_line = Text()
    input_line.append("convert>  ", style=f"bold {theme.ACCENT}")
    input_line.append(buffer, style="bold white")
    input_line.append("▏", style=f"bold {theme.WARN}")
    table.add_row(input_line)
    if error:
        table.add_row(Text(error, style=theme.ERROR))
    else:
        table.add_row(
            Text(
                "  examples: 1 BTC in EUR · 500 EUR in JPY · 1 GC.F in EUR",
                style=theme.MUTED,
            )
        )
    table.add_row("")
    table.add_row(
        Text("Esc to close · Enter to compute", style=theme.MUTED)
    )
    return Panel(
        table,
        title="terminex — converter",
        title_align="left",
        border_style=theme.PANEL_BORDER_NEUTRAL,
        padding=(1, 2),
    )
