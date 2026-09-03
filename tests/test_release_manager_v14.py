from __future__ import annotations

import ast
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "windows" / "release-manager"
APP = RELEASE_DIR / "app_v14.py"
BRIDGE = RELEASE_DIR / "fdm_bridge.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"
REQUIREMENTS = RELEASE_DIR / "requirements.txt"

HAS_PSUTIL = importlib.util.find_spec("psutil") is not None
if HAS_PSUTIL:
    sys.path.insert(0, str(RELEASE_DIR))
    from fdm_bridge import FdmDatabaseReader  # noqa: E402
else:
    FdmDatabaseReader = None


class ReleaseManagerV14Tests(unittest.TestCase):
    def test_v14_only_replaces_download_transport(self):
        source = APP.read_text(encoding="utf-8")
        tree = ast.parse(source)
        manager = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Manager")
        methods = {node.name for node in manager.body if isinstance(node, ast.FunctionDef)}
        self.assertEqual(methods, {"__init__"})
        self.assertIn("game_prepare_base.ParallelDownloader = FdmDownloader", source)
        self.assertIn('APP_VERSION = "0.14.0"', source)
        self.assertIn("FDM tarafından yönetiliyor", source)

    @unittest.skipUnless(HAS_PSUTIL, "FDM runtime dependencies are installed only in Release Manager matrix job")
    def test_fdm_reader_uses_fdm_database_progress_and_speed(self):
        assert FdmDatabaseReader is not None
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "fdm.sqlite"
            target = root / "downloads"
            target.mkdir()
            url = "https://example.test/files/game.rar"
            output = target / "game.rar"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE downloads (url TEXT, target_path TEXT, total_bytes INTEGER, downloaded_bytes INTEGER, speed INTEGER, status TEXT, connections INTEGER)")
            connection.execute("INSERT INTO downloads VALUES (?, ?, ?, ?, ?, ?, ?)", (url, str(output), 1000, 250, 125, "downloading", 16))
            connection.commit()
            connection.close()
            reader = FdmDatabaseReader(database, url, "game.rar", target)
            snapshot = reader.snapshot(1000)
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(snapshot.done, 250)
            self.assertEqual(snapshot.total, 1000)
            self.assertEqual(snapshot.speed, 125)
            self.assertEqual(snapshot.connections, 16)
            self.assertFalse(snapshot.completed)
            connection = sqlite3.connect(database)
            connection.execute("UPDATE downloads SET downloaded_bytes = 1000, status = 'completed'")
            connection.commit()
            connection.close()
            snapshot = reader.snapshot(1000)
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(snapshot.done, 1000)
            self.assertTrue(snapshot.completed)

    def test_bridge_reads_fdm_state_not_download_file_for_telemetry(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("class FdmDatabaseReader", source)
        self.assertIn("mode=ro", source)
        self.assertIn("derived_speed", source)
        self.assertIn("FDM download kaydı", source)
        self.assertNotIn("output.stat().st_size -", source)

    def test_windows_build_packages_fdm_bridge_and_latest_manager(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v20.py", workflow)
        self.assertIn("python -m py_compile windows/release-manager/fdm_bridge.py", workflow)
        self.assertIn('Pattern "fdm_bridge"', workflow)
        self.assertIn('Pattern "pywinauto"', workflow)
        self.assertIn("pywinauto>=0.6.9,<0.7", requirements)


if __name__ == "__main__":
    unittest.main()
