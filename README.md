# terminex

A terminal tool that displays live-updating exchange rates for the top 25
most-traded foreign currencies (per the BIS triennial FX survey).

## Requirements

- Python 3.9+
- `requests`, `rich` (see `requirements.txt`)

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 forex.py
```

Press `Ctrl+C` to quit.

### Options

- `--base USD` — base currency (default: `USD`)
- `--interval 10` — refresh interval in seconds (default: `10`)

## Data source

Rates are fetched from the free [open.er-api.com](https://open.er-api.com)
endpoint. The public feed updates roughly once per hour; the app polls at the
configured interval and highlights any change since the previous tick.

## Currencies shown

USD, EUR, JPY, GBP, CNY, AUD, CAD, CHF, HKD, SGD, SEK, KRW, NOK, NZD, INR,
MXN, TWD, ZAR, BRL, DKK, PLN, THB, ILS, IDR, CZK.
