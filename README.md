# terminex

A terminal dashboard for live prices across FX, crypto, and commodities — because opening a browser tab just to check a price is too many steps.

terminex keeps a persistent, keyboard-navigable price table in your terminal with live sparklines, cross-rate conversion, and threshold alerts — all built on `rich` with no Electron, no browser, and no SaaS account required.

## Asset classes

- **FX** — top 25 most-traded currencies (BIS triennial survey), updated hourly
- **Crypto** — top 25 coins by market cap via CoinGecko, with CoinLore as a fallback (no key required), or CoinCap (free key, faster)
- **Commodities** — 14 futures across metals, energy, and agriculturals via Yahoo Finance (~10 min delayed), all in USD per unit
- **Watchlist** — a synthetic view composing your pinned rows from all three tabs in one place

## Install

Requires Python 3.11+.

```bash
pipx install terminex
# or, from a local checkout:
pipx install .
# or editable for development:
pip install -e .
```

## Run

```bash
terminex
# or without installing:
python3 -m terminex
```

## Keys

| Key       | Action                                              |
|-----------|-----------------------------------------------------|
| `1/2/3/4` | Switch to FX / Crypto / Commodities / Watchlist tab |
| `←` / `→` | Previous / next tab                                 |
| `j` / `k` | Move highlighted row down / up (also `↓` / `↑`)     |
| `g` / `G` | Jump to first / last row                            |
| `s`       | Cycle sort key: default → 24h → price               |
| `S`       | Toggle sort direction                               |
| `/`       | Filter by symbol or name substring (live)           |
| `Esc`     | Clear filter / close help / close converter         |
| `w`       | Toggle watchlist pin for the highlighted row        |
| `~`       | Toggle the 7-day trend column                       |
| `c`       | Open cross-rate calculator                          |
| `a`       | Create alert on highlighted row                     |
| `A`       | List / delete alerts                                |
| `?`       | Toggle help overlay                                 |
| `r`       | Refresh now (says when, if the feed has nothing new) |
| `q`       | Quit                                                |

## CLI options

```bash
terminex --base EUR        # FX base currency (default: USD)
terminex --tab crypto      # start on a specific tab (fx|crypto|commodity|watchlist)
terminex --interval 15     # refresh interval in seconds (default: 10)
terminex --once            # print the current tab once and exit
terminex --version         # print the installed version
```

## Features

### Filter

Press `/` to enter live-filter mode. The table narrows as you type against both symbol and name. `Enter` exits filter mode while keeping the filter active; `Esc` cancels and clears it.

### Sparklines

Press `~` to toggle the Trend column. Commodity rows, and crypto rows on the default CoinGecko feed, show the last 7 days as soon as they load, with the 7-day change beside the line. FX, and crypto while CoinCap or CoinLore is serving it, has no free history, so those rows draw from prices collected while terminex runs, stored in SQLite so they survive restarts. Moves smaller than 0.5% stay close to flat, so a stablecoin's noise doesn't look like a crash. Green means up over the period, red means down.

### Cross-rate calculator

Press `c` to open a conversion prompt that resolves across all three asset classes via USD pivot. Type natural expressions:

```
1 BTC in EUR
500 EUR in JPY
1 GC.F in EUR
1,000 USD in GBP
```

Press `Enter` to compute, `Esc` to close. The last 5 results stay visible above the prompt. Commodity symbols use futures notation (`GC.F` for gold, `CL.F` for WTI crude, `BZ.F` for Brent, etc.).

### Price alerts

Highlight any row and press `a` to open the alert-creation modal. The threshold pre-fills with the current price.

| Key        | Action                         |
|------------|--------------------------------|
| `0-9` / `.` | Edit threshold value          |
| `<` / `>`  | Toggle comparison operator     |
| `r`        | Toggle recurring (default: one-shot) |
| `Enter`    | Create alert                   |
| `Esc`      | Cancel                         |

Alerts fire when a price *crosses* the threshold — not every tick while above or below it. On fire: terminal bell, status-line toast, and a desktop notification via `notify-send` (Linux; silently skipped if unavailable). Non-recurring alerts auto-deactivate after the first fire. A recurring alert re-arms once the price is back on the other side of the threshold, so it fires on every genuine crossing. An alert created while its condition already holds waits for the next crossing. Restarting terminex doesn't re-fire alerts, and two terminex windows sharing a database never fire the same crossing twice. FX alerts keep the base currency they were created in (`JPY per 1 USD`), so they mean the same thing whatever `--base` a window uses.

