import json
import unittest

from drowned_shared.upload_status import STATUS_PATH, UploadStatusBroadcaster


class FakeClient:
    def __init__(self):
        self.calls = []

    def upsert_text(self, path, text, message):
        self.calls.append((path, json.loads(text), message))
        return {}


class UploadStatusBroadcasterTests(unittest.TestCase):
    def test_first_update_is_sent_and_computes_percent(self):
        client = FakeClient()
        broadcaster = UploadStatusBroadcaster(client, "game", "Demo", "pc", "stable", "1.0.0")
        broadcaster.update({"phase": "upload", "total_sent": 50, "total_size": 200})

        self.assertEqual(len(client.calls), 1)
        path, body, _ = client.calls[0]
        self.assertEqual(path, STATUS_PATH)
        self.assertEqual(body["active"], True)
        self.assertEqual(body["phase"], "upload")
        self.assertEqual(body["kind"], "game")
        self.assertEqual(body["title"], "Demo")
        self.assertEqual(body["percent"], 25)
        self.assertEqual(body["total_sent"], 50)
        self.assertEqual(body["total_size"], 200)

    def test_same_phase_progress_ticks_are_throttled(self):
        client = FakeClient()
        broadcaster = UploadStatusBroadcaster(client, "game", "Demo", "pc", "stable", "1.0.0")
        broadcaster.update({"phase": "upload", "total_sent": 10, "total_size": 200})
        broadcaster.update({"phase": "upload", "total_sent": 20, "total_size": 200})
        broadcaster.update({"phase": "upload", "total_sent": 30, "total_size": 200})

        self.assertEqual(len(client.calls), 1, "rapid same-phase ticks should be throttled to one commit")

    def test_phase_change_bypasses_throttle(self):
        client = FakeClient()
        broadcaster = UploadStatusBroadcaster(client, "game", "Demo", "pc", "stable", "1.0.0")
        broadcaster.update({"phase": "plan", "total_sent": 0, "total_size": 200})
        broadcaster.update({"phase": "upload", "total_sent": 5, "total_size": 200})

        self.assertEqual(len(client.calls), 2, "a phase transition must always be reported")

    def test_finish_reports_inactive_done(self):
        client = FakeClient()
        broadcaster = UploadStatusBroadcaster(client, "addon", "Pack", "pc", "stable", "2.0.0")
        broadcaster.finish()

        _, body, _ = client.calls[-1]
        self.assertEqual(body["active"], False)
        self.assertEqual(body["phase"], "done")

    def test_fail_reports_inactive_error_with_message(self):
        client = FakeClient()
        broadcaster = UploadStatusBroadcaster(client, "game", "Demo", "pc", "stable", "1.0.0")
        broadcaster.fail("network exploded")

        _, body, _ = client.calls[-1]
        self.assertEqual(body["active"], False)
        self.assertEqual(body["phase"], "error")
        self.assertEqual(body["message"], "network exploded")

    def test_broadcast_failure_never_raises(self):
        class BrokenClient:
            def upsert_text(self, path, text, message):
                raise RuntimeError("network down")

        broadcaster = UploadStatusBroadcaster(BrokenClient(), "game", "Demo", "pc", "stable", "1.0.0")
        broadcaster.update({"phase": "upload", "total_sent": 1, "total_size": 2})  # must not raise

    def test_update_simple_matches_plain_progress_callback_shape(self):
        client = FakeClient()
        broadcaster = UploadStatusBroadcaster(client, "addon", "Pack", "pc", "stable", "2.0.0")
        broadcaster.update_simple(75, 150)

        _, body, _ = client.calls[-1]
        self.assertEqual(body["percent"], 50)
        self.assertEqual(body["phase"], "upload")


if __name__ == "__main__":
    unittest.main()
