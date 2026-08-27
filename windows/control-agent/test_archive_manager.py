import tempfile
import zipfile
from pathlib import Path

from archive_manager import ArchiveError, ArchiveManager


def test_valid_zip(root: Path):
    archive = root / "ExampleGame.zip"
    payload = b"Drowned archive test" * 4096
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("ExampleGame/game.exe", payload)
        handle.writestr("ExampleGame/data/readme.txt", b"ok")

    info = ArchiveManager.inspect(archive)
    assert info["file_count"] == 2
    assert info["single_root"] == "ExampleGame"
    assert info["uncompressed_bytes"] == len(payload) + 2

    samples = []
    destination = root / "installed"
    result = ArchiveManager.extract(
        archive,
        destination=destination,
        progress=lambda done, total: samples.append((done, total)),
        verified_info=info,
    )
    assert (destination / "ExampleGame" / "game.exe").read_bytes() == payload
    assert result["game_root"] == str(destination / "ExampleGame")
    assert samples
    assert samples[-1][0] == samples[-1][1] == info["uncompressed_bytes"]

    try:
        ArchiveManager.extract(archive, destination=destination, verified_info=info)
    except ArchiveError:
        pass
    else:
        raise AssertionError("Existing extraction destination must not be overwritten")


def test_zip_slip_is_rejected(root: Path):
    archive = root / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", b"nope")

    try:
        ArchiveManager.inspect(archive)
    except ArchiveError:
        pass
    else:
        raise AssertionError("ZIP traversal entry must be rejected")

    assert not (root.parent / "escape.txt").exists()


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        test_valid_zip(root)
        test_zip_slip_is_rejected(root)
    print("Archive manager tests OK")


if __name__ == "__main__":
    main()
