import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from drowned_shared.errors import DownloadCancelled
from drowned_shared.install import DownloadControl, _split_ranges, _write_chunk_slice


class TurboDownloadTests(unittest.TestCase):
    def test_split_ranges_cover_exact_size_without_overlap(self):
        ranges = _split_ranges(100, 16)
        self.assertTrue(ranges)
        self.assertEqual(ranges[0][0], 0)
        self.assertEqual(ranges[-1][1], 99)
        cursor = 0
        covered = 0
        for start, end in ranges:
            self.assertEqual(start, cursor)
            self.assertGreaterEqual(end, start)
            covered += end - start + 1
            cursor = end + 1
        self.assertEqual(covered, 100)

    def test_chunk_slice_writes_across_two_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.bin").write_bytes(b"\x00" * 5)
            (root / "b.bin").write_bytes(b"\x00" * 5)
            chunk = {
                "segments": [
                    {"file": "a.bin", "file_offset": 0, "chunk_offset": 0, "length": 5},
                    {"file": "b.bin", "file_offset": 0, "chunk_offset": 5, "length": 5},
                ]
            }
            locks = {}
            _write_chunk_slice(chunk, root, 3, b"ABCDEFG", locks)
            self.assertEqual((root / "a.bin").read_bytes(), b"\x00\x00\x00AB")
            self.assertEqual((root / "b.bin").read_bytes(), b"CDEFG")

    def test_pause_resume_and_cancel_control(self):
        control = DownloadControl()
        control.pause()
        released = []

        def waiter():
            control.checkpoint()
            released.append(True)

        thread = threading.Thread(target=waiter)
        thread.start()
        time.sleep(0.25)
        self.assertFalse(released)
        control.resume()
        thread.join(2)
        self.assertEqual(released, [True])

        control.cancel()
        with self.assertRaises(DownloadCancelled):
            control.checkpoint()


if __name__ == "__main__":
    unittest.main()