Press `A` for the list view — browse all alerts, enter an ID and press `Enter` to delete. The status bar shows the active count.

Alerts are stored in SQLite at `~/.local/share/terminex/terminex.db` (or `$XDG_DATA_HOME/terminex/`) and survive across runs.

### Watchlist

Press `w` on any row in the FX, Crypto, or Commodities tabs to pin it. Press `4` to see all pinned rows in a single unified view, sortable the same way as any other tab. Pins persist to `~/.config/terminex/watchlist.toml`.

### Scripting

When output isn't a terminal (`terminex | less`, `terminex > prices.txt`, cron), or with `--once`, terminex prints the current tab as a table and exits. It exits with status 1 and a message on stderr if the feed can't be reached. Alerts are not checked in this mode.

```bash
terminex --once --tab crypto
terminex --tab commodity > commodities.txt
```

## Data sources

| Asset       | Feeds, in order                                            | Key required?    | Notes                                  |
|-------------|------------------------------------------------------------|------------------|----------------------------------------|
| FX          | `open.er-api.com`                                          | no               | updates ~hourly                        |
| Crypto      | `rest.coincap.io` (only if a key is set) → `coingecko.com` → `coinlore.com` | CoinCap: free key | top 25 by market cap; 7-day history from CoinGecko |
| Commodities | `query1.finance.yahoo.com` → `query2.finance.yahoo.com`    | no               | 14 futures, ~10 min delayed            |

When a feed fails, terminex serves the tab from the next one in its row and the caption under the table says so (for example "via coinlore.com (coingecko.com unavailable)"). A feed that fails rests for a few minutes (or as long as its rate limit asks) before it is tried again, and terminex switches back when it recovers. If every feed fails at once, terminex assumes the connection dropped and retries the first feed within 30 seconds.

The commodities feed uses Yahoo Finance's public but undocumented spark endpoint, served from two hosts. If Yahoo changes or limits it, the Commodities tab shows an error and the other tabs keep working.

The crypto tab works out of the box via CoinGecko's public API, with CoinLore behind it. For higher-rate data, grab a free [CoinCap API key](https://coincap.io/) and export it; CoinCap then leads the chain:

```bash
export TERMINEX_COINCAP_KEY=your-key-here
```

## Config file

terminex looks for `~/.config/terminex/config.toml` (or `$XDG_CONFIG_HOME/terminex/config.toml`). All keys are optional:

```toml
base_currency = "USD"
refresh_interval = 10
active_tab = "fx"

[providers.crypto]
api_key = "your-coincap-key"
```

Environment variables override config file values.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Stdlib `unittest` only — no extra dependencies. Covers the pure-logic modules: converter, alerts DAO and engine, watchlist, filter/sort helpers, and age formatter. No external services or API keys required; tests use an in-memory SQLite database.

## Contributing

Bug reports and pull requests are welcome at https://github.com/Bij4n/terminex/issues. See [CHANGELOG.md](CHANGELOG.md) for what changed in each release and [ROADMAP.md](ROADMAP.md) for what's planned next.

```bash
git clone https://github.com/Bij4n/terminex.git
cd terminex
pip install -e .
terminex
```

**Guidelines:**

- Keep dependencies minimal: stdlib + `requests` + `rich` only
- Each provider must return a `Snapshot` of `Quote` objects — the renderer must not branch on provider identity
- New providers go in `terminex/providers/` and implement the `Provider` ABC from `providers/base.py`
- POSIX-only for now (keyboard handling uses `termios`/`tty`)
- Run the test suite before opening a PR: `python -m unittest discover -s tests -t .`
- Provider tests parse real responses saved in `tests/fixtures/`; refresh them with `python scripts/record_fixtures.py` when a feed changes its format on purpose
- `python scripts/canary.py` checks every live feed; the `canary` workflow runs it daily and opens an issue labelled `canary` when a feed fails

Your terminal is already open. Your prices should be there too.
