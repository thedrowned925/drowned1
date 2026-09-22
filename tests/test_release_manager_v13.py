from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "windows" / "release-manager" / "app_v13.py"
DOWNLOADER = ROOT / "windows" / "release-manager" / "game_download_v2.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class ReleaseManagerV13Tests(unittest.TestCase):
    def test_v13_is_download_only_wrapper(self):
        source = APP.read_text(encoding="utf-8")
        tree = ast.parse(source)
        manager = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Manager")
        methods = {node.name for node in manager.body if isinstance(node, ast.FunctionDef)}
        self.assertEqual(methods, {"__init__"})
        self.assertIn("game_prepare_base.ParallelDownloader = ProgressiveParallelDownloader", source)
        self.assertIn('APP_VERSION = "0.13.0"', source)

    def test_gigabit_defaults_and_no_full_size_preallocation(self):
        source = DOWNLOADER.read_text(encoding="utf-8")
        self.assertIn("return 16", source)
        self.assertIn("SEGMENT_BYTES = 64 * MIB", source)
        self.assertIn("NETWORK_BLOCK = 4 * MIB", source)
        self.assertIn("gerçek indirilen veri", source)
        self.assertNotIn("truncate(probe.size)", source)
        self.assertIn("shutil.copyfileobj", source)
        self.assertIn("seg_path.unlink", source)

    def test_latest_windows_build_supersedes_v13(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v21.py", workflow)


if __name__ == "__main__":
    unittest.main()
