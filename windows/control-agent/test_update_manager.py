from update_manager import UpdateError, windows_update


def sample(build_number=10, url=None, sha256=None):
    return {
        "version": "0.9.0-nightly.10",
        "build_sha": "abc123",
        "windows": {
            "available": True,
            "build_number": build_number,
            "url": url
            or "https://github.com/thedrowned925/drowned1/releases/download/control-nightly/Drowned-Agent.exe",
            "sha256": sha256 or ("a" * 64),
        },
    }


def main():
    available = windows_update(sample())
    assert available is not None
    assert available["build_number"] == 10
    assert available["sha256"] == "a" * 64

    assert windows_update(sample(build_number=0)) is None
    assert windows_update({"windows": {"available": False}}) is None

    try:
        windows_update(sample(url="https://example.com/Drowned-Agent.exe"))
    except UpdateError:
        pass
    else:
        raise AssertionError("Non-GitHub update URL should be rejected")

    try:
        windows_update(sample(sha256="bad"))
    except UpdateError:
        pass
    else:
        raise AssertionError("Invalid SHA-256 should be rejected")


if __name__ == "__main__":
    main()
