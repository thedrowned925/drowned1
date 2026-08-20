import hashlib
import tempfile
import unittest
from pathlib import Path

from drowned_shared.chunking import ChunkBuilder
from drowned_shared.direct_stream import (
    DirectChunkReader,
    hash_source_files,
    plan_direct_stream,
)
from drowned_shared.errors import SourceChangedError
from drowned_shared.turbo_upload import TurboAssetUploader


class DirectStreamTests(unittest.TestCase):
    def make_game(self, root: Path):
        (root / "a.bin").write_bytes(b"A" * 10)
        (root / "b.bin").write_bytes(b"B" * 7)

    def test_planner_and_reader_reproduce_original_chunk_bytes_without_temp_bins(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_game(root)
            builder = ChunkBuilder(root, chunk_size=8)
            plan = plan_direct_stream(builder)

            self.assertEqual([c["size"] for c in plan["chunks"]], [8, 8, 1])
            rebuilt = []
            for chunk in plan["chunks"]:
                reader = DirectChunkReader(chunk, plan["snapshot_map"])
                payload = b""
                while True:
                    block = reader.read(3)
                    if not block:
                        break
                    payload += block
                self.assertEqual(reader.sha256, hashlib.sha256(payload).hexdigest())
                rebuilt.append(payload)

            self.assertEqual(b"".join(rebuilt), b"A" * 10 + b"B" * 7)
            self.assertEqual(
                {p.name for p in root.iterdir()},
                {"a.bin", "b.bin"},
            )

    def test_file_hashes_match_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_game(root)
            plan = plan_direct_stream(ChunkBuilder(root, chunk_size=8))
            files = hash_source_files(plan["snapshots"])
            by_name = {item["path"]: item for item in files}
            self.assertEqual(by_name["a.bin"]["sha256"], hashlib.sha256(b"A" * 10).hexdigest())
            self.assertEqual(by_name["b.bin"]["sha256"], hashlib.sha256(b"B" * 7).hexdigest())

    def test_reader_rejects_source_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_game(root)
            plan = plan_direct_stream(ChunkBuilder(root, chunk_size=8))
            (root / "a.bin").write_bytes(b"changed")
            reader = DirectChunkReader(plan["chunks"][0], plan["snapshot_map"])
            with self.assertRaises(SourceChangedError):
                reader.read(8)

    def test_turbo_upload_stream_consumes_direct_reader_and_returns_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_game(root)
            plan = plan_direct_stream(ChunkBuilder(root, chunk_size=8))
            chunk = plan["chunks"][1]
            captured = {}

            class FakeResponse:
                ok = True
                status_code = 201
                headers = {}
                text = ""

                def json(self):
                    return {"id": 123}

            class FakeSession:
                def post(self, url, params, headers, data, timeout):
                    payload = bytearray()
                    while True:
                        block = data.read(3)
                        if not block:
                            break
                        payload.extend(block)
                    captured["body"] = bytes(payload)
                    captured["headers"] = headers
                    return FakeResponse()

            class Client:
                owner = "owner"
                repo = "repo"
                token = "token"

                @staticmethod
                def _permission_help(status, text):
                    return f"{status}: {text}"

            uploader = TurboAssetUploader(Client(), 99, min_start_interval=0)
            uploader._session = lambda: FakeSession()
            asset, digest = uploader.upload_stream(
                chunk["name"],
                chunk["size"],
                reader_factory=lambda: DirectChunkReader(chunk, plan["snapshot_map"]),
            )
            self.assertEqual(asset["id"], 123)
            self.assertEqual(captured["body"], b"AA" + b"B" * 6)
            self.assertEqual(digest, hashlib.sha256(captured["body"]).hexdigest())
            self.assertEqual(int(captured["headers"]["Content-Length"]), chunk["size"])


if __name__ == "__main__":
    unittest.main()
