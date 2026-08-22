from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V15 = ROOT / "windows" / "launcher" / "app_v15.py"


class LauncherUIV15Tests(unittest.TestCase):
    def test_v15_is_presentation_only(self):
        tree = ast.parse(V15.read_text(encoding="utf-8"))
        launcher = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Launcher"
        )
        methods = {
            node.name for node in launcher.body if isinstance(node, ast.FunctionDef)
        }
        forbidden = {
            "install_current_game",
            "install_progress",
            "install_done",
            "install_cancelled",
            "install_error",
            "verify_current_game",
            "repair_done",
            "repair_error",
            "uninstall_current_game",
            "uninstall_done",
            "toggle_pause",
            "cancel_download",
            "_set_download_controls",
            "_addon_toggled",
            "_start_addon_install",
            "_start_addon_remove",
            "_addon_install_done",
            "_addon_remove_done",
            "_addon_error",
            "_addon_verify_done",
            "_addon_verify_error",
            "load_catalog",
            "open_settings",
        }
        self.assertFalse(methods & forbidden, methods & forbidden)

    def test_v15_inherits_v14_and_has_no_backend_imports(self):
        source = V15.read_text(encoding="utf-8")
        self.assertIn("import app_v14 as previous", source)
        self.assertIn('APP_VERSION = "0.15.0"', source)
        self.assertNotIn("from drowned_shared", source)
        self.assertNotIn("import drowned_shared", source)
        self.assertNotIn("release-manager", source.lower())

    def test_v15_preserves_runtime_widget_contracts(self):
        source = V15.read_text(encoding="utf-8")
        required = {
            "self.nav_library",
            "self.nav_downloads",
            "self.connection",
            "self.big_picture_button",
            "self.right_stack",
            "self.library_grid",
            "self.library_grid_bp",
            "self.install_button",
            "self.verify_button",
            "self.action_pause",
            "self.progress",
            "self.progress_text",
            "self.logs",
            "self.screenshot_gallery",
            "self.stat_platform",
            "self.stat_channel",
            "self.stat_version",
            "self.stat_size",
            "self.panel_state",
            "self.panel_path",
            "self.panel_tag",
            "self.panel_repo",
            "self.panel_branch",
        }
        missing = sorted(name for name in required if name not in source)
        self.assertFalse(missing, missing)


if __name__ == "__main__":
    unittest.main()
