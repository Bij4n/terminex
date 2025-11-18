# terminex

A terminal dashboard for live prices across three asset classes:

- **FX** — top 25 most-traded currencies (BIS triennial survey)
- **Crypto** — top 25 coins by market cap
- **Commodities** — metals, energy, and agriculturals futures

## Requirements

- Python 3.11+ (uses `tomllib`)
- `requests`, `rich`

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 -m terminex
# or, legacy entry point:
python3 forex.py
```

### Keys

| Key   | Action                |
|-------|-----------------------|
| `1`   | FX tab                |
| `2`   | Crypto tab            |
| `3`   | Commodities tab       |
| `r`   | Force refresh now     |
| `q`   | Quit                  |

### CLI options

- `--base USD` — FX base currency (default: `USD`)
- `--tab fx|crypto|commodity` — tab to start on
- `--interval 10` — refresh interval in seconds

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
