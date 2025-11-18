# terminex — project notes

Terminal multi-asset price dashboard with tabbed `fx` / `crypto` /
`commodity` views, built on `rich` with a pluggable provider interface.

## Layout

- `forex.py` / `terminex/__main__.py` — entry points
- `terminex/app.py` — App controller, tab state, live refresh loop
- `terminex/keyboard.py` — POSIX stdin raw-mode listener (1/2/3/r/q)
- `terminex/display.py` — asset-class-aware rich Table renderer
- `terminex/config.py` — TOML config loader (XDG) + env overrides
- `terminex/quote.py` — shared `Quote` / `Snapshot` dataclasses
- `terminex/currencies.py` — BIS top-25 FX code list
- `terminex/providers/base.py` — `Provider` ABC + `ProviderError`
- `terminex/providers/fx_erapi.py` — open.er-api.com FX provider
- `terminex/providers/crypto_coincap.py` — CoinCap v3 crypto provider
- `terminex/providers/commodities_stooq.py` — Stooq CSV commodities

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
