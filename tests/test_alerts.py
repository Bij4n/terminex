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

    def test_deactivate(self):
        a = alerts.create(
            self.conn, asset_class="fx", symbol="A", op="<", threshold=1.0
        )
        alerts.deactivate(self.conn, a.id)
        self.assertEqual(alerts.count_active(self.conn), 0)
        # Still present in list_all
        self.assertEqual(len(alerts.list_all(self.conn)), 1)

    def test_delete(self):
        a = alerts.create(
            self.conn, asset_class="fx", symbol="A", op="<", threshold=1.0
        )
        self.assertTrue(alerts.delete(self.conn, a.id))
        self.assertFalse(alerts.delete(self.conn, a.id))  # already gone
        self.assertEqual(len(alerts.list_all(self.conn)), 0)

    def test_record_fire_updates_last_fired_at(self):
        a = alerts.create(
            self.conn, asset_class="fx", symbol="A", op="<", threshold=1.0
        )
        alerts.record_fire(self.conn, a.id, 0.5)
        refreshed = alerts.get(self.conn, a.id)
        self.assertIsNotNone(refreshed.last_fired_at)

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
        # Past the cooldown, crossing back below fires again.
        self.conn.execute("UPDATE alerts SET last_fired_at = '2000-01-01T00:00:00+00:00'")
        fires = self.engine.evaluate(
            _snap([Quote("JPY", "Y", 158.0, "USD")]), "fx"
        )  # crossed back below
        self.assertEqual(len(fires), 1)

    def test_recurring_cooldown_suppresses_rapid_refires(self):
        alerts.create(self.conn, asset_class="fx", symbol="JPY", op="<",
                      threshold=160.0, recurring=True)
        self.engine.evaluate(_snap([Quote("JPY", "Y", 155.0, "USD")]), "fx")  # fires
        self.engine.evaluate(_snap([Quote("JPY", "Y", 162.0, "USD")]), "fx")
        fires = self.engine.evaluate(_snap([Quote("JPY", "Y", 158.0, "USD")]), "fx")
        self.assertEqual(fires, [])  # hovering at the threshold doesn't spam

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


if __name__ == "__main__":
    unittest.main()
