import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from drowned_shared.addon_delete import delete_optional_package
from drowned_shared.addon_publish import publish_optional_package


class DummyDeleteClient:
    def __init__(self):
        self.owner = "owner"
        self.repo = "repo"
        self.branch = "main"
        self.events = []
        self.catalog_text = ""

    def release_by_tag(self, tag):
        self.events.append(("release_lookup", tag))
        return {"id": 77, "tag_name": tag}

    def delete_release(self, release_id):
        self.events.append(("delete_release", release_id))
        return True

    def delete_tag_ref(self, tag):
        self.events.append(("delete_tag", tag))
        return True

    def delete_repo_file(self, path, message):
        self.events.append(("delete_manifest", path))
        return True

    def upsert_text(self, path, text, message):
        self.events.append(("catalog", path))
        self.catalog_text = text
        return {}


class AddonLifecycleTests(unittest.TestCase):
    def catalog(self):
        return {
            "schema_version": 1,
            "updated_at": None,
            "games": [
                {
                    "id": "demo",
                    "title": "Demo",
                    "platform": "pc",
                    "channels": {
                        "stable": {
                            "version": "1.0.0",
                            "tag": "pc-demo-v1.0.0-stable",
                            "manifest_path": "manifests/pc/demo/stable/1.0.0.json",
                            "optional_packages": [
                                {
                                    "id": "hires",
                                    "title": "High Res Textures",
                                    "version": "1.0.0",
                                    "tag": "pc-demo-v1.0.0-stable-addon-hires-v1.0.0",
                                    "manifest_path": "manifests/pc/demo/stable/1.0.0/addons/hires/1.0.0.json",
                                }
                            ],
                        }
                    },
                }
            ],
        }

    def test_existing_package_id_must_be_deleted_before_republish(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)
            (source / "texture.bin").write_bytes(b"x")
            with patch("drowned_shared.addon_publish.load_catalog", return_value=self.catalog()):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    publish_optional_package(
                        object(),
                        source,
                        "demo",
                        "pc",
                        "stable",
                        "1.0.0",
                        "High Res Textures",
                        "hires",
                        "2.0.0",
                    )

    def test_delete_optional_package_updates_catalog_last(self):
        client = DummyDeleteClient()
        with patch("drowned_shared.addon_delete.load_catalog", return_value=self.catalog()):
            result = delete_optional_package(
                client, "demo", "pc", "stable", "hires", log=lambda _: None
            )

        names = [event[0] for event in client.events]
        self.assertEqual(
            names,
            ["release_lookup", "delete_release", "delete_tag", "delete_manifest", "catalog"],
        )
        self.assertTrue(result["release_deleted"])
        self.assertTrue(result["tag_deleted"])
        self.assertTrue(result["manifest_deleted"])
        updated = json.loads(client.catalog_text)
        channel = updated["games"][0]["channels"]["stable"]
        self.assertNotIn("optional_packages", channel)


if __name__ == "__main__":
    unittest.main()
