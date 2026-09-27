from __future__ import annotations

import ast
import importlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "windows" / "launcher"
V19 = LAUNCHER / "app_v19.py"
STEAM_MODULES = ("steam_theme.py", "steam_format.py", "steam_widgets.py", "steam_library.py", "steam_pages.py")
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"

BACKEND_METHODS = {
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


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


def _methods(node: ast.ClassDef) -> set[str]:
    return {item.name for item in node.body if isinstance(item, ast.FunctionDef)}


def _steam_format():
    if str(LAUNCHER) not in sys.path:
        sys.path.insert(0, str(LAUNCHER))
    return importlib.import_module("steam_format")


class LauncherUIV19Tests(unittest.TestCase):
    def test_v19_is_presentation_only(self):
        tree = ast.parse(V19.read_text(encoding="utf-8"))
        overridden = _methods(_class(tree, "Launcher")) & BACKEND_METHODS
        self.assertFalse(overridden, overridden)

    @staticmethod
    def _imports(name: str) -> set[str]:
        tree = ast.parse((LAUNCHER / name).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        return imported

    def test_v19_inherits_v16_and_has_no_backend_imports(self):
        source = V19.read_text(encoding="utf-8")
        self.assertIn("import app_v16 as previous", source)
        self.assertIn('APP_VERSION = "0.19.0"', source)
        for name in ("app_v19.py", *STEAM_MODULES):
            backend = {module for module in self._imports(name) if module.startswith("drowned_shared")}
            self.assertFalse(backend, f"{name} imports {backend}")
            self.assertNotIn("release-manager", (LAUNCHER / name).read_text(encoding="utf-8").lower(), name)

    def test_steam_modules_are_pure_ui(self):
        for name in STEAM_MODULES:
            launcher_layers = {module for module in self._imports(name) if module.startswith("app_v")}
            self.assertFalse(launcher_layers, f"{name} imports {launcher_layers}")
        qt = {module for module in self._imports("steam_format.py") if module.startswith("PySide6")}
        self.assertFalse(qt, "steam_format must stay importable without Qt")

    def test_v19_keeps_widget_contracts_used_by_the_backend(self):
        source = V19.read_text(encoding="utf-8")
        required = (
            "self.install_button =", "self.verify_button =", "self.info_card =", "self.state_badge =",
            "self.status =", "self.status_icon =", "self.progress =", "self.progress_text =", "self._status_row =",
            "self.logs =", "self.connection =", "self.download_dot =", "self.library =", "self.platform =",
            "self.channel =", "self.search =", "self._search_debounce =", "self.game_count =", "self.title =",
            "self.meta =", "self.description =", "self.cover =", "self.hero =", "self.screenshot_gallery =",
            "self.library_grid =", "self.library_grid_bp =", "self.big_picture =", "self.big_picture_button =",
            "self.main_stack =", "self._chrome_widgets =", "self.right_stack =", "self.nav_library =",
            "self.nav_downloads =", "self.stat_platform =", "self.stat_channel =", "self.stat_version =",
            "self.stat_size =", "self.panel_state =", "self.panel_path =", "self.panel_tag =", "self.panel_repo =",
            "self.panel_branch =", "self.action_dl =", "self.action_pause =", "self.action_dl_caption =",
            "self.action_dl_value =", "self.action_dl_bar =", "self.dlp_hero =", "self.dlp_peak =",
            "self.dlp_limit =", "self.dlp_title =", "self.dlp_detail =", "self.dlp_eta =", "self.dlp_percent =",
            "self.dlp_bar =", "self.dlp_bytes =", "self.dlp_pause =", "self.dlp_queue_caption =",
            "self.dlp_queue_body =", "self.dlp_done_caption =", "self.dlp_done_empty =", "self.dlp_rows_layout =",
            "self._completed_rows", "self._wire_runtime()",
        )
        missing = [name for name in required if name not in source]
        self.assertFalse(missing, missing)
        # dlp_net / dlp_streams are unpacked from the downloads header.
        self.assertIn("self.dlp_net, self._dlp_peak_shown, self._dlp_total, self.dlp_streams", source)

    def test_v19_wires_the_real_actions(self):
        source = V19.read_text(encoding="utf-8")
        for action in (
            "self.install_current_game",
            "self.verify_current_game",
            "self.uninstall_current_game",
            "self.toggle_pause",
            "self.cancel_download",
            "self.load_catalog",
            "self.open_settings",
            "self._toggle_big_picture",
            "self._open_install_folder",
            "self._forget_install_record",
        ):
            self.assertIn(action, source)

    def test_library_list_implements_the_view_contract(self):
        tree = ast.parse((LAUNCHER / "steam_library.py").read_text(encoding="utf-8"))
        view = _class(tree, "SteamLibraryList")
        needed = {
            "show_loading_skeleton", "set_items", "set_current_row", "set_source_rows", "set_tile_progress",
            "set_tile_badge", "set_tile_cover", "set_tile_installed", "focus_selection", "is_selection_on_last_row",
            "contains_source_row", "first_source_row", "activate_current", "move_direction",
        }
        self.assertFalse(needed - _methods(view), needed - _methods(view))
        signals = {
            target.id
            for item in view.body if isinstance(item, ast.Assign)
            for target in item.targets if isinstance(target, ast.Name)
        }
        for signal in ("tileActivated", "coverRequested", "selectionChanged", "gameActivated"):
            self.assertIn(signal, signals)

    def test_windows_build_uses_v19(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/launcher\n            entry: app_v19.py", workflow)


class SteamFormatTests(unittest.TestCase):
    def test_human_size_matches_backend_format(self):
        from drowned_shared.util import format_bytes

        fmt = _steam_format()
        for value in (0, 1, 1023, 1024, 94151373, 7276478040, 172095946463):
            self.assertEqual(fmt.human_size(value), format_bytes(value))

    def test_speed_parser_reads_iec_units_written_by_the_downloader(self):
        from drowned_shared.util import format_bytes

        fmt = _steam_format()
        speed = 13 * 1024 * 1024
        self.assertAlmostEqual(fmt.speed_to_bytes(f"{format_bytes(speed)}/sn"), speed)
        self.assertAlmostEqual(fmt.speed_to_bytes("512,5 KiB/sn"), 512.5 * 1024)
        self.assertAlmostEqual(fmt.speed_to_bytes("2 MB/sn"), 2 * 1024 * 1024)
        self.assertEqual(fmt.speed_to_bytes("-"), 0.0)
        self.assertEqual(fmt.speed_to_bytes(""), 0.0)

    def test_time_buckets(self):
        fmt = _steam_format()
        now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(fmt.time_bucket(now - timedelta(hours=1), now), "Bugün")
        self.assertEqual(fmt.time_bucket(now - timedelta(days=1), now), "Dün")
        self.assertEqual(fmt.time_bucket(now - timedelta(days=4), now), "Bu hafta")
        self.assertEqual(fmt.time_bucket(now - timedelta(days=10), now), "Geçen hafta")
        self.assertEqual(fmt.time_bucket(datetime(2026, 5, 3, tzinfo=timezone.utc), now), "Mayıs")
        self.assertEqual(fmt.time_bucket(datetime(2025, 12, 3, tzinfo=timezone.utc), now), "Aralık 2025")
        self.assertEqual(fmt.time_bucket("", now), "")

    def test_launch_candidates_prefer_the_game_over_installers(self):
        fmt = _steam_format()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "unins000.exe": 10,
                "vc_redist.x64.exe": 10,
                "UnityCrashHandler64.exe": 10,
                "PapersPlease.exe": 2000,
                "_CommonRedist/DirectX/DXSETUP.exe": 10,
                "Engine/Binaries/Win64/CrashReportClient.exe": 10,
                "tools/editor.exe": 10,
                "bin/helper.exe": 10,
                ".drowned/state.json": 2,
                "readme.txt": 5,
            }
            for relative, size in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * size)
            candidates = [p.relative_to(root).as_posix() for p in fmt.find_launch_candidates(root, "Papers, Please")]
        self.assertEqual(candidates[0], "PapersPlease.exe")
        self.assertIn("bin/helper.exe", candidates)
        for skipped in ("unins000.exe", "vc_redist.x64.exe", "UnityCrashHandler64.exe", "tools/editor.exe"):
            self.assertNotIn(skipped, candidates)
        self.assertFalse(any("DXSETUP" in c or "CrashReport" in c for c in candidates))

    def test_launch_candidates_for_missing_folder(self):
        fmt = _steam_format()
        self.assertEqual(fmt.find_launch_candidates(Path(tempfile.gettempdir()) / "missing-drowned-dir"), [])


if __name__ == "__main__":
    unittest.main()
