# terminex — project notes

Terminal multi-asset price dashboard with tabbed `fx` / `crypto` /
`commodity` / `watchlist` views, built on `rich` with a pluggable
provider interface. Rows are keyboard-navigable (vim-style) and sortable.

## Layout

- `forex.py` / `terminex/__main__.py` — entry points
- `terminex/app.py` — App controller, TabState, live refresh loop, sort
  logic (`_sort_quotes`), watchlist wiring, keyboard dispatch
- `terminex/keyboard.py` — POSIX stdin raw-mode listener
- `terminex/display.py` — asset-class-aware rich Table renderer; handles
  pin glyph, row highlight, sort indicator, watchlist layout
- `terminex/config.py` — TOML config loader (XDG) + env overrides
- `terminex/watchlist.py` — `Pin` / `Watchlist` + TOML round-trip
- `terminex/sparkline.py` — Unicode block renderer for price series
- `terminex/series.py` — `SeriesStore` ring buffers (per `(asset, symbol)`)
- `terminex/help.py` — help overlay + filter input bar
- `terminex/converter.py` — cross-rate parser, USD-pivot engine, panel renderer
- `terminex/quote.py` — shared `Quote` / `Snapshot` dataclasses
- `terminex/currencies.py` — BIS top-25 FX code list
- `terminex/providers/base.py` — `Provider` ABC + `ProviderError`
- `terminex/providers/fx_erapi.py` — open.er-api.com FX provider
- `terminex/providers/crypto_coincap.py` — CoinCap v3 crypto provider
- `terminex/providers/commodities_stooq.py` — Stooq CSV commodities
- `terminex/providers/watchlist_agg.py` — synthetic provider composing
  pinned quotes from other tabs' snapshots (no network I/O)

## Watchlist architecture

The watchlist tab is a synthetic provider. On each `fetch()` it walks
`Watchlist.pins` and looks up each pin's symbol in the relevant source
tab's `last_snapshot`. Source-tab refreshes invalidate the watchlist's
snapshot so the next poll re-composes it. When a user pins a symbol,
`App._lookup_pinned_quote` is the bridge between the aggregator and the
other tab states.

## Conventions

- Python 3.11+, stdlib + `requests` + `rich` only
- Each provider returns a `Snapshot` of `Quote` objects — rendering
  never branches on provider, only on `asset_class` / `is_watchlist`
- Small single-purpose modules; keep commits tight
- POSIX-only keyboard handling for now (termios/tty)

## Conventions

- Python 3.11+, stdlib + `requests` + `rich` only
- Each provider returns a `Snapshot` of `Quote` objects — rendering
  never branches on provider, only on `asset_class`
- Small single-purpose modules; keep commits tight
- POSIX-only keyboard handling for now (termios/tty)

## Known quirks

- CoinCap v3 requires a free API key (v2 is deprecated/dead)
- Yahoo Finance's v7 quote API is rate-limited to 429 for unauthenticated
  requests; we use Stooq instead
- Stooq reports some futures in non-standard units (silver/copper show
  exchange points, not USD/oz or USD/lb)
