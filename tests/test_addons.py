import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from drowned_shared.addons import (
    addon_state_path,
    assert_addon_compatible,
    install_optional_package,
    is_addon_installed,
    list_installed_addons,
    remove_optional_package,
)


def file_entry(path: str, data: bytes) -> dict:
    return {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def manifest_for(tag: str, files: list[tuple[str, bytes]], *, package=None, base=None) -> dict:
    offset = 0
    segments = []
    raw = b""
    entries = []
    for path, data in files:
        entries.append(file_entry(path, data))
        segments.append(
            {
                "file": path,
                "file_offset": 0,
                "chunk_offset": offset,
                "length": len(data),
            }
        )
        raw += data
        offset += len(data)
    value = {
        "schema_version": 1,
        "release": {"owner": "owner", "repo": "repo", "tag": tag},
        "total_size": len(raw),
        "files": entries,
        "chunks": [
            {
                "name": "chunk-000001.bin",
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "segments": segments,
            }
        ],
    }
    if package is None:
        value["game"] = {
            "id": "demo",
            "platform": "pc",
            "channel": "stable",
            "version": "1.0.0",
        }
    else:
        value["package_type"] = "optional"
        value["package"] = package
        value["base"] = base
    return value


class AddonTests(unittest.TestCase):
    def setUp(self):
        self.base_bytes = b"BASE-TEXTURE"
        self.addon_bytes = b"ULTRA-TEXTURE"
        self.extra_bytes = b"ADDON-ONLY"
        self.base = manifest_for(
            "pc-demo-v1.0.0-stable",
            [("data/texture.bin", self.base_bytes), ("game.exe", b"EXE")],
        )
        self.addon = manifest_for(
            "pc-demo-v1.0.0-stable-addon-hires-v1.0.0",
            [("data/texture.bin", self.addon_bytes), ("hires/extra.bin", self.extra_bytes)],
            package={"id": "hires", "title": "High Res Textures", "version": "1.0.0"},
            base={"game_id": "demo", "platform": "pc", "channel": "stable", "version": "1.0.0"},
        )

    def test_compatibility_is_scoped_to_exact_base_version(self):
        assert_addon_compatible(self.addon, self.base)
        wrong = json.loads(json.dumps(self.addon))
        wrong["base"]["version"] = "2.0.0"
        with self.assertRaises(ValueError):
            assert_addon_compatible(wrong, self.base)

    def test_install_keeps_base_resume_state_separate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".drowned").mkdir()
            base_state = {"tag": self.base["release"]["tag"], "completed_chunks": ["base"], "verified": True}
            (root / ".drowned" / "state.json").write_text(json.dumps(base_state), encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "texture.bin").write_bytes(self.base_bytes)
            (root / "game.exe").write_bytes(b"EXE")

            def fake_download(manifest, install_root, chunk_names, progress, log, cancelled, **kwargs):
                for path, data in (("data/texture.bin", self.addon_bytes), ("hires/extra.bin", self.extra_bytes)):
                    target = Path(install_root) / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                callback = kwargs.get("on_chunk_complete")
                if callback:
                    callback("chunk-000001.bin")
                progress(manifest["total_size"], manifest["total_size"])
                return 1

            with patch("drowned_shared.addons._download_chunks", side_effect=fake_download):
                state = install_optional_package(
                    self.addon,
                    root,
                    self.base,
                    manifest_url="https://example/addon.json",
                    base_manifest_url="https://example/base.json",
                )

            self.assertTrue(state["installed"])
            self.assertTrue(is_addon_installed(root, "hires"))
            self.assertEqual(len(list_installed_addons(root)), 1)
            unchanged = json.loads((root / ".drowned" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(unchanged, base_state)
            self.assertEqual((root / "data" / "texture.bin").read_bytes(), self.addon_bytes)
            self.assertEqual((root / "hires" / "extra.bin").read_bytes(), self.extra_bytes)

    def test_remove_deletes_only_package_files_and_restores_base_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir(parents=True)
            (root / "hires").mkdir(parents=True)
            (root / "data" / "texture.bin").write_bytes(self.addon_bytes)
            (root / "hires" / "extra.bin").write_bytes(self.extra_bytes)
            state = {
                "package_id": "hires",
                "title": "High Res Textures",
                "version": "1.0.0",
                "tag": self.addon["release"]["tag"],
                "installed": True,
                "files": ["data/texture.bin", "hires/extra.bin"],
                "completed_chunks": ["chunk-000001.bin"],
            }
            path = addon_state_path(root, "hires")
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(state), encoding="utf-8")

            def fake_base_repair(manifest, install_root, **kwargs):
                target = Path(install_root) / "data" / "texture.bin"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self.base_bytes)
                return {"repaired_files": ["data/texture.bin"], "downloaded_chunks": 1}

            with patch("drowned_shared.addons.repair_manifest", side_effect=fake_base_repair):
                result = remove_optional_package("hires", root, self.base)

            self.assertFalse((root / "hires" / "extra.bin").exists())
            self.assertEqual((root / "data" / "texture.bin").read_bytes(), self.base_bytes)
            self.assertFalse(addon_state_path(root, "hires").exists())
            self.assertEqual(result["removed_files"], ["hires/extra.bin"])
            self.assertEqual(result["restored_base_files"], ["data/texture.bin"])

    def test_malicious_state_path_cannot_escape_install_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "game"
            root.mkdir()
            outside = Path(td) / "outside.bin"
            outside.write_bytes(b"DO-NOT-DELETE")
            state = {
                "package_id": "bad",
                "title": "Bad",
                "version": "1",
                "tag": "tag",
                "installed": True,
                "files": ["../outside.bin"],
            }
            path = addon_state_path(root, "bad")
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(ValueError):
                remove_optional_package("bad", root, self.base)
            self.assertEqual(outside.read_bytes(), b"DO-NOT-DELETE")


if __name__ == "__main__":
    unittest.main()
