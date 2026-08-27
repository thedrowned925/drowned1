import tempfile
import time
from pathlib import Path

from download_watcher import DownloadWatcher


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        watcher = DownloadWatcher()
        first = watcher.start(temp_dir)
        assert first["state"] == "waiting"

        target = Path(temp_dir) / "sample-download.bin"
        target.write_bytes(b"a" * 1024)
        detected = watcher.poll()
        assert detected["file_name"] == target.name
        assert detected["downloaded_bytes"] == 1024

        time.sleep(0.05)
        with target.open("ab") as handle:
            handle.write(b"b" * 4096)
        growing = watcher.poll()
        assert growing["state"] == "downloading"
        assert growing["downloaded_bytes"] == 5120
        assert growing["speed_bps"] > 0

        watcher.last_change_at = time.monotonic() - 9
        stable = watcher.poll()
        assert stable["state"] == "stable"
        assert stable["stable_seconds"] >= 8

        stopped = watcher.stop()
        assert stopped["state"] == "stopped"


if __name__ == "__main__":
    main()
