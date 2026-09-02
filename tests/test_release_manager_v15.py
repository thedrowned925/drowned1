from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "windows" / "release-manager" / "app_v15.py"
BRIDGE = ROOT / "windows" / "release-manager" / "fdm_bridge.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class ReleaseManagerV15Tests(unittest.TestCase):
    def test_v15_adds_persistent_custom_fdm_path(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "0.15.0"', source)
        self.assertIn('form.insertRow(2, "FDM yolu", holder)', source)
        self.assertIn("QSettings", source)
        self.assertIn("set_fdm_override", source)
        self.assertIn("FDM seç", source)

    def test_bridge_can_auto_detect_running_and_override_fdm(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("def set_fdm_override", source)
        self.assertIn("def _running_fdm_executable", source)
        self.assertIn("DROWNED_FDM_PATH", source)
        self.assertIn("App Paths\\fdm.exe", source)

    def test_windows_build_supersedes_v15(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v18.py", source)


if __name__ == "__main__":
    unittest.main()
