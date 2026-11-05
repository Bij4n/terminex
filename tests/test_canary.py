"""The live-feed canary (scripts/canary.py) with fake providers and a fake gh."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from terminex.providers.base import Provider, ProviderError, RateLimitError
from terminex.quote import Quote, Snapshot

_spec = importlib.util.spec_from_file_location(
    "canary", Path(__file__).resolve().parent.parent / "scripts" / "canary.py")
canary = importlib.util.module_from_spec(_spec)
sys.modules["canary"] = canary  # dataclasses look their module up here
_spec.loader.exec_module(canary)


class Scripted(Provider):
    """Returns or raises the scripted outcomes in order."""

    asset_class = "crypto"

    def __init__(self, name, *outcomes):
        self.name = name
        self.outcomes = list(outcomes)

    def fetch(self):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def snap(symbols, history=True):
    quotes = [Quote(s, s, 100.0, "USD", 1.0, meta={"history": [99.0, 100.0]} if history else {})
              for s in symbols]
    return Snapshot("crypto", "USD", quotes, datetime.now(tz=timezone.utc))


GOOD = [f"C{i}" for i in range(18)] + ["BTC", "ETH"]


def check(provider, **kw):
    spec = canary.Check(provider=provider, min_rows=20, required={"BTC", "ETH"}, history=True)
    return canary.run_check(spec, delays=(0, 0), **kw)


class TestChecks(unittest.TestCase):
    def test_healthy_feed(self):
        self.assertEqual(check(Scripted("feed", snap(GOOD))).status, "ok")

    def test_missing_symbol_fails(self):
        result = check(Scripted("feed", snap(GOOD[:-1] + ["XRP"])))
        self.assertEqual(result.status, "failing")
        self.assertIn("ETH", result.detail)

    def test_too_few_rows_fails(self):
        self.assertEqual(check(Scripted("feed", snap(["BTC", "ETH"]))).status, "failing")

    def test_missing_history_fails(self):
        self.assertEqual(check(Scripted("feed", snap(GOOD, history=False))).status, "failing")

    def test_transient_error_is_retried(self):
        result = check(Scripted("feed", ProviderError("timeout"), snap(GOOD)))
        self.assertEqual(result.status, "ok")

    def test_persistent_error_fails(self):
        errors = [ProviderError("can't reach feed")] * 3
        result = check(Scripted("feed", *errors))
        self.assertEqual(result.status, "failing")
        self.assertIn("can't reach feed", result.detail)

    def test_persistent_rate_limit_is_its_own_status(self):
        limits = [RateLimitError("429", retry_after=1)] * 3
        self.assertEqual(check(Scripted("feed", *limits)).status, "rate-limited")

    def test_unexpected_exception_is_a_failure_not_a_crash(self):
        result = check(Scripted("feed", AttributeError("'list' object has no attribute 'get'")))
        self.assertEqual(result.status, "failing")
        self.assertIn("AttributeError", result.detail)

    def test_simulated_failure(self):
        result = check(Scripted("feed", snap(GOOD)), simulate_failure=True)
        self.assertEqual(result.status, "failing")
        self.assertIn("simulated", result.detail)


class FakeGh:
    def __init__(self, open_issues=()):
        self.open = {title: n for n, title in enumerate(open_issues, start=1)}
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            import json
            return json.dumps([{"number": n, "title": t} for t, n in self.open.items()])
        return ""

    def actions(self):
        return [c[:2] for c in self.calls if c[:2] != ("issue", "list") and c[0] != "label"]


class TestIssues(unittest.TestCase):
    def result(self, status):
        return canary.Result(name="coingecko.com", status=status, detail="details")

    def test_new_failure_opens_an_issue(self):
        gh = FakeGh()
        canary.manage_issues([self.result("failing")], gh=gh)
        self.assertEqual(gh.actions(), [("issue", "create")])
        create = [c for c in gh.calls if c[:2] == ("issue", "create")][0]
        self.assertIn("canary: coingecko.com failing", create)

    def test_ongoing_failure_comments_on_the_open_issue(self):
        gh = FakeGh(["canary: coingecko.com failing"])
        canary.manage_issues([self.result("failing")], gh=gh)
        self.assertEqual(gh.actions(), [("issue", "comment")])

    def test_recovery_closes_the_issue(self):
        gh = FakeGh(["canary: coingecko.com failing"])
        canary.manage_issues([self.result("ok")], gh=gh)
        self.assertEqual(gh.actions(), [("issue", "close")])

    def test_rate_limited_run_does_not_close_an_open_issue(self):
        gh = FakeGh(["canary: coingecko.com failing"])
        canary.manage_issues([self.result("rate-limited")], gh=gh)
        self.assertEqual(gh.actions(), [])

    def test_one_gh_failure_does_not_stop_the_others(self):
        import subprocess
        calls = []

        def flaky_gh(*args):
            calls.append(args)
            if args[:2] == ("issue", "list"):
                return "[]"
            if args[:2] == ("issue", "create") and "canary: first.com failing" in args:
                raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 403: Resource not accessible")
            return ""

        results = [canary.Result("first.com", "failing", "x"), canary.Result("second.com", "failing", "y")]
        errors = canary.manage_issues(results, gh=flaky_gh)
        created = [a for a in calls if a[:2] == ("issue", "create")]
        self.assertEqual(len(created), 2)                      # second still attempted
        self.assertEqual(len(errors), 1)
        self.assertIn("HTTP 403", errors[0])

    def test_healthy_or_rate_limited_feeds_open_nothing(self):
        gh = FakeGh()
        canary.manage_issues([self.result("ok"), self.result("rate-limited")], gh=gh)
        self.assertEqual(gh.actions(), [])



class TestMain(unittest.TestCase):
    def test_summary_includes_gh_errors_and_exit_is_nonzero(self):
        import tempfile
        from unittest import mock
        healthy = canary.Check(Scripted("feed.com", snap(GOOD)), min_rows=20, required={"BTC"})
        with tempfile.NamedTemporaryFile("r+", suffix=".md") as summary, \
                mock.patch.object(canary, "default_checks", return_value=[healthy]), \
                mock.patch.object(canary, "manage_issues", return_value=["feed.com: HTTP 403"]), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            code = canary.main(["--manage-issues", "--summary", summary.name])
            text = open(summary.name).read()
        self.assertEqual(code, 1)
        self.assertIn("Issue updates failed", text)
        self.assertIn("HTTP 403", text)


if __name__ == "__main__":
    unittest.main()
