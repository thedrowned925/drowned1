from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V14 = ROOT / "windows" / "launcher" / "app_v14.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class LauncherUIV14Tests(unittest.TestCase):
    def test_v14_keeps_backend_methods_inherited(self):
        tree = ast.parse(V14.read_text(encoding="utf-8"))
        launcher = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Launcher")
        methods = {node.name for node in launcher.body if isinstance(node, ast.FunctionDef)}
        forbidden = {
            "install_current_game", "install_progress", "install_done", "install_cancelled",
            "install_error", "verify_current_game", "repair_done", "repair_error",
            "uninstall_current_game", "uninstall_done", "toggle_pause", "cancel_download",
            "_set_download_controls", "_addon_toggled", "_start_addon_install",
            "_start_addon_remove", "_addon_install_done", "_addon_remove_done",
            "_addon_error", "_addon_verify_done", "_addon_verify_error", "load_catalog",
            "open_settings",
        }
        self.assertFalse(methods & forbidden, methods & forbidden)

    def test_v14_does_not_import_backend_or_release_manager(self):
        source = V14.read_text(encoding="utf-8")
        self.assertNotIn("from drowned_shared", source)
        self.assertNotIn("import drowned_shared", source)
        self.assertNotIn("release-manager", source.lower())
        self.assertIn("import app_v12 as previous", source)
        self.assertIn('APP_VERSION = "0.14.0"', source)

    def test_windows_build_keeps_release_manager_and_uses_latest_launcher_ui(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v20.py", workflow)
        self.assertIn("dir: windows/launcher\n            entry: app_v18.py", workflow)


if __name__ == "__main__":
    unittest.main()
