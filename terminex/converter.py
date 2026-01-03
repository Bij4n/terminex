"""Cross-asset-class conversion via USD pivot.

Parses expressions like ``1 BTC in EUR`` or ``500 EUR in JPY`` and
evaluates them against the rates in currently-loaded snapshots from
the fx / crypto / commodity tabs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
