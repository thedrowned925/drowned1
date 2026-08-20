import math
import unittest

from drowned_shared.constants import CHUNK_SIZE_BYTES, MAX_DATA_ASSETS
from drowned_shared.turbo_upload import (
    MIB,
    GIB,
    MAX_TURBO_WORKERS,
    MIN_BALANCED_STREAMS,
    choose_upload_chunk_size,
    choose_upload_plan,
    effective_worker_count,
)


class TurboUploadTests(unittest.TestCase):
    def assert_plan(self, gib, workers, chunks, waves):
        total = int(gib * GIB)
        plan = choose_upload_plan(total)
        self.assertEqual(plan["workers"], workers)
        self.assertEqual(plan["chunk_count"], chunks)
        self.assertEqual(plan["waves"], waves)
        self.assertLessEqual(plan["chunk_size"], CHUNK_SIZE_BYTES)
        self.assertEqual(math.ceil(total / plan["chunk_size"]), chunks)
        self.assertEqual(chunks, workers * waves)
        return plan

    def test_safe_chunk_ceiling_is_1900_mib(self):
        self.assertEqual(CHUNK_SIZE_BYTES, 1900 * MIB)
        self.assertLess(CHUNK_SIZE_BYTES, 2 * GIB)

    def test_small_projects_do_not_force_40_tiny_assets(self):
        plan = choose_upload_plan(500 * MIB)
        self.assertEqual(plan["workers"], 8)
        self.assertEqual(plan["chunk_count"], 8)
        self.assertEqual(plan["waves"], 1)
        self.assertLessEqual(plan["chunk_size"], 64 * MIB)

        plan = choose_upload_plan(2 * GIB)
        self.assertEqual(plan["workers"], 32)
        self.assertEqual(plan["chunk_count"], 32)
        self.assertEqual(plan["waves"], 1)

    def test_five_gib_starts_one_full_40_stream_wave(self):
        plan = self.assert_plan(5, 40, 40, 1)
        self.assertEqual(plan["chunk_size"], 128 * MIB)

    def test_61_83_gib_is_one_40_stream_wave(self):
        self.assert_plan(61.83, 40, 40, 1)

    def test_concurrency_rises_only_when_one_wave_needs_it(self):
        self.assert_plan(75, 41, 41, 1)
        self.assert_plan(100, 54, 54, 1)
        self.assert_plan(118, 64, 64, 1)

    def test_119_gib_switches_to_two_complete_40_stream_waves(self):
        self.assert_plan(119, 40, 80, 2)

    def test_120_gib_is_40_plus_40(self):
        plan = self.assert_plan(120, 40, 80, 2)
        self.assertEqual(plan["chunk_size"], 1536 * MIB)

    def test_150_gib_is_41_plus_41(self):
        self.assert_plan(150, 41, 82, 2)

    def test_200_gib_is_54_plus_54(self):
        self.assert_plan(200, 54, 108, 2)

    def test_explicit_40_worker_cap_stays_balanced(self):
        plan = choose_upload_plan(200 * GIB, requested_workers=40)
        self.assertEqual(plan["workers"], 40)
        self.assertEqual(plan["waves"], 3)
        self.assertEqual(plan["chunk_count"], 120)
        self.assertLessEqual(plan["chunk_size"], CHUNK_SIZE_BYTES)

    def test_direct_stream_workers_ignore_temp_space_and_cap_at_64(self):
        self.assertEqual(MIN_BALANCED_STREAMS, 40)
        self.assertEqual(MAX_TURBO_WORKERS, 64)
        self.assertEqual(effective_worker_count(1900 * MIB, 64, free_temp_bytes=1), 64)
        self.assertEqual(effective_worker_count(1900 * MIB, 80), 64)

    def test_compatibility_chunk_size_wrapper_uses_balanced_plan(self):
        total = 61.83 * GIB
        self.assertEqual(
            choose_upload_chunk_size(int(total)),
            choose_upload_plan(int(total))["chunk_size"],
        )

    def test_large_project_respects_asset_budget(self):
        total = 1200 * GIB
        plan = choose_upload_plan(total)
        self.assertLessEqual(plan["chunk_count"], MAX_DATA_ASSETS)
        self.assertLessEqual(plan["chunk_size"], CHUNK_SIZE_BYTES)
        self.assertEqual(plan["chunk_count"], plan["workers"] * plan["waves"])


if __name__ == "__main__":
    unittest.main()
