from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V17 = ROOT / "windows" / "launcher" / "app_v17.py"


class LauncherUIV17Tests(unittest.TestCase):
    def test_v17_is_presentation_only(self):
        tree = ast.parse(V17.read_text(encoding="utf-8"))
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
            "render_library",
            "library_selection_changed",
        }
        self.assertFalse(methods & forbidden, methods & forbidden)

    def test_v17_inherits_v16_and_has_no_backend_imports(self):
        source = V17.read_text(encoding="utf-8")
        self.assertIn("import app_v16 as previous", source)
        self.assertIn('APP_VERSION = "0.17.0"', source)
        self.assertNotIn("from drowned_shared", source)
        self.assertNotIn("import drowned_shared", source)
        self.assertNotIn("release-manager", source.lower())

    def test_v17_makes_big_picture_shell_the_default_view(self):
        """The whole point of v17: Epic/Steam-style capsule grid on launch,
        not hidden behind the old F11 kiosk-mode toggle."""
        source = V17.read_text(encoding="utf-8")
        self.assertIn("self._show_epic_home()", source)
        self.assertIn("self.big_picture.show()", source, "reparented big_picture must be un-hidden explicitly")
        self.assertIn("self._show_classic_shell", source, "must keep an explicit way back to the old list-rail UI")

    # Whether the Windows build actually points at v17 is superseded by
    # app_v18 (see test_launcher_ui_v18.py); this file only asserts
    # properties of v17's own source, not which version ships.


if __name__ == "__main__":
    unittest.main()
