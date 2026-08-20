import math
import unittest

from drowned_shared.constants import CHUNK_SIZE_BYTES, MAX_DATA_ASSETS
from drowned_shared.turbo_upload import (
    MIB,
    GIB,
    MAX_TURBO_WORKERS,
    choose_upload_chunk_size,
    effective_worker_count,
)


class TurboUploadTests(unittest.TestCase):
    def test_small_project_keeps_existing_chunk_plan(self):
        total = 90 * MIB
        chunk16 = choose_upload_chunk_size(total, 16)
        chunk40 = choose_upload_chunk_size(total, 40)
        self.assertEqual(chunk40, chunk16)
        count = math.ceil(total / chunk40)
        self.assertLess(chunk40, total)
        self.assertGreaterEqual(count, 12)
        self.assertLessEqual(count, 16)

    def test_10gb_project_keeps_existing_chunk_plan(self):
        total = 10 * GIB
        chunk16 = choose_upload_chunk_size(total, 16)
        chunk40 = choose_upload_chunk_size(total, 40)
        self.assertEqual(chunk40, chunk16)
        count = math.ceil(total / chunk40)
        self.assertGreaterEqual(count, 15)
        self.assertLessEqual(count, 16)
        self.assertLessEqual(chunk40, CHUNK_SIZE_BYTES)

    def test_80gb_project_keeps_1_5gib_chunks_and_allows_40_workers(self):
        total = 80 * GIB
        chunk = choose_upload_chunk_size(total, 40)
        self.assertEqual(chunk, 1536 * MIB)
        self.assertLessEqual(math.ceil(total / chunk), MAX_DATA_ASSETS)
        self.assertEqual(effective_worker_count(chunk, 40), 40)

    def test_direct_stream_worker_count_does_not_depend_on_temp_space(self):
        chunk = 1536 * MIB
        self.assertEqual(
            effective_worker_count(chunk, 40, free_temp_bytes=1),
            40,
        )

    def test_worker_count_caps_at_40(self):
        self.assertEqual(MAX_TURBO_WORKERS, 40)
        self.assertEqual(effective_worker_count(1536 * MIB, 64), 40)

    def test_requested_16_still_behaves_like_old_profile(self):
        total = 80 * GIB
        chunk = choose_upload_chunk_size(total, 16)
        self.assertEqual(chunk, 1536 * MIB)
        self.assertEqual(effective_worker_count(chunk, 16), 16)

    def test_large_project_respects_asset_budget_and_max_chunk(self):
        total = 1200 * GIB
        chunk = choose_upload_chunk_size(total, 40)
        self.assertLessEqual(math.ceil(total / chunk), 900)
        self.assertLessEqual(chunk, CHUNK_SIZE_BYTES)


if __name__ == "__main__":
    unittest.main()
