from __future__ import annotations

import json
from datetime import datetime, timezone

from .constants import CATALOG_NAME
from .metadata import load_catalog
from .util import slugify


def delete_optional_package(
    client,
    game_id: str,
    platform: str,
    channel: str,
    package_id: str,
    log=print,
) -> dict:
    """Delete one optional package release/tag/manifest and update catalog last."""
    game_id = slugify(game_id)
    platform = slugify(platform)
    channel = slugify(channel)
    package_id = slugify(package_id)
    catalog = load_catalog(client)
    game = next(
        (
            g
            for g in catalog.get("games", [])
            if g.get("id") == game_id and g.get("platform") == platform
        ),
        None,
    )
    if not game:
        raise KeyError(f"game not found: {platform}/{game_id}")
    data = (game.get("channels") or {}).get(channel)
    if not data:
        raise KeyError(f"channel not found: {channel}")
    packages = list(data.get("optional_packages") or [])
    package = next(
        (item for item in packages if slugify(str(item.get("id") or "")) == package_id),
        None,
    )
    if not package:
        raise KeyError(f"optional package not found: {package_id}")

    tag = str(package.get("tag") or "")
    release_deleted = False
    tag_deleted = False
    manifest_deleted = False
    if tag:
        release = client.release_by_tag(tag)
        if release is not None:
            log(f"Deleting optional package Release: {tag}")
            client.delete_release(int(release["id"]))
            release_deleted = True
        if client.delete_tag_ref(tag):
            tag_deleted = True
            log(f"Deleted optional package tag: {tag}")

    manifest_path = str(package.get("manifest_path") or "")
    if manifest_path:
        manifest_deleted = client.delete_repo_file(
            manifest_path,
            f"Delete optional package {package_id} manifest",
        )
        if manifest_deleted:
            log(f"Deleted optional package manifest: {manifest_path}")

    data["optional_packages"] = [
        item for item in packages if slugify(str(item.get("id") or "")) != package_id
    ]
    if not data["optional_packages"]:
        data.pop("optional_packages", None)
    catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert_text(
        CATALOG_NAME,
        json.dumps(catalog, ensure_ascii=False, indent=2),
        f"Delete optional package {package_id}",
    )
    log("Catalog updated after optional package cleanup completed")
    return {
        "package_id": package_id,
        "release_deleted": release_deleted,
        "tag_deleted": tag_deleted,
        "manifest_deleted": bool(manifest_deleted),
    }
