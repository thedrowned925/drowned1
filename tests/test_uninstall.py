from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from drowned_shared.uninstall import UnsafeUninstallTarget, remove_install_tree, validate_uninstall_target


class UninstallSafetyTest(unittest.TestCase):
    def test_removes_only_marked_install(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "Game"
            marker = root / ".drowned" / "state.json"
            marker.parent.mkdir(parents=True)
            marker.write_text(json.dumps({"tag": "pc-game-v1-stable"}), encoding="utf-8")
            (root / "data.bin").write_bytes(b"game-data")

            self.assertEqual(validate_uninstall_target(root, "pc-game-v1-stable"), root.resolve())
            removed = remove_install_tree(root, "pc-game-v1-stable")
            self.assertEqual(removed, root.resolve())
            self.assertFalse(root.exists())

    def test_refuses_directory_without_drowned_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "NotManaged"
            root.mkdir()
            with self.assertRaises(UnsafeUninstallTarget):
                validate_uninstall_target(root, "some-tag")
            self.assertTrue(root.exists())

    def test_refuses_tag_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "Game"
            marker = root / ".drowned" / "state.json"
            marker.parent.mkdir(parents=True)
            marker.write_text(json.dumps({"tag": "real-tag"}), encoding="utf-8")
            with self.assertRaises(UnsafeUninstallTarget):
                validate_uninstall_target(root, "wrong-tag")
            self.assertTrue(root.exists())


if __name__ == "__main__":
    unittest.main()
