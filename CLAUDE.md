# terminex — project notes

Terminal multi-asset price dashboard with tabbed `fx` / `crypto` /
`commodity` / `watchlist` views, built on `rich` with a pluggable
provider interface. Rows are keyboard-navigable (vim-style and arrow keys)
and sortable. Plans live in `ROADMAP.md`; every user-visible change goes in
`CHANGELOG.md`.

## Layout

- `terminex/__main__.py` — `python -m terminex` entry point
- `terminex/app.py` — App controller, TabState, live refresh loop, sort
  logic (`_sort_quotes`), watchlist wiring, keyboard dispatch, viewport
  fitting (`_fit_to_terminal`, "too small" state), SIGTERM/SIGHUP →
  SystemExit, `run_once` (`--once` / piped output). All fetches go through
  `_refresh`, which enforces rate-limit backoff; `r` uses `_manual_refresh`
- `terminex/keyboard.py` — POSIX raw-mode listener; reads the fd with
  `os.read` and parses escape sequences with `split_keys`
- `terminex/display.py` — asset-class-aware rich Table renderer; pin glyph,
  row highlight, Trend cell, `fit_hidden` column dropping, `scroll_offset`
- `terminex/statusbar.py` — bottom status line and `format_age`
- `terminex/theme.py` — every colour/style token (no rich colour strings elsewhere)
- `terminex/config.py` — TOML config loader (XDG) + env overrides; each
  value validated, bad values warn and fall back to defaults
- `terminex/watchlist.py` — `Pin` / `Watchlist` + TOML round-trip
- `terminex/sparkline.py` — block sparkline with % label, 0.5% minimum scale
- `terminex/series.py` — `SeriesStore` ring buffers (per `(asset, symbol)`),
  stores only changed prices
- `terminex/help.py` — help overlay (two columns from 76 cols, fits 80×24) +
  filter input bar
- `terminex/converter.py` — cross-rate parser, USD-pivot engine
  (`fx_usd_per_unit`, `build_usd_lookup`), panel renderer
- `terminex/store.py` — SQLite scaffolding (WAL, XDG path, schema init),
  `open_store` (in-memory fallback + startup notices), versioned migrations
  via `PRAGMA user_version` (v1: commodity alert thresholds cents → dollars)
- `terminex/alerts.py` — Alert dataclass + CRUD DAO; `claim_fire` makes a
  fire atomic across instances, recurring alerts cool down 5 min
- `terminex/alert_engine.py` — threshold crossing detection with last-price tracking
- `terminex/alerts_ui.py` — alert creation modal + list view panels
- `terminex/quote.py` — shared `Quote` / `Snapshot` dataclasses
- `terminex/currencies.py` — BIS top-25 FX code list
- `terminex/providers/base.py` — `Provider` ABC, `ProviderError`, `RateLimitError`,
  `finite_number` (payload validation), `parse_retry_after`,
  `describe_request_error` (one-sentence error messages)
- `terminex/providers/fx_erapi.py` — open.er-api.com FX provider
- `terminex/providers/crypto_coincap.py` — CoinCap v3 crypto provider (requires key)
- `terminex/providers/crypto_coingecko.py` — CoinGecko public crypto provider
  (keyless default, includes 7-day sparkline history)
- `terminex/providers/commodities_yahoo.py` — Yahoo Finance v8 spark, 14 futures
  in one request, with 7-day history
- `terminex/providers/watchlist_agg.py` — synthetic provider composing
  pinned quotes from other tabs' snapshots (no network I/O)

## Watchlist architecture

The watchlist tab is a synthetic provider. On each `fetch()` it walks
`Watchlist.pins` and looks up each pin's symbol in the relevant source
tab's `last_snapshot`. Source-tab refreshes invalidate the watchlist's
snapshot so the next poll re-composes it. When a user pins a symbol,
`App._lookup_pinned_quote` is the bridge between the aggregator and the
other tab states. FX pins are converted to USD per unit through
`App._fx_usd_price` (the FX tab itself shows units per base).

## Conventions

- Python 3.11+, stdlib + `requests` + `rich` only
- Each provider returns a `Snapshot` of `Quote` objects — rendering
  never branches on provider, only on `asset_class` / `is_watchlist`
- Providers put optional extras in `Quote.meta`: `history` (list of prices,
  oldest first), `change_7d_pct`, `unit`, `rank`
- Every table column is `no_wrap`: the viewport math assumes one line per row
- Small single-purpose modules; keep commits tight; tests first for fixes
- POSIX-only keyboard handling for now (termios/tty)

## Tests

`python3 -m unittest discover -s tests -t .` — stdlib only, no network
(`requests.get` is mocked in provider tests; keyboard tests use a pty).
`tests/test_app.py` builds a real `App` with fake providers in a temporary
home, with full-frame render tests at several terminal sizes and a fake
clock for refresh timing.
CI runs Ubuntu and macOS on Python 3.11–3.14.

## Known quirks

- Stooq's CSV endpoint was removed in 2026 (the 0.4.0 Commodities tab died
  with a 404); commodities now come from Yahoo's undocumented v8 spark endpoint
- Yahoo rejects the default `python-requests` User-Agent with 429 "Edge: Too
  Many Requests"; the provider sends one naming terminex and the repo URL
- Yahoo quotes grains and softs (ZW, ZC, ZS, KC, SB, CT) in US cents; the
  provider converts them to dollars so every price is USD per unit
- Commodity symbols keep the old `GC.F` style so existing pins and alerts match;
  0.4.0 alert thresholds in cents are migrated on first start (store v1)
- CoinCap v3 requires a free API key (v2 is dead); CoinGecko is the keyless default
- CoinGecko's public tier caches ~60 s and rate-limits per IP (worse on shared
  VPN exits), so its provider has a 60 s poll floor
- open.er-api.com has no history, so FX rows draw the live series only; the
  app also records an `fx_usd` series (USD per unit) for watchlist FX trends
