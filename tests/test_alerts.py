"""Tests for terminex.alerts DAO and terminex.alert_engine."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from terminex import alerts
from terminex.alert_engine import AlertEngine
from terminex.quote import Quote, Snapshot
from terminex.store import connect


def _snap(quotes):
    return Snapshot(
        asset_class="fx",
        quote_ccy="USD",
        quotes=quotes,
        fetched_at=datetime.now(tz=timezone.utc),
    )


class TestAlertDao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "t.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_create_round_trip(self):
        a = alerts.create(
            self.conn,
            asset_class="fx",
            symbol="EUR",
            op=">",
            threshold=0.9,
        )
        self.assertEqual(a.symbol, "EUR")
        self.assertTrue(a.active)
        self.assertFalse(a.recurring)
        got = alerts.get(self.conn, a.id)
        self.assertEqual(got.symbol, "EUR")

    def test_list_and_count(self):
        alerts.create(self.conn, asset_class="fx", symbol="A", op="<", threshold=1.0)
        alerts.create(self.conn, asset_class="fx", symbol="B", op="<", threshold=1.0)
        self.assertEqual(alerts.count_active(self.conn), 2)
        self.assertEqual(len(alerts.list_active(self.conn)), 2)
        self.assertEqual(len(alerts.list_all(self.conn)), 2)

    def test_claim_fire_is_atomic(self):
        a = alerts.create(
            self.conn, asset_class="fx", symbol="A", op="<", threshold=1.0
        )
        self.assertTrue(alerts.claim_fire(self.conn, a, 0.5))
        self.assertFalse(alerts.claim_fire(self.conn, a, 0.5))  # already claimed
        self.assertEqual(alerts.count_active(self.conn), 0)  # one-shot: done
        self.assertEqual(len(alerts.list_all(self.conn)), 1)
        self.assertIsNotNone(alerts.get(self.conn, a.id).last_fired_at)

    def test_delete(self):
        a = alerts.create(
            self.conn, asset_class="fx", symbol="A", op="<", threshold=1.0
        )
        self.assertTrue(alerts.delete(self.conn, a.id))
        self.assertFalse(alerts.delete(self.conn, a.id))  # already gone
        self.assertEqual(len(alerts.list_all(self.conn)), 0)

    def test_create_disarmed(self):
        a = alerts.create(self.conn, asset_class="fx", symbol="A", op="<",
                          threshold=1.0, armed=False)
        self.assertFalse(a.armed)

    def test_get_missing_raises(self):
        with self.assertRaises(KeyError):
            alerts.get(self.conn, 9999)


class TestAlertEngine(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "t.db")
        self.engine = AlertEngine(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_first_observation_fires_if_condition_met(self):
        alerts.create(
            self.conn, asset_class="fx", symbol="JPY", op="<", threshold=160.0
        )
        fires = self.engine.evaluate(
            _snap([Quote("JPY", "Yen", 155.0, "USD")]), "fx"
        )
        self.assertEqual(len(fires), 1)

    def test_no_fire_while_condition_stays_true(self):
        alerts.create(
            self.conn,
            asset_class="fx",
            symbol="JPY",
            op="<",
            threshold=160.0,
            recurring=True,
        )
        self.engine.evaluate(_snap([Quote("JPY", "Y", 155.0, "USD")]), "fx")
        fires = self.engine.evaluate(
            _snap([Quote("JPY", "Y", 158.0, "USD")]), "fx"
        )
        self.assertEqual(fires, [])

    def test_re_fire_after_crossing_back_recurring(self):
        alerts.create(
            self.conn,
            asset_class="fx",
            symbol="JPY",
            op="<",
            threshold=160.0,
            recurring=True,
        )
        self.engine.evaluate(_snap([Quote("JPY", "Y", 155.0, "USD")]), "fx")  # fires
        self.engine.evaluate(_snap([Quote("JPY", "Y", 162.0, "USD")]), "fx")  # crossed above
        fires = self.engine.evaluate(
            _snap([Quote("JPY", "Y", 158.0, "USD")]), "fx"
        )  # crossed back below
        self.assertEqual(len(fires), 1)

    def test_quick_recross_then_breakout_is_not_missed(self):
        alerts.create(self.conn, asset_class="crypto", symbol="BTC", op=">",
                      threshold=100.0, recurring=True)
        q = lambda p: _snap([Quote("BTC", "Bitcoin", p, "USD")])  # noqa: E731
        self.assertEqual(len(self.engine.evaluate(q(101.0), "crypto")), 1)
        self.engine.evaluate(q(99.0), "crypto")                      # back below
        self.assertEqual(len(self.engine.evaluate(q(102.0), "crypto")), 1)  # breakout
        self.assertEqual(self.engine.evaluate(q(103.0), "crypto"), [])      # stays above

    def test_restart_does_not_refire_a_disarmed_alert(self):
        alerts.create(self.conn, asset_class="fx", symbol="JPY", op="<",
                      threshold=160.0, recurring=True)
        self.engine.evaluate(_snap([Quote("JPY", "Y", 155.0, "USD")]), "fx")  # fires
        # Long after the fire (no time window can be what holds it back):
        self.conn.execute("UPDATE alerts SET last_fired_at = '2000-01-01T00:00:00+00:00'")
        restarted = AlertEngine(self.conn)
        self.assertEqual(restarted.evaluate(_snap([Quote("JPY", "Y", 154.0, "USD")]), "fx"), [])

    def test_alert_created_disarmed_waits_for_a_crossing(self):
        alerts.create(self.conn, asset_class="fx", symbol="JPY", op="<",
                      threshold=160.0, armed=False)
        self.assertEqual(self.engine.evaluate(_snap([Quote("JPY", "Y", 155.0, "USD")]), "fx"), [])
        self.engine.evaluate(_snap([Quote("JPY", "Y", 161.0, "USD")]), "fx")  # re-arms
        self.assertEqual(len(self.engine.evaluate(_snap([Quote("JPY", "Y", 159.0, "USD")]), "fx")), 1)

    def test_non_recurring_deactivates_on_fire(self):
        alerts.create(
            self.conn,
            asset_class="fx",
            symbol="EUR",
            op=">",
            threshold=0.8,
        )
        fires = self.engine.evaluate(_snap([Quote("EUR", "E", 0.9, "USD")]), "fx")
        self.assertEqual(len(fires), 1)
        self.assertEqual(alerts.count_active(self.conn), 0)

    def test_no_fire_when_condition_false(self):
        alerts.create(
            self.conn,
            asset_class="fx",
            symbol="EUR",
            op=">",
            threshold=0.9,
        )
        fires = self.engine.evaluate(_snap([Quote("EUR", "E", 0.85, "USD")]), "fx")
        self.assertEqual(fires, [])

    def test_ignores_other_asset_classes(self):
        alerts.create(
            self.conn, asset_class="crypto", symbol="BTC", op=">", threshold=1.0
        )
        fires = self.engine.evaluate(
            _snap([Quote("BTC", "B", 100.0, "USD")]), "fx"
        )
        self.assertEqual(fires, [])



class TestTwoInstances(unittest.TestCase):
    """Two terminex windows on one database must fire an alert once."""

    def _engines(self, recurring: bool):
        import tempfile
        from pathlib import Path
        from terminex.store import connect
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "terminex.db"
        a, b = connect(path), connect(path)
        alerts.create(a, asset_class="crypto", symbol="BTC", op=">",
                          threshold=100.0, recurring=recurring)
        engines = [AlertEngine(a), AlertEngine(b)]
        below = Snapshot("crypto", "USD", [Quote("BTC", "Bitcoin", 99.0, "USD")], datetime.now(tz=timezone.utc))
        for e in engines:
            e.evaluate(below, "crypto")
        return engines, (a, b)

    def _cross(self, recurring: bool) -> int:
        engines, conns = self._engines(recurring)
        above = Snapshot("crypto", "USD", [Quote("BTC", "Bitcoin", 101.0, "USD")], datetime.now(tz=timezone.utc))
        fired = sum(len(e.evaluate(above, "crypto")) for e in engines)
        stored = conns[0].execute("SELECT count(*) FROM fires").fetchone()[0]
        for c in conns:
            c.close()
        self.tmp.cleanup()
        self.assertEqual(stored, fired)
        return fired

    def test_one_shot_fires_once(self):
        self.assertEqual(self._cross(recurring=False), 1)

    def test_recurring_fires_once_per_crossing(self):
        self.assertEqual(self._cross(recurring=True), 1)



class TestFxAlertBase(unittest.TestCase):
    """FX thresholds are in units per 1 base; the alert keeps its base."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "t.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _fx(self, base, rows):
        return Snapshot("fx", base, [Quote(s, s, p, base) for s, p in rows], datetime.now(tz=timezone.utc))

    def test_alert_created_under_usd_is_evaluated_in_usd_from_a_eur_window(self):
        alerts.create(self.conn, asset_class="fx", symbol="JPY", op="<",
                      threshold=160.0, base="USD")
        eur_window = AlertEngine(self.conn)
        # 177.0 JPY per EUR / 1.1237 USD per EUR = 157.5 JPY per USD < 160
        fires = eur_window.evaluate(self._fx("EUR", [("EUR", 1.0), ("USD", 1.1237), ("JPY", 177.0)]), "fx")
        self.assertEqual(len(fires), 1)

    def test_two_windows_with_different_bases_agree(self):
        alerts.create(self.conn, asset_class="fx", symbol="JPY", op="<",
                      threshold=160.0, base="USD", recurring=True)
        usd, eur = AlertEngine(self.conn), AlertEngine(self.conn)
        fired = 0
        for _ in range(6):
            fired += len(usd.evaluate(self._fx("USD", [("USD", 1.0), ("JPY", 150.0)]), "fx"))
            fired += len(eur.evaluate(self._fx("EUR", [("EUR", 1.0), ("USD", 1.1), ("JPY", 165.0)]), "fx"))
        self.assertEqual(fired, 1)  # 165/1.1 = 150 JPY per USD: same view, one fire


if __name__ == "__main__":
    unittest.main()
