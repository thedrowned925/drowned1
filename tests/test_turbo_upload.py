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
    def test_small_project_uses_multiple_assets(self):
        total = 90 * MIB
        chunk = choose_upload_chunk_size(total, 8)
        self.assertLess(chunk, total)
        self.assertGreaterEqual(math.ceil(total / chunk), 4)
        self.assertLessEqual(math.ceil(total / chunk), 8)

    def test_80gb_project_stays_near_256mib(self):
        total = 80 * GIB
        chunk = choose_upload_chunk_size(total, 8)
        self.assertGreaterEqual(chunk, 256 * MIB)
        self.assertLessEqual(math.ceil(total / chunk), MAX_DATA_ASSETS)
        self.assertEqual(effective_worker_count(chunk, 8), 8)

    def test_large_project_grows_chunks_to_respect_asset_budget(self):
        total = 700 * GIB
        chunk = choose_upload_chunk_size(total, 8)
        self.assertGreater(chunk, 256 * MIB)
        self.assertLessEqual(math.ceil(total / chunk), 900)
        self.assertLessEqual(chunk, CHUNK_SIZE_BYTES)


if __name__ == "__main__":
    unittest.main()
