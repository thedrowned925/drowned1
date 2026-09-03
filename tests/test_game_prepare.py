from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "windows" / "release-manager" / "game_prepare.py"
SPEC = importlib.util.spec_from_file_location("release_manager_game_prepare", MODULE_PATH)
game_prepare = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = game_prepare
SPEC.loader.exec_module(game_prepare)


class GamePrepareTests(unittest.TestCase):
    def test_exe_scoring_prefers_game_binary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = root / "Binaries" / "Win64" / "DetroitBecomeHuman-Win64-Shipping.exe"
            setup = root / "UEPrereqSetup_x64.exe"
            crash = root / "CrashReporter.exe"
            good.parent.mkdir(parents=True)
            for path, size in ((good, 20 * 1024 * 1024), (setup, 120_000), (crash, 120_000)):
                with path.open("wb") as handle:
                    handle.truncate(size)

            chosen, ranked = game_prepare.detect_executable(root, "Detroit Become Human")
            self.assertEqual(chosen, good)
            self.assertGreater(ranked[0][0], 50)
            self.assertLess(game_prepare.score_executable(crash, "Detroit Become Human"), 0)

    def test_root_detection_can_find_nested_win64_game(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / "Project" / "Binaries" / "Win64" / "MyGame-Win64-Shipping.exe"
            binary.parent.mkdir(parents=True)
            with binary.open("wb") as handle:
                handle.truncate(12 * 1024 * 1024)
            detected = game_prepare.detect_game_root(root, "My Game")
            self.assertTrue(game_prepare._inside(binary, detected))

    def test_archive_entry_point_uses_only_first_multipart_rar(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = []
            for name in ("game.part01.rar", "game.part02.rar", "game.part03.rar"):
                path = root / name
                path.write_bytes(b"x")
                files.append(path)
            entries = game_prepare._archive_entry_points(files)
            self.assertEqual([p.name for p in entries], ["game.part01.rar"])

    def test_success_cleanup_deletes_all_rar_volumes_but_keeps_extracted_game(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            extracted = root / "_extracted_game"
            game_root = extracted / "Game"
            game_root.mkdir(parents=True)
            exe = game_root / "Game.exe"
            exe.write_bytes(b"MZ")
            parts = []
            for name in ("game.part01.rar", "game.part02.rar", "game.part03.rar"):
                path = root / name
                path.write_bytes(b"archive")
                parts.append(path)

            prepared = game_prepare.PreparedGame(
                title="Game",
                download_dir=str(root),
                extraction_root=str(extracted),
                game_root=str(game_root),
                executable=str(exe),
                downloaded_files=[str(p) for p in parts],
                archives=[str(parts[0])],
                created_at=1.0,
            )
            freed = game_prepare.confirm_test_success(prepared)
            self.assertGreater(freed, 0)
            self.assertTrue(game_root.exists())
            self.assertTrue(exe.exists())
            self.assertTrue(all(not p.exists() for p in parts))
            self.assertTrue(prepared.user_confirmed)

    def test_final_cleanup_refuses_arbitrary_user_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            extracted = root / "_extracted_game"
            game_root = extracted / "Game"
            game_root.mkdir(parents=True)
            (game_root / "Game.exe").write_bytes(b"MZ")
            external = root / "my-master-build"
            external.mkdir()
            prepared = game_prepare.PreparedGame(
                title="Game",
                download_dir=str(root),
                extraction_root=str(extracted),
                game_root=str(game_root),
                executable=str(game_root / "Game.exe"),
                downloaded_files=[],
                archives=[],
                created_at=1.0,
                user_confirmed=True,
            )
            with self.assertRaises(RuntimeError):
                game_prepare.cleanup_after_verified_publish(prepared, str(external))
            self.assertTrue(extracted.exists())

    def test_final_cleanup_deletes_only_owned_extraction_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            extracted = root / "_extracted_game"
            game_root = extracted / "Game"
            game_root.mkdir(parents=True)
            exe = game_root / "Game.exe"
            exe.write_bytes(b"MZdata")
            unrelated = root / "do-not-delete.txt"
            unrelated.write_text("keep", encoding="utf-8")
            prepared = game_prepare.PreparedGame(
                title="Game",
                download_dir=str(root),
                extraction_root=str(extracted),
                game_root=str(game_root),
                executable=str(exe),
                downloaded_files=[],
                archives=[],
                created_at=1.0,
                user_confirmed=True,
            )
            freed = game_prepare.cleanup_after_verified_publish(prepared, str(game_root))
            self.assertGreater(freed, 0)
            self.assertFalse(extracted.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
