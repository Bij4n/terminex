# terminex

A terminal dashboard for live prices across three asset classes:

- **FX** — top 25 most-traded currencies (BIS triennial survey)
- **Crypto** — top 25 coins by market cap
- **Commodities** — metals, energy, and agriculturals futures

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

### Keys

| Key       | Action                                              |
|-----------|-----------------------------------------------------|
| `1/2/3/4` | Switch to FX / Crypto / Commodities / Watchlist tab |
| `j` / `k` | Move highlighted row down / up                      |
| `g` / `G` | Jump to first / last row                            |
| `s`       | Cycle sort key: default → 24h → price               |
| `S`       | Toggle sort direction                               |
| `/`       | Filter by symbol or name substring (live)           |
| `Esc`     | Clear filter / close help / close converter        |
| `w`       | Toggle watchlist pin for the highlighted row        |
| `~`       | Toggle sparkline column                             |
| `c`       | Open cross-rate calculator                          |
| `a`       | Create alert on highlighted row                     |
| `A`       | List / delete alerts                                |
| `?`       | Toggle help overlay                                 |
| `r`       | Force refresh the current tab                       |
| `q`       | Quit                                                |

### CLI options

- `--base USD` — FX base currency (default: `USD`)
- `--tab fx|crypto|commodity|watchlist` — tab to start on
- `--interval 10` — refresh interval in seconds

### Filter

Press `/` to enter live-filter mode and start typing. The table filters
as you type against both symbol and name. Enter exits filter mode
(keeping the filter active); Esc cancels and clears.

### Sparklines

Press `~` to toggle a 20-point sparkline column showing recent price
movement. Series are built up from live polls — newly-started series
start empty and fill in over time. Green means net up, red means net
down. The column hides the natural units but makes trend-shape obvious
at a glance.

### Cross-rate calculator

Press `c` to open an interactive conversion prompt that resolves across
all three asset classes via USD pivot. Type expressions like:

```
1 BTC in EUR
500 EUR in JPY
1 GC.F in EUR
1,000 USD in GBP
```

Press `Enter` to compute, `Esc` to close. The last 5 results stay
visible above the prompt. Symbols are whatever is loaded in the
fx / crypto / commodity tabs (commodity symbols use Stooq notation like
`GC.F`, `CL.F`).

### Price alerts

Highlight any row and press `a` to open the alert-creation modal. The
threshold field pre-fills with the current price. While the modal is
open:

- `0-9` / `.` — edit threshold
- `<` / `>` — toggle the comparison operator
- `r` — toggle recurring (one-shot by default)
- `Enter` — create alert
- `Esc` — cancel

Alerts fire when the price *crosses* the threshold, not every tick
while above/below it. On fire: terminal bell, toast in the status
line, and a desktop notification via `notify-send` (Linux; silently
skipped if unavailable). Non-recurring alerts auto-deactivate on first
fire.

Press `A` for the list view — browse all alerts, type an ID and press
`Enter` to delete. The status bar shows the active-alert count.

Alerts are stored in SQLite at
`~/.local/share/terminex/terminex.db` (or `$XDG_DATA_HOME/terminex/`)
and survive across runs.

### Watchlist

Highlight any row on the FX / Crypto / Commodities tabs and press `w` to
pin it. Press `4` to see all pins across asset classes in a single
unified view, sortable the same way as any other tab. Pins persist to
`~/.config/terminex/watchlist.toml` and survive across runs.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Stdlib `unittest` only, no extra dependencies. Covers the pure-logic
modules (converter, alerts DAO & engine, watchlist, filter/sort
helpers, age formatter).

## Data sources

| Asset       | Provider            | Key required?     | Notes                              |
|-------------|---------------------|-------------------|------------------------------------|
| FX          | `open.er-api.com`   | no                | updates ~hourly                    |
| Crypto      | `rest.coincap.io`   | **yes** (free)    | top 25 by mcap, sub-minute data    |
| Commodities | `stooq.com` (CSV)   | no                | 14 futures, ~15-min delayed        |

To enable the crypto tab, [grab a free CoinCap API
key](https://coincap.io/) and export it:

```bash
export TERMINEX_COINCAP_KEY=your-key-here
```

Or put it in the config file (see below).

## Config file

terminex looks for `~/.config/terminex/config.toml` (or
`$XDG_CONFIG_HOME/terminex/config.toml`). All keys optional:

```toml
base_currency = "USD"
refresh_interval = 10
active_tab = "fx"

[providers.crypto]
api_key = "your-coincap-key"
```

Environment variables win over config file values.
