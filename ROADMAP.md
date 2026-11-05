# Roadmap

Where terminex is heading, in order. Each phase should ship as a release
before the next one starts.

## Where things stand (November 2026)

0.4.0 is on PyPI, and its Commodities tab no longer works: Stooq removed the CSV
endpoint it read from. A blackbox test of the published package also found
broken arrow keys, an inverted EUR price on the watchlist, wrong
crypto-to-FX conversions with a non-USD `--base`, a cursor left hidden
after `kill`, no scrolling in an 80×24 terminal, and a Trend column too
noisy to read. All of these are fixed for the next release.

The lesson from Stooq matters more than any single bug. Two of the three
feeds are free public endpoints with no contract (CoinGecko's public tier,
Yahoo's undocumented spark endpoint). They can be rate-limited, changed or
removed without notice, and nothing told anyone that commodities had died.

## Phase 1: 0.5.0, repair release

Ready to release.

- Commodities on Yahoo Finance: 14 futures in USD per unit, Brent added.
- 7-day Trend from provider history, with the change printed beside it.
- Scrolling table, and columns that drop in a set order so prices are never truncated.
- Arrow keys, SIGTERM/SIGHUP cleanup, config and argument validation.
- Correct USD prices for FX on the watchlist and in the converter.
- CoinGecko polled no faster than its 60-second cache.
- Python 3.13 and 3.14 in CI.

## Phase 2: survive a dead feed

Goal: the next provider failure is caught by us, not by users, and the app
degrades clearly instead of confusingly.

- **Provider canary.** A scheduled GitHub Actions job runs each provider
  against the live API daily and opens an issue when one fails or changes
  shape.
- **Recorded fixtures for every provider.** Parse tests run against saved
  real responses, so a format change shows up as a failing test with a diff.
- **Plain degraded states.** One sentence per state ("can't reach
  open.er-api.com, retrying in 60 s") instead of raw exceptions. Watchlist
  rows say "unavailable" rather than "loading…" forever. The converter names
  the missing feed.
- **Fallbacks where they exist.** Crypto already falls back from CoinCap to
  CoinGecko. Find a second keyless commodities source, or a free-key option,
  so the tab has somewhere to go when Yahoo blocks it.
- **Tests for the app loop.** Let `App` accept its providers, store and
  keyboard, so key handling, tab switching and refresh timing can be tested
  with fakes. Today only the pure modules are covered.
- **Small fixes from testing:** a corrupt `watchlist.toml` is backed up
  rather than overwritten, an unwritable data dir runs without persistence
  instead of crashing, alert times shown in local time, crypto prices at 2
  decimals, and `#` keeps the market-cap rank after sorting.

## Phase 3: use it from scripts and make it yours

- **`--once` and `--json`.** Print one snapshot and exit, as a table or as
  JSON, for scripts, status bars and cron. Also fixes piped output, which
  today prints nothing and never exits.
- **Your own symbols.** Choose the coins, FX codes and futures per tab in
  `config.toml` instead of the fixed top-25 lists.
- **FX trend history.** The ECB reference rates (keyless, daily) cover 24 of
  the 25 FX codes. That gives FX rows a 7-day trend instead of the live-only
  line.
- **Alert polish.** Fire once per alert even with two instances open, and
  pre-fill FX alerts in the units the row shows.

## Phase 4: reach

- **Stocks and ETFs tab.** The Yahoo spark endpoint already serves equities,
  so this mostly reuses the commodities provider. Only worth doing once
  Phase 2's canary and fallbacks exist, because it deepens the dependence on
  an unofficial endpoint.
- **Windows.** Keyboard input is termios-only. A `msvcrt` listener would
  make the rest of the app work unchanged.

## Not planned

- Accounts, a hosted service, or anything that needs a server.
- Trading or brokerage integration.
- Dependencies beyond `requests` and `rich`.
