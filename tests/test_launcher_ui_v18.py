from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V18 = ROOT / "windows" / "launcher" / "app_v18.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class LauncherUIV18Tests(unittest.TestCase):
    def test_v18_is_presentation_only(self):
        tree = ast.parse(V18.read_text(encoding="utf-8"))
        launcher = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Launcher"
        )
        methods = {
            node.name for node in launcher.body if isinstance(node, ast.FunctionDef)
        }
        forbidden = {
            "install_current_game",
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
            "install_progress",
        }
        self.assertFalse(methods & forbidden, methods & forbidden)

    def test_v18_inherits_v16_and_has_no_backend_imports(self):
        source = V18.read_text(encoding="utf-8")
        self.assertIn("import app_v16 as previous", source)
        self.assertIn('APP_VERSION = "0.18.0"', source)
        self.assertNotIn("from drowned_shared", source)
        self.assertNotIn("import drowned_shared", source)
        self.assertNotIn("release-manager", source.lower())

    def test_v18_does_not_reuse_library_grid_widgets(self):
        """The whole point of v18: freshly painted tile/grid/hero widgets,
        not the GameCapsule/GameGridView/BigPictureView classes v10-v17 all
        shared. This is a deliberately narrow check standing in for "built
        from scratch, not wrapped"."""
        source = V18.read_text(encoding="utf-8")
        self.assertNotIn("library_grid.GameCapsule", source)
        self.assertNotIn("BASE.GameGridView", source)
        self.assertNotIn("BASE.BigPictureView", source)
        for fresh_class in ("class EpicTile", "class EpicGrid", "class EpicTopBar", "class EpicHeroBanner"):
            self.assertIn(fresh_class, source)

    def test_v18_wires_fresh_widgets_into_existing_extension_points(self):
        source = V18.read_text(encoding="utf-8")
        for hook in (
            "def render_library(self):",
            "def library_selection_changed(self, current, previous_item):",
            "def _apply_cover(self, key, pixmap):",
            "def update_install_state_ui(self):",
        ):
            self.assertIn(hook, source)
        for real_action in (
            "self.install_current_game",
            "self.verify_current_game",
            "self.uninstall_current_game",
            "self.toggle_pause",
            "self.cancel_download",
        ):
            self.assertIn(real_action, source)

    def test_windows_build_uses_v18(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/launcher\n            entry: app_v18.py", workflow)


if __name__ == "__main__":
    unittest.main()
