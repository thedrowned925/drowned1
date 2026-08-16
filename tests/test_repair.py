import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from drowned_shared.install import chunks_for_files, find_invalid_files, repair_manifest


class RepairTests(unittest.TestCase):
    def make_manifest(self):
        a = b"AAAA-healthy-file"
        b = b"BBBB-file-that-will-be-deleted"
        manifest = {
            "schema_version": 1,
            "release": {"owner": "owner", "repo": "repo", "tag": "pc-test-v1-stable"},
            "files": [
                {"path": "a.bin", "size": len(a), "sha256": hashlib.sha256(a).hexdigest()},
                {"path": "sub/b.bin", "size": len(b), "sha256": hashlib.sha256(b).hexdigest()},
            ],
            "chunks": [
                {
                    "name": "chunk-000001.bin",
                    "size": len(a),
                    "sha256": hashlib.sha256(a).hexdigest(),
                    "segments": [
                        {"file": "a.bin", "file_offset": 0, "chunk_offset": 0, "length": len(a)}
                    ],
                },
                {
                    "name": "chunk-000002.bin",
                    "size": len(b),
                    "sha256": hashlib.sha256(b).hexdigest(),
                    "segments": [
                        {"file": "sub/b.bin", "file_offset": 0, "chunk_offset": 0, "length": len(b)}
                    ],
                },
            ],
            "total_size": len(a) + len(b),
        }
        return manifest, a, b

    def test_missing_file_maps_only_to_required_chunk(self):
        manifest, a, _ = self.make_manifest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.bin").write_bytes(a)
            invalid = find_invalid_files(manifest, root)
            self.assertEqual(invalid, ["sub/b.bin"])
            self.assertEqual(chunks_for_files(manifest, invalid), {"chunk-000002.bin"})

    def test_repair_redownloads_only_chunk_for_missing_file(self):
        manifest, a, b = self.make_manifest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.bin").write_bytes(a)
            state_dir = root / ".drowned"
            state_dir.mkdir()
            (state_dir / "state.json").write_text(
                json.dumps(
                    {
                        "tag": manifest["release"]["tag"],
                        "completed_chunks": ["chunk-000001.bin", "chunk-000002.bin"],
                        "verified": True,
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def fake_download(m, install_root, chunk_names, progress, log, cancelled):
                calls.append(set(chunk_names))
                target = Path(install_root) / "sub" / "b.bin"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b)
                return 1

            with patch("drowned_shared.install._download_chunks", side_effect=fake_download):
                result = repair_manifest(manifest, root)

            self.assertEqual(calls, [{"chunk-000002.bin"}])
            self.assertEqual(result["repaired_files"], ["sub/b.bin"])
            self.assertEqual((root / "sub" / "b.bin").read_bytes(), b)
            state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
            self.assertTrue(state["verified"])
            self.assertEqual(
                set(state["completed_chunks"]),
                {"chunk-000001.bin", "chunk-000002.bin"},
            )

    def test_clean_install_does_not_download_anything(self):
        manifest, a, b = self.make_manifest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.bin").write_bytes(a)
            (root / "sub").mkdir()
            (root / "sub" / "b.bin").write_bytes(b)
            with patch("drowned_shared.install._download_chunks") as downloader:
                result = repair_manifest(manifest, root)
            downloader.assert_not_called()
            self.assertEqual(result["repaired_files"], [])


if __name__ == "__main__":
    unittest.main()
