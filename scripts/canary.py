"""Check every live data feed and report failures as GitHub issues.

Runs each provider's real ``fetch()`` and checks the result looks right:
enough rows, the symbols everyone expects, prices, and history where the
feed provides it. A transient error or rate limit is retried with backoff
before it counts.

    python scripts/canary.py                       # print a report
    python scripts/canary.py --manage-issues       # also open/close issues (needs gh + GH_TOKEN)
    python scripts/canary.py --simulate-failure coingecko.com   # test the issue flow

Exit status is 1 if any feed is failing or, with --manage-issues, if a gh
call failed. A feed that is only rate limited (likely the CI runner's
shared address) is reported but is not a failure.
Runs daily from .github/workflows/canary.yml.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminex.providers.base import Provider, ProviderError, RateLimitError  # noqa: E402

LABEL = "canary"
DELAYS = (30.0, 90.0)  # seconds to wait before the 2nd and 3rd attempts


@dataclass
class Check:
    provider: Provider
    min_rows: int
    required: set[str] = field(default_factory=set)
    history: bool = False


@dataclass
class Result:
    name: str
    status: str  # "ok" | "failing" | "rate-limited"
    detail: str


def default_checks() -> list[Check]:
    from terminex.providers.commodities_yahoo import HOSTS, CommoditiesYahoo
    from terminex.providers.crypto_coincap import CryptoCoinCap
    from terminex.providers.crypto_coingecko import CryptoCoinGecko
    from terminex.providers.crypto_coinlore import CryptoCoinLore
    from terminex.providers.fx_erapi import FxERApi

    # Every feed separately, fallbacks included: a fallback that has quietly
    # died is no fallback.
    futures = {"GC.F", "CL.F", "ZW.F"}
    checks = [
        Check(FxERApi(), min_rows=25, required={"USD", "EUR", "JPY", "GBP"}),
        Check(CryptoCoinGecko(), min_rows=20, required={"BTC", "ETH"}, history=True),
        Check(CryptoCoinLore(), min_rows=20, required={"BTC", "ETH"}),
        *(Check(CommoditiesYahoo(host=h), min_rows=12, required=futures, history=True)
          for h in HOSTS),
    ]
    key = os.environ.get("TERMINEX_COINCAP_KEY")
    if key:
        checks.append(Check(CryptoCoinCap(api_key=key), min_rows=20, required={"BTC", "ETH"}))
    return checks


def _problems(check: Check, snapshot) -> list[str]:
    problems = []
    symbols = {q.symbol for q in snapshot.quotes}
    if len(snapshot.quotes) < check.min_rows:
        problems.append(f"only {len(snapshot.quotes)} rows (expected at least {check.min_rows})")
    missing = sorted(check.required - symbols)
    if missing:
        problems.append(f"missing {', '.join(missing)}")
    if check.history:
        without = sorted(q.symbol for q in snapshot.quotes if len(q.meta.get("history") or []) < 2)
        if without:
            problems.append(f"no history for {', '.join(without[:5])}")
    return problems


def run_check(
    check: Check,
    delays: Sequence[float] = DELAYS,
    simulate_failure: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> Result:
    name = check.provider.name
    if simulate_failure:
        return Result(name, "failing", "simulated failure (--simulate-failure)")
    last_error: Exception | None = None
    for attempt in range(len(delays) + 1):
        if attempt:
            sleep(delays[attempt - 1])
        try:
            snapshot = check.provider.fetch()
        except ProviderError as exc:  # RateLimitError included
            last_error = exc
            continue
        except Exception as exc:  # a changed format can surface as any error
            return Result(name, "failing", f"{type(exc).__name__}: {exc}")
        problems = _problems(check, snapshot)
        if not problems:
            return Result(name, "ok", f"{len(snapshot.quotes)} rows")
        return Result(name, "failing", "; ".join(problems))
    if isinstance(last_error, RateLimitError):
        return Result(name, "rate-limited", str(last_error))
    return Result(name, "failing", str(last_error))


def _title(name: str) -> str:
    return f"canary: {name} failing"


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _gh_error(exc: Exception) -> str:
    stderr = getattr(exc, "stderr", "") or ""
    return f"{exc}: {stderr.strip()}" if stderr else str(exc)


def manage_issues(results: list[Result], gh: Callable[..., str] = _gh) -> list[str]:
    """One open issue per failing feed; comment while it fails, close on recovery.

    Each feed is handled on its own: a gh failure for one (permissions,
    Issues disabled) is collected and the rest still go ahead. Returns the
    gh errors, if any.
    """
    errors: list[str] = []
    try:
        gh("label", "create", LABEL, "--color", "B60205",
           "--description", "Live data feed check", "--force")
        listed = json.loads(gh("issue", "list", "--label", LABEL, "--state", "open",
                               "--json", "number,title", "--limit", "100") or "[]")
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        return [f"listing canary issues: {_gh_error(exc)}"]
    open_issues = {issue["title"]: str(issue["number"]) for issue in listed}
    run_url = _run_url()
    for result in results:
        number = open_issues.get(_title(result.name))
        try:
            if result.status == "failing":
                if number:
                    gh("issue", "comment", number, "--body",
                       f"Still failing: `{result.detail}`\n\n{run_url}")
                else:
                    body = (f"The daily canary could not get good data from "
                            f"**{result.name}**.\n\n`{result.detail}`\n\n{run_url}")
                    gh("issue", "create", "--title", _title(result.name),
                       "--label", LABEL, "--body", body)
            elif result.status == "ok" and number:
                gh("issue", "close", number, "--comment",
                   f"Recovered: {result.detail}.\n\n{run_url}")
        except (subprocess.CalledProcessError, OSError) as exc:
            errors.append(f"{result.name}: {_gh_error(exc)}")
    return errors


def _run_url() -> str:
    server, repo, run = (os.environ.get(k) for k in
                         ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"Run: {server}/{repo}/actions/runs/{run}" if server and repo and run else ""


def _report(results: list[Result]) -> str:
    icons = {"ok": "✅", "failing": "❌", "rate-limited": "⚠️"}
    lines = ["| Feed | Status | Detail |", "|---|---|---|"]
    lines += [f"| {r.name} | {icons[r.status]} {r.status} | {r.detail} |" for r in results]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manage-issues", action="store_true",
                        help="open, update and close GitHub issues (needs gh and GH_TOKEN)")
    parser.add_argument("--summary", metavar="FILE",
                        help="append a markdown report (e.g. $GITHUB_STEP_SUMMARY)")
    parser.add_argument("--simulate-failure", metavar="FEED", default="",
                        help="report this feed (e.g. coingecko.com) as failing, to test the issue flow")
    args = parser.parse_args(argv)

    results = [
        run_check(check, simulate_failure=check.provider.name == args.simulate_failure)
        for check in default_checks()
    ]
    gh_errors = manage_issues(results) if args.manage_issues else []
    report = _report(results)
    if gh_errors:
        report += "\n\n**Issue updates failed:**\n\n" + "\n".join(f"- {e}" for e in gh_errors)
    print(report)
    for error in gh_errors:
        print(f"gh error: {error}", file=sys.stderr)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write("## terminex feed canary\n\n" + report + "\n")
    return 1 if gh_errors or any(r.status == "failing" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
