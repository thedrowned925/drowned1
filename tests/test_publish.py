import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from drowned_shared.publish import publish_project


class FakeUploader:
    """Stands in for TurboAssetUploader so the test never touches the network."""

    def __init__(self, client, release_id):
        self.client = client
        self.release_id = release_id

    def upload(self, name, path, progress=None, content_type="application/octet-stream"):
        size = Path(path).stat().st_size
        if progress:
            progress(size, size)
        return {"id": 1, "name": name}


class FakeClient:
    owner = "thedrowned925"
    repo = "drowned1"
    branch = "main"
    token = "fake-token"

    def __init__(self, catalog=None):
        self.catalog = catalog or {"schema_version": 1, "updated_at": None, "games": []}
        self.uploaded_bytes = {}
        self.uploaded_text = {}
        self.uploaded_assets = []
        self.released = []

    def raw_content(self, path):
        if path == "catalog.json":
            return json.dumps(self.catalog).encode()
        return None

    def create_release(self, tag, name, body, prerelease):
        return {"id": 1}

    def upload_asset(self, release_id, name, path, content_type):
        self.uploaded_assets.append((release_id, name))

    def upsert_text(self, path, text, message):
        self.uploaded_text[path] = text
        if path == "catalog.json":
            self.catalog = json.loads(text)

    def upsert_bytes(self, path, data, message):
        self.uploaded_bytes[path] = data

    def raw_url(self, path):
        return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.branch}/{path}"

    def publish_release(self, release_id, prerelease):
        self.released.append((release_id, prerelease))


def _source_dir(tmp):
    source = Path(tmp) / "source"
    source.mkdir()
    (source / "game.bin").write_bytes(b"hello world" * 100)
    return source


def _artwork_dir(tmp):
    art = Path(tmp) / "artwork_input"
    art.mkdir()
    (art / "hero.png").write_bytes(b"hero-bytes")
    (art / "shot0.png").write_bytes(b"shot-0-bytes")
    (art / "shot1.png").write_bytes(b"shot-1-bytes")
    return art


class PublishScreenshotsTests(unittest.TestCase):
    @mock.patch("drowned_shared.publish.TurboAssetUploader", new=FakeUploader)
    def test_screenshots_uploaded_and_written_to_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _source_dir(tmp)
            art = _artwork_dir(tmp)
            client = FakeClient()
            publish_project(
                client, source, "Demo Game", "pc", "stable", "1.0.0",
                description="desc",
                artwork={
                    "hero": str(art / "hero.png"),
                    "screenshots": [str(art / "shot0.png"), str(art / "shot1.png")],
                },
                upload_workers=1,
            )

            self.assertEqual(client.uploaded_bytes["artwork/pc/demo-game/hero.png"], b"hero-bytes")
            self.assertEqual(client.uploaded_bytes["artwork/pc/demo-game/screenshots/00.png"], b"shot-0-bytes")
            self.assertEqual(client.uploaded_bytes["artwork/pc/demo-game/screenshots/01.png"], b"shot-1-bytes")

            game = client.catalog["games"][0]
            self.assertEqual(
                game["artwork"]["hero"],
                "https://raw.githubusercontent.com/thedrowned925/drowned1/main/artwork/pc/demo-game/hero.png",
            )
            self.assertEqual(
                game["artwork"]["screenshots"],
                [
                    "https://raw.githubusercontent.com/thedrowned925/drowned1/main/artwork/pc/demo-game/screenshots/00.png",
                    "https://raw.githubusercontent.com/thedrowned925/drowned1/main/artwork/pc/demo-game/screenshots/01.png",
                ],
            )

    @mock.patch("drowned_shared.publish.TurboAssetUploader", new=FakeUploader)
    def test_icon_uploaded_like_other_single_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _source_dir(tmp)
            art = _artwork_dir(tmp)
            (art / "game.ico").write_bytes(b"icon-bytes")
            client = FakeClient()
            publish_project(
                client, source, "Demo Game", "pc", "stable", "1.0.0",
                artwork={"icon": str(art / "game.ico")},
                upload_workers=1,
            )
            self.assertEqual(client.uploaded_bytes["artwork/pc/demo-game/icon.ico"], b"icon-bytes")
            self.assertEqual(
                client.catalog["games"][0]["artwork"]["icon"],
                "https://raw.githubusercontent.com/thedrowned925/drowned1/main/artwork/pc/demo-game/icon.ico",
            )

    @mock.patch("drowned_shared.publish.TurboAssetUploader", new=FakeUploader)
    def test_media_written_outside_artwork(self):
        # Trailers are external Steam CDN links, so they must land under
        # game["media"] and never inside game["artwork"], which the deletion
        # pass treats as repository-owned files.
        with tempfile.TemporaryDirectory() as tmp:
            source = _source_dir(tmp)
            client = FakeClient()
            trailers = [{"name": "Launch Trailer", "mp4": "https://cdn.example/t.mp4", "webm": ""}]
            publish_project(
                client, source, "Demo Game", "pc", "stable", "1.0.0",
                media={"trailers": trailers, "steam_app_id": 620},
                upload_workers=1,
            )
            game = client.catalog["games"][0]
            self.assertEqual(game["media"]["trailers"], trailers)
            self.assertEqual(game["media"]["steam_app_id"], 620)
            self.assertNotIn("trailers", game["artwork"])
            self.assertEqual(game["artwork"], {})

    @mock.patch("drowned_shared.publish.TurboAssetUploader", new=FakeUploader)
    def test_no_media_leaves_catalog_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _source_dir(tmp)
            client = FakeClient()
            publish_project(
                client, source, "Demo Game", "pc", "stable", "1.0.0", upload_workers=1
            )
            self.assertNotIn("media", client.catalog["games"][0])

    @mock.patch("drowned_shared.publish.TurboAssetUploader", new=FakeUploader)
    def test_backward_compatible_without_screenshots(self):
        # Regression guard: publishing without an artwork["screenshots"] key
        # (every caller before this change) must produce a catalog identical
        # in shape to what publish_project() wrote previously.
        with tempfile.TemporaryDirectory() as tmp:
            source = _source_dir(tmp)
            art = _artwork_dir(tmp)
            client = FakeClient()
            publish_project(
                client, source, "Demo Game", "pc", "stable", "1.0.0",
                description="desc",
                artwork={"hero": str(art / "hero.png")},
                upload_workers=1,
            )
            game = client.catalog["games"][0]
            self.assertEqual(set(game["artwork"]), {"hero"})
            self.assertNotIn("screenshots", game["artwork"])
            self.assertNotIn("artwork/pc/demo-game/screenshots/00.png", client.uploaded_bytes)


if __name__ == "__main__":
    unittest.main()
