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

## Phase 2: survive a dead feed (released in 0.6.0, 2026-11-04)

Goal: the next provider failure is caught by us, not by users.

Done in 0.6.0:

- **Provider canary.** A daily GitHub Actions job checks every feed against
  its live API, fallbacks included, and keeps one issue open per failing
  feed until it recovers.
- **Recorded fixtures.** Provider tests parse saved real responses, so a
  format change shows up as a failing test.
- **Fallbacks.** Crypto: CoinGecko → CoinLore, with CoinCap first when a key
  is set. Commodities: Yahoo's `query1` host → `query2`.
- **Injectable app parts.** `App` takes its providers, store, console and
  keyboard, and the main loop has tests.

Still open:

- **An independent commodities source.** No keyless feed covering all 14
  futures was found; both fallbacks are Yahoo. Candidates need a key
  (FRED: daily, no metals) or cover only metals (gold-api.com).

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
