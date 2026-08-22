import ast
import unittest
from pathlib import Path


class LauncherUIV13Tests(unittest.TestCase):
    def test_v13_is_presentation_only_wrapper(self):
        path = Path("windows/launcher/app_v13.py")
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        self.assertIn("import app_v12 as previous", source)
        self.assertNotIn("from drowned_shared", source)
        self.assertNotIn("import drowned_shared", source)

        launcher = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Launcher"
        )
        bases = [ast.unparse(base) for base in launcher.bases]
        self.assertEqual(bases, ["previous.Launcher"])

        # Backend/action methods remain inherited verbatim from app_v12.
        forbidden_overrides = {
            "install_current_game",
            "verify_current_game",
            "uninstall_current_game",
            "install_done",
            "install_error",
            "install_cancelled",
            "toggle_pause",
            "cancel_download",
            "load_catalog",
            "render_library",
            "artwork_loaded",
            "_addon_toggled",
            "_start_addon_install",
            "_start_addon_remove",
            "_addon_install_done",
            "_addon_remove_done",
            "_addon_error",
            "_addon_verify_done",
            "_addon_verify_error",
            "update_install_state_ui",
            "library_selection_changed",
        }
        defined = {
            node.name for node in launcher.body if isinstance(node, ast.FunctionDef)
        }
        self.assertFalse(forbidden_overrides & defined)

    def test_release_manager_is_not_imported_or_patched(self):
        source = Path("windows/launcher/app_v13.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("release-manager", source)
        self.assertNotIn("release_manager", source)


if __name__ == "__main__":
    unittest.main()
