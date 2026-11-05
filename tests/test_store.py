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
            conn, warning = open_store(Path(d) / "terminex" / "terminex.db")
            self.assertIsNone(warning)
            conn.close()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write anywhere")
    def test_unwritable_dir_falls_back_to_memory(self):
        with tempfile.TemporaryDirectory() as d:
            ro = Path(d) / "ro"
            ro.mkdir()
            ro.chmod(stat.S_IRUSR | stat.S_IXUSR)
            try:
                conn, warning = open_store(ro / "terminex" / "terminex.db")
                self.assertIn(str(ro / "terminex"), warning)
                self.assertIn("won't be saved", warning)
                # schema is there, so alerts still work for the session
                conn.execute(
                    "INSERT INTO alerts (asset_class, symbol, op, threshold, created_at)"
                    " VALUES ('crypto', 'BTC', '>', 1, 'now')"
                )
                self.assertEqual(conn.execute("SELECT count(*) FROM alerts").fetchone()[0], 1)
                conn.close()
            finally:
                ro.chmod(stat.S_IRWXU)


if __name__ == "__main__":
    unittest.main()
