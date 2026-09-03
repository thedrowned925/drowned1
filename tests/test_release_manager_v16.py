from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "windows" / "release-manager"
APP = RELEASE_DIR / "app_v16.py"
UI = RELEASE_DIR / "fdm_ui_v2.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class ReleaseManagerV16Tests(unittest.TestCase):
    def test_v16_installs_only_fdm_ui_submission_fix(self):
        source = APP.read_text(encoding="utf-8")
        tree = ast.parse(source)
        manager = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Manager")
        methods = {node.name for node in manager.body if isinstance(node, ast.FunctionDef)}
        self.assertEqual(methods, {"__init__"})
        self.assertIn('APP_VERSION = "0.16.0"', source)
        self.assertIn("fdm_ui_v2.install()", source)
        self.assertIn("import app_v15 as previous", source)

    def test_fdm_flow_clicks_add_download_and_never_ctrl_j(self):
        source = UI.read_text(encoding="utf-8")
        self.assertIn('ADD_BUTTON_TEXTS = {"indirme ekle", "add download"}', source)
        self.assertIn("add_button.click_input()", source)
        self.assertIn("FIRST_CONFIRM_TEXTS", source)
        self.assertIn("confirm.click_input()", source)
        self.assertIn("URL_LABEL_TOKENS", source)
        self.assertIn("root_rect.top + 70", source)
        self.assertNotIn('send_keys("^j")', source)
        self.assertNotIn("send_keys('^j')", source)

    def test_fdm_flow_handles_save_to_destination_before_start(self):
        source = UI.read_text(encoding="utf-8")
        self.assertIn("FOLDER_LABEL_TOKENS", source)
        self.assertIn("_pick_destination_control", source)
        self.assertIn("_set_value(destination, str(target_dir))", source)
        self.assertIn("action.click_input()", source)
        self.assertIn("_database_has_url", source)

    def test_windows_build_supersedes_v16(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v21.py", workflow)
        self.assertIn("python -m py_compile windows/release-manager/fdm_ui_v2.py", workflow)


if __name__ == "__main__":
    unittest.main()
