import math
import unittest

from drowned_shared.constants import CHUNK_SIZE_BYTES, MAX_DATA_ASSETS
from drowned_shared.turbo_upload import (
    MIB,
    GIB,
    TEMP_RESERVE_BYTES,
    choose_upload_chunk_size,
    effective_worker_count,
)


class TurboUploadTests(unittest.TestCase):
    def test_small_project_keeps_existing_chunk_plan(self):
        total = 90 * MIB
        chunk16 = choose_upload_chunk_size(total, 16)
        chunk32 = choose_upload_chunk_size(total, 32)
        self.assertEqual(chunk32, chunk16)
        count = math.ceil(total / chunk32)
        self.assertLess(chunk32, total)
        self.assertGreaterEqual(count, 12)
        self.assertLessEqual(count, 16)

    def test_10gb_project_keeps_existing_chunk_plan(self):
        total = 10 * GIB
        chunk16 = choose_upload_chunk_size(total, 16)
        chunk32 = choose_upload_chunk_size(total, 32)
        self.assertEqual(chunk32, chunk16)
        count = math.ceil(total / chunk32)
        self.assertGreaterEqual(count, 15)
        self.assertLessEqual(count, 16)
        self.assertLessEqual(chunk32, CHUNK_SIZE_BYTES)

    def test_80gb_project_keeps_1_5gib_chunks_and_allows_32_workers(self):
        total = 80 * GIB
        chunk = choose_upload_chunk_size(total, 32)
        self.assertEqual(chunk, 1536 * MIB)
        self.assertLessEqual(math.ceil(total / chunk), MAX_DATA_ASSETS)
        self.assertEqual(
            effective_worker_count(
                chunk,
                32,
                free_temp_bytes=56 * GIB,
            ),
            32,
        )

    def test_low_temp_space_reduces_workers_without_changing_chunk(self):
        chunk = 1536 * MIB
        # 32 GiB free - 8 GiB reserve = 24 GiB usable = 16 x 1.5 GiB.
        workers = effective_worker_count(
            chunk,
            32,
            free_temp_bytes=32 * GIB,
        )
        self.assertEqual(TEMP_RESERVE_BYTES, 8 * GIB)
        self.assertEqual(workers, 16)

    def test_requested_16_still_behaves_like_old_profile(self):
        total = 80 * GIB
        chunk = choose_upload_chunk_size(total, 16)
        self.assertEqual(chunk, 1536 * MIB)
        self.assertEqual(effective_worker_count(chunk, 16), 16)

    def test_large_project_respects_asset_budget_and_max_chunk(self):
        total = 1200 * GIB
        chunk = choose_upload_chunk_size(total, 32)
        self.assertLessEqual(math.ceil(total / chunk), 900)
        self.assertLessEqual(chunk, CHUNK_SIZE_BYTES)


if __name__ == "__main__":
    unittest.main()
