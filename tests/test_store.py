"""Opening the SQLite store, including when the data directory is unwritable."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from terminex.store import open_store


class TestOpenStore(unittest.TestCase):
    def test_writable_path(self):
        with tempfile.TemporaryDirectory() as d:
            conn, notices = open_store(Path(d) / "terminex" / "terminex.db")
            self.assertEqual(notices, [])
            conn.close()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write anywhere")
    def test_unwritable_dir_falls_back_to_memory(self):
        with tempfile.TemporaryDirectory() as d:
            ro = Path(d) / "ro"
            ro.mkdir()
            ro.chmod(stat.S_IRUSR | stat.S_IXUSR)
            try:
                conn, notices = open_store(ro / "terminex" / "terminex.db")
                self.assertIn(str(ro / "terminex"), notices[0])
                self.assertIn("won't be saved", notices[0])
                # schema is there, so alerts still work for the session
                conn.execute(
                    "INSERT INTO alerts (asset_class, symbol, op, threshold, created_at)"
                    " VALUES ('crypto', 'BTC', '>', 1, 'now')"
                )
                self.assertEqual(conn.execute("SELECT count(*) FROM alerts").fetchone()[0], 1)
                conn.close()
            finally:
                ro.chmod(stat.S_IRWXU)



class TestCommodityUnitMigration(unittest.TestCase):
    """0.4.0 databases hold commodity thresholds in Stooq's cents."""

    def _old_db(self, path: Path) -> None:
        import sqlite3
        from terminex.store import SCHEMA
        path.parent.mkdir(parents=True)
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA)
        rows = [
            ("commodity", "SI.F", 3205.0),   # cents/oz -> 32.05
            ("commodity", "ZW.F", 590.0),    # cents/bu -> 5.90
            ("commodity", "SB.F", 0.2),      # already dollars: keep
            ("commodity", "GC.F", 4000.0),   # gold was always dollars
            ("crypto", "BTC", 80000.0),
        ]
        conn.executemany(
            "INSERT INTO alerts (asset_class, symbol, op, threshold, created_at)"
            " VALUES (?, ?, '>', ?, 'then')", rows,
        )
        conn.execute(
            "INSERT INTO prices (asset_class, symbol, price, recorded_at)"
            " VALUES ('commodity', 'SI.F', 3205.0, 'then')"
        )
        conn.commit()
        conn.close()

    def test_cent_thresholds_converted_once_with_a_notice(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "terminex" / "terminex.db"
            self._old_db(path)
            conn, notices = open_store(path)
            got = dict(conn.execute("SELECT symbol, threshold FROM alerts").fetchall())
            self.assertEqual(got, {"SI.F": 32.05, "ZW.F": 5.9, "SB.F": 0.2, "GC.F": 4000.0, "BTC": 80000.0})
            self.assertEqual(conn.execute("SELECT count(*) FROM prices WHERE asset_class='commodity'").fetchone()[0], 0)
            self.assertEqual(len(notices), 1)
            self.assertIn("SI.F 3205 → 32.05", notices[0])
            self.assertIn("ZW.F 590 → 5.9", notices[0])
            conn.close()
            conn, notices = open_store(path)  # second start: nothing to do
            self.assertEqual(notices, [])
            self.assertEqual(conn.execute("SELECT threshold FROM alerts WHERE symbol='SI.F'").fetchone()[0], 32.05)
            conn.close()



class TestArmedColumnMigration(unittest.TestCase):
    def test_old_alerts_table_gains_armed(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "terminex" / "terminex.db"
            path.parent.mkdir(parents=True)
            old = sqlite3.connect(path)
            old.executescript(
                "CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " asset_class TEXT NOT NULL, symbol TEXT NOT NULL, op TEXT NOT NULL,"
                " threshold REAL NOT NULL, recurring INTEGER NOT NULL DEFAULT 0,"
                " active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,"
                " last_fired_at TEXT);"
                "INSERT INTO alerts (asset_class, symbol, op, threshold, created_at)"
                " VALUES ('crypto', 'BTC', '>', 1, 'then');"
            )
            old.commit()
            old.close()
            conn, _ = open_store(path)
            self.assertEqual(conn.execute("SELECT armed FROM alerts").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            conn.close()


if __name__ == "__main__":
    unittest.main()
