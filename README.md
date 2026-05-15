# terminex

A terminal dashboard for live prices across FX, crypto, and commodities — because opening a browser tab just to check a price is too many steps.

terminex keeps a persistent, keyboard-navigable price table in your terminal with live sparklines, cross-rate conversion, and threshold alerts — all built on `rich` with no Electron, no browser, and no SaaS account required.

## Asset classes

- **FX** — top 25 most-traded currencies (BIS triennial survey), updated hourly
- **Crypto** — top 25 coins by market cap via CoinGecko (no key required) or CoinCap (free key, faster)
- **Commodities** — 14 futures across metals, energy, and agriculturals via Stooq (~15 min delayed)
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
| `j` / `k` | Move highlighted row down / up                      |
| `g` / `G` | Jump to first / last row                            |
| `s`       | Cycle sort key: default → 24h → price               |
| `S`       | Toggle sort direction                               |
| `/`       | Filter by symbol or name substring (live)           |
| `Esc`     | Clear filter / close help / close converter         |
| `w`       | Toggle watchlist pin for the highlighted row        |
| `~`       | Toggle sparkline column                             |
| `c`       | Open cross-rate calculator                          |
| `a`       | Create alert on highlighted row                     |
| `A`       | List / delete alerts                                |
| `?`       | Toggle help overlay                                 |
| `r`       | Force refresh the current tab                       |
| `q`       | Quit                                                |

## CLI options

```bash
terminex --base EUR        # FX base currency (default: USD)
terminex --tab crypto      # start on a specific tab (fx|crypto|commodity|watchlist)
terminex --interval 15     # refresh interval in seconds (default: 10)
```

## Features

### Filter

Press `/` to enter live-filter mode. The table narrows as you type against both symbol and name. `Enter` exits filter mode while keeping the filter active; `Esc` cancels and clears it.

### Sparklines

Press `~` to toggle a 20-point sparkline column built from live polls. Series start empty and fill in over time, so the longer terminex runs the richer the history. Green means net up, red means net down. The SQLite-backed series store persists across restarts so your sparklines survive a reboot.

### Cross-rate calculator

Press `c` to open a conversion prompt that resolves across all three asset classes via USD pivot. Type natural expressions:

```
1 BTC in EUR
500 EUR in JPY
1 GC.F in EUR
1,000 USD in GBP
```

Press `Enter` to compute, `Esc` to close. The last 5 results stay visible above the prompt. Commodity symbols use Stooq notation (`GC.F` for gold, `CL.F` for crude, etc.).

### Price alerts

Highlight any row and press `a` to open the alert-creation modal. The threshold pre-fills with the current price.

| Key        | Action                         |
|------------|--------------------------------|
| `0-9` / `.` | Edit threshold value          |
| `<` / `>`  | Toggle comparison operator     |
| `r`        | Toggle recurring (default: one-shot) |
| `Enter`    | Create alert                   |
| `Esc`      | Cancel                         |

Alerts fire when a price *crosses* the threshold — not every tick while above or below it. On fire: terminal bell, status-line toast, and a desktop notification via `notify-send` (Linux; silently skipped if unavailable). Non-recurring alerts auto-deactivate after the first fire.

Press `A` for the list view — browse all alerts, enter an ID and press `Enter` to delete. The status bar shows the active count.

Alerts are stored in SQLite at `~/.local/share/terminex/terminex.db` (or `$XDG_DATA_HOME/terminex/`) and survive across runs.

### Watchlist

Press `w` on any row in the FX, Crypto, or Commodities tabs to pin it. Press `4` to see all pinned rows in a single unified view, sortable the same way as any other tab. Pins persist to `~/.config/terminex/watchlist.toml`.

## Data sources

| Asset       | Provider                       | Key required? | Notes                         |
|-------------|--------------------------------|---------------|-------------------------------|
| FX          | `open.er-api.com`              | no            | updates ~hourly               |
| Crypto      | `coingecko.com` (default)      | no            | top 25 by mcap, ~1 min cache  |
| Crypto      | `rest.coincap.io` (if key set) | yes (free)    | top 25 by mcap, sub-minute    |
| Commodities | `stooq.com` (CSV)              | no            | 14 futures, ~15 min delayed   |

The crypto tab works out of the box via CoinGecko's public API. For higher-rate data, grab a free [CoinCap API key](https://coincap.io/) and export it — terminex automatically prefers it when present:

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

Bug reports and pull requests are welcome at https://github.com/Bij4n/terminex/issues.

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
- Run the test suite before opening a PR

Your terminal is already open. Your prices should be there too.
