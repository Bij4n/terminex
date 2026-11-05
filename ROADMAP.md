# Roadmap

Where terminex is heading, in order. Each phase should ship as a release
before the next one starts.

## Where things stand (November 2026)

0.4.0 is on PyPI, and its Commodities tab no longer works: Stooq removed the CSV
endpoint it read from. A blackbox test of the published package, followed by
an independent code review, found more: broken arrow keys, wrong USD prices
for FX on the watchlist and in the converter with a non-USD `--base`, a
cursor left hidden after `kill`, no scrolling in an 80×24 terminal, a noisy
Trend column, crashes on malformed API responses and `Retry-After` headers,
and rate-limit backoff that tab switching could bypass. All of these are
fixed in 0.5.0.

The lesson from Stooq matters more than any single bug. Two of the three
feeds are free public endpoints with no contract (CoinGecko's public tier,
Yahoo's undocumented spark endpoint). They can be rate-limited, changed or
removed without notice, and nothing told anyone that commodities had died.

## Phase 1: 0.5.0, repair release

Released 2026-11-04. See `CHANGELOG.md` for the full list.

- Commodities on Yahoo Finance: 14 futures in USD per unit, Brent added.
  Saved alerts from 0.4.0 are migrated from cents to dollars.
- 7-day Trend from provider history, with the change printed beside it.
- Scrolling table, columns that drop in a set order so prices are never
  truncated, a clear message when the terminal is too small, and a help
  overlay that fits 80×24.
- Plain messages when a feed is offline or rate limited, with a retry
  countdown, and backoff that every refresh path respects.
- `--once` (also automatic when output is piped) for scripts and cron.
- Arrow keys, SIGTERM/SIGHUP cleanup, config and argument validation,
  validated API payloads, a corrupt watchlist backed up rather than replaced,
  and an in-memory fallback when the data directory isn't writable.
- Alerts fire once per crossing across terminex windows and restarts;
  fire times in local time; units shown when creating one.
- Python 3.13 and 3.14 in CI.

## Phase 2: survive a dead feed

Goal: the next provider failure is caught by us, not by users.

- **Provider canary.** A scheduled GitHub Actions job runs each provider
  against the live API daily and opens an issue when one fails or changes
  shape.
- **Recorded fixtures for every provider.** Parse tests run against saved
  real responses, so a format change shows up as a failing test with a diff.
- **Real fallbacks.** Today terminex uses CoinCap when a key is set and
  CoinGecko otherwise; neither takes over when the other fails. Add
  failure-triggered fallback for crypto, and find a second keyless (or
  free-key) commodities source so the tab has somewhere to go when Yahoo
  blocks it.
- **Injectable app parts.** Let `App` accept its providers, store and
  keyboard directly. The test suite already builds an `App` with fake
  providers in a temporary home; constructor injection would make that the
  supported way.

## Phase 3: use it from scripts and make it yours

- **`--json`.** The `--once` output as JSON, for status bars and scripts.
- **Your own symbols.** Choose the coins, FX codes and futures per tab in
  `config.toml` instead of the fixed top-25 lists.
- **FX trend history.** The ECB reference rates (keyless, daily) cover 24 of
  the 25 FX codes. That gives FX rows a 7-day trend instead of the live-only
  line.

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
