"""Record trimmed real API responses as test fixtures.

Runs each provider's real ``fetch()`` and captures the HTTP response it
gets, so a fixture is exactly what terminex requests (same URL, params
and headers). Responses are trimmed to a few rows to keep the repo small.

    python scripts/record_fixtures.py            # all keyless providers
    TERMINEX_COINCAP_KEY=... python scripts/record_fixtures.py

Fixtures land in tests/fixtures/<provider>.json. Re-record when a
provider's format changes on purpose; the parse tests then show the diff.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminex.providers.commodities_yahoo import CommoditiesYahoo  # noqa: E402
from terminex.providers.crypto_coincap import CryptoCoinCap  # noqa: E402
from terminex.providers.crypto_coingecko import CryptoCoinGecko  # noqa: E402
from terminex.providers.fx_erapi import FxERApi  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
KEEP_ROWS = 5
KEEP_FUTURES = ("GC=F", "SI=F", "ZW=F")  # a metal in $, one quoted in cents


def _trim_coingecko(payload):
    return payload[:KEEP_ROWS]


def _trim_coincap(payload):
    return {**payload, "data": payload.get("data", [])[:KEEP_ROWS]}


def _trim_yahoo(payload):
    return {sym: payload[sym] for sym in KEEP_FUTURES if sym in payload}


def _trim_erapi(payload):
    return payload  # one small object; keep every rate


def record(name: str, provider, trim) -> None:
    real_get = requests.get
    captured = {}

    def capturing_get(url, *args, **kwargs):
        resp = real_get(url, *args, **kwargs)
        captured.update(url=url, params=kwargs.get("params"), status=resp.status_code,
                        payload=resp.json())
        return resp

    with mock.patch("requests.get", capturing_get):
        snap = provider.fetch()
    fixture = {
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "url": captured["url"],
        "params": captured["params"],
        "payload": trim(captured["payload"]),
    }
    path = FIXTURES / f"{name}.json"
    path.write_text(json.dumps(fixture, indent=1, sort_keys=True) + "\n")
    print(f"{name}: {len(snap.quotes)} quotes live, saved {path.relative_to(ROOT)} "
          f"({path.stat().st_size // 1024} KB)")


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    record("erapi", FxERApi(), _trim_erapi)
    record("coingecko", CryptoCoinGecko(), _trim_coingecko)
    record("yahoo_spark", CommoditiesYahoo(), _trim_yahoo)
    key = os.environ.get("TERMINEX_COINCAP_KEY")
    if key:
        record("coincap", CryptoCoinCap(api_key=key), _trim_coincap)
    else:
        print("coincap: skipped (set TERMINEX_COINCAP_KEY to record it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
