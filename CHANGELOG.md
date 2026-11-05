# Changelog

## 0.6.0 (unreleased)

Makes terminex survive a dead feed: every tab now has somewhere to go when
its data source fails, and a daily check catches failures before users do.

### Added

- Fallback feeds. Crypto is served from CoinGecko, then CoinLore (both
  keyless); with a CoinCap key, CoinCap leads and the other two back it up.
  Commodities fall back from Yahoo's `query1` host to `query2`. The caption
  under the table names the feed in use, a failed feed rests for a few
  minutes (or as long as its rate limit asks), and terminex switches back
  when it recovers.
- A daily canary (`scripts/canary.py`, `canary` workflow) checks every feed
  against its live API, fallbacks included, and keeps a GitHub issue open
  for each failing feed until it recovers.
- Provider tests run against recorded real responses (`tests/fixtures/`,
  refreshed with `scripts/record_fixtures.py`).

### Changed

- A feed that answers with nothing usable (usually a format change
  upstream) now shows an error instead of an empty table.
- A pinned coin that the serving feed doesn't list shows "(not in current
  Crypto feed)" instead of "loading…", and "Δ since last" resets when the
  serving feed changes instead of showing the gap between two feeds.

## 0.5.0 (2026-11-04)

A repair release. The Commodities tab in 0.4.0 stopped working when Stooq
removed its CSV endpoint; this release moves it to Yahoo Finance and fixes
the problems found by a blackbox test of the published package and an
independent code review.

### Upgrading from 0.4.x

- **Commodity prices are now USD per unit.** Silver and copper were shown in
  exchange points, and grains and softs in cents. Saved commodity alerts are
  converted from cents to dollars the first time 0.5.0 starts, and terminex
  lists each conversion (for example `SI.F 3205 → 32.05`).
- **Alerts no longer re-fire when terminex restarts.** Whether an alert has
  fired is now stored, so a recurring alert fires again only after the
  price has gone back across the threshold. A new alert whose condition is
  already true waits for the next crossing.
- **Piped output prints once and exits.** `terminex | less` or
  `terminex > file` now prints the current tab instead of hanging.

### Added

- Brent crude (`BZ.F`), the 14th future, and a Unit column on the
  Commodities tab.
- A 7-day Trend column from provider history (CoinGecko and Yahoo), with the
  7-day change printed beside the line.
- `--once` prints the current tab and exits; this is automatic when output
  is not a terminal.
- The table scrolls with the selection and shows `rows 12–25 of 25`. In a
  small terminal, optional columns are dropped so prices are never truncated,
  and below the minimum size terminex says how large a terminal it needs.
- Arrow keys: `↑` / `↓` move, `←` / `→` switch tabs.
- Error panels count down to the next retry. `r` says when the next refresh
  is due if the feed has nothing new yet.
- The alert modal states the units of the threshold (`EUR per 1 USD`,
  `USD/oz`).
- Python 3.13 and 3.14 are supported and tested.

### Changed

- The commodities feed moved from Stooq to Yahoo Finance's spark endpoint.
  Symbols keep their `GC.F` style, so pins and alerts still match.
- CoinGecko is polled at most once a minute, matching its cache.
- Crypto prices of $1 or more show cents; smaller ones keep four significant
  digits. The `#` column keeps the market-cap rank when sorting.
- `TERMINEX_COINCAP_KEY` overrides the key in `config.toml`, as documented.
- Feed errors are one plain sentence ("can't reach open.er-api.com — check
  your connection") instead of the raw exception.

### Fixed

- The Commodities tab showed only a 404.
- Up opened the alerts list and Down did nothing; arrow-key escape sequences
  leaked out as separate keypresses.
- The watchlist showed FX rates instead of USD prices (EUR at 0.89 instead
  of 1.12).
- With a non-USD `--base`, the converter gave wrong crypto and commodity
  results (`1 BTC in GBP` was 12% high), and watchlist FX trends were drawn
  in the wrong currency.
- `kill`, `timeout` or closing the terminal left the cursor hidden, and a
  signal during startup could leave the terminal in cbreak mode.
- At 80×24 only 15 rows fit, and the selection and status bar went off
  screen. Resizing left fragments of old output.
- A wrong-typed config value, an unwritable data directory, a malformed API
  response or a date-form `Retry-After` header crashed terminex.
- Switching tabs and pressing `r` bypassed rate-limit backoff.
- A corrupt `watchlist.toml` was silently overwritten; it is now backed up to
  `watchlist.toml.bak`.
- Watchlist prices stopped updating while you stayed on that tab, and a
  feed that failed once stayed unavailable there.
- Pins from a failed feed said "loading…" forever, and the converter
  answered "unknown symbol" when a feed wasn't loaded.
- Very small USD prices on the watchlist (one Indonesian rupiah is about
  $0.00006) showed a single significant digit.
- Two terminex windows on the same database both fired the same alert, and
  recurring alerts re-fired on every restart while their condition held.
- FX alerts were compared in the wrong units in a window running a
  different `--base`. Alerts now keep the base they were created in
  (existing ones are taken as USD, 0.4.0's default).
- Alert fire times were shown as UTC dates.
- The help overlay was cut off at 80×24.
- Changes that round to zero were shown as `▼ -0.00%`.
- PyPI's Homepage and Issues links pointed to a repository that doesn't
  exist.

## 0.4.0 (2026-05-11)

First release on PyPI: FX, crypto and commodity tabs, a watchlist, price
alerts with desktop notifications, a cross-rate converter and sparklines.
