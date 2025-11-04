# terminex — project notes

Terminal tool that streams exchange rates for the top 25 most-traded
currencies into a live-updating `rich` table.

## Layout

- `forex.py` — entry point; CLI parsing and the live-refresh loop
- `terminex/fetcher.py` — HTTP client for the rates API
- `terminex/display.py` — builds the `rich` table from rate snapshots
- `terminex/currencies.py` — the fixed list of 25 currency codes + names

## Conventions

- Python 3.9+, standard library + `requests` + `rich` only
- Keep modules small and single-purpose
- Commit in small, descriptive chunks
