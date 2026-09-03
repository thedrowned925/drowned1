from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "windows" / "release-manager"
APP = RELEASE_DIR / "app_v17.py"
UI = RELEASE_DIR / "fdm_ui_v3.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class ReleaseManagerV17Tests(unittest.TestCase):
    def test_v17_only_replaces_fdm_submission_layer(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "0.17.0"', source)
        self.assertIn("import app_v16 as previous", source)
        self.assertIn("fdm_ui_v3.install()", source)

    def test_v17_clipboard_bridge_does_not_find_toolbar_button(self):
        source = UI.read_text(encoding="utf-8")
        self.assertIn("_clipboard_set_text(url)", source)
        self.assertIn('send_keys("^v")', source)
        self.assertIn("_focus_download_canvas", source)
        self.assertIn("_configure_second_dialog", source)
        self.assertNotIn('send_keys("^j")', source)
        self.assertNotIn("_find_add_button", source)
        self.assertNotIn("ADD_BUTTON_TEXTS", source)
        self.assertNotIn("capture_as_image", source)

    def test_windows_build_supersedes_v17(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v20.py", workflow)
        self.assertIn("python -m py_compile windows/release-manager/fdm_ui_v3.py", workflow)


if __name__ == "__main__":
    unittest.main()
