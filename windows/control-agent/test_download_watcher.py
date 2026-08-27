import os
import tempfile
import time
import zipfile
from pathlib import Path

from download_watcher import DownloadWatcher


def test_growth_and_stability(root: Path):
    watcher = DownloadWatcher()
    first = watcher.start(root)
    assert first["state"] == "waiting"

    target = root / "sample-download.bin"
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


def test_same_size_write_resets_stability(root: Path):
    watcher = DownloadWatcher()
    watcher.start(root)
    target = root / "preallocated.bin"
    target.write_bytes(b"a" * 4096)
    watcher.poll()

    watcher.last_change_at = time.monotonic() - 9
    assert watcher.poll()["state"] == "stable"

    time.sleep(0.02)
    with target.open("r+b") as handle:
        handle.seek(0)
        handle.write(b"b" * 64)
        handle.flush()
        os.fsync(handle.fileno())
    now = time.time() + 1.0
    os.utime(target, (now, now))

    changed = watcher.poll()
    assert changed["state"] == "downloading"
    assert changed["downloaded_bytes"] == 4096
    assert changed["stable_seconds"] < 1


def test_zip_enters_automatic_extraction(root: Path):
    watcher = DownloadWatcher()
    watcher.start(root)
    archive = root / "TinyGame.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("TinyGame/game.exe", b"test-binary" * 4096)

    watcher.poll()
    watcher.last_change_at = time.monotonic() - 9
    started = watcher.poll()
    assert started["archive_state"] in {"archive_verifying", "extracting", "extracted"}

    watcher._archive_future.result(timeout=10)
    finished = watcher.poll()
    assert finished["archive_state"] == "extracted"
    assert finished["state"] == "ZIP çıkarıldı"
    assert finished["archive_progress"] == 100.0
    assert finished["game_root"]
    assert (Path(finished["game_root"]) / "game.exe").exists()


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        test_growth_and_stability(root)

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        test_same_size_write_resets_stability(root)

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        test_zip_enters_automatic_extraction(root)

    print("Download watcher tests OK")


if __name__ == "__main__":
    main()
