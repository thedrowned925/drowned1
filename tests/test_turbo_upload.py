import math
import unittest

from drowned_shared.constants import CHUNK_SIZE_BYTES, MAX_DATA_ASSETS
from drowned_shared.turbo_upload import (
    MIB,
    GIB,
    choose_upload_chunk_size,
    effective_worker_count,
)


class TurboUploadTests(unittest.TestCase):
    def test_small_project_keeps_roughly_16_streams_busy(self):
        total = 90 * MIB
        chunk = choose_upload_chunk_size(total, 16)
        count = math.ceil(total / chunk)
        self.assertLess(chunk, total)
        self.assertGreaterEqual(count, 12)
        self.assertLessEqual(count, 16)
        self.assertEqual(effective_worker_count(chunk, 16), 16)

    def test_10gb_project_targets_about_16_assets(self):
        total = 10 * GIB
        chunk = choose_upload_chunk_size(total, 16)
        count = math.ceil(total / chunk)
        self.assertGreaterEqual(count, 15)
        self.assertLessEqual(count, 16)
        self.assertLessEqual(chunk, CHUNK_SIZE_BYTES)
        self.assertEqual(effective_worker_count(chunk, 16), 16)

    def test_80gb_project_uses_1_5gib_max_and_16_workers(self):
        total = 80 * GIB
        chunk = choose_upload_chunk_size(total, 16)
        self.assertEqual(chunk, 1536 * MIB)
        self.assertLessEqual(math.ceil(total / chunk), MAX_DATA_ASSETS)
        self.assertEqual(effective_worker_count(chunk, 16), 16)

    def test_large_project_respects_asset_budget_and_max_chunk(self):
        total = 1200 * GIB
        chunk = choose_upload_chunk_size(total, 16)
        self.assertLessEqual(math.ceil(total / chunk), 900)
        self.assertLessEqual(chunk, CHUNK_SIZE_BYTES)


if __name__ == "__main__":
    unittest.main()
