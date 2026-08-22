from __future__ import annotations

import json
from datetime import datetime, timezone

from .constants import CATALOG_NAME
from .metadata import load_catalog, manifest_repo_path, repo_path_from_raw_url


def _find_game(catalog: dict, game_id: str, platform: str) -> dict:
    for game in catalog.get("games", []):
        if game.get("id") == game_id and game.get("platform") == platform:
            return game
    raise KeyError(f"game not found: {platform}/{game_id}")


def _channel_resources(channel_data: dict) -> list[dict]:
    """Return base release metadata followed by every optional package."""
    return [channel_data, *list(channel_data.get("optional_packages") or [])]


def _other_channel_refs(
    catalog: dict,
    target_game: dict,
    removed_channels: set[str],
) -> tuple[set[str], set[str]]:
    tags: set[str] = set()
    manifests: set[str] = set()
    for game in catalog.get("games", []):
        for channel, data in (game.get("channels") or {}).items():
            if game is target_game and channel in removed_channels:
                continue
            for resource in _channel_resources(data):
                tag = resource.get("tag")
                if tag:
                    tags.add(tag)
                path = resource.get("manifest_path")
                if path:
                    manifests.add(path)
    return tags, manifests


def _flatten_artwork_value(value) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [item for item in values if isinstance(item, str) and item]


def _other_artwork_urls(catalog: dict, target_game: dict) -> set[str]:
    urls: set[str] = set()
    for game in catalog.get("games", []):
        if game is target_game:
            continue
        for value in (game.get("artwork") or {}).values():
            urls.update(_flatten_artwork_value(value))
    return urls


def _delete_release_record(client, data: dict, log, protected_tags: set[str]) -> tuple[bool, bool]:
    tag = data.get("tag")
    if not tag:
        raise ValueError("catalog release record has no tag")
    if tag in protected_tags:
        log(f"Shared Release/tag retained because another catalog entry still references it: {tag}")
        return False, False

    release_deleted = False
    tag_deleted = False
    release = client.release_by_tag(tag)
    if release is None:
        log(f"Release already absent: {tag}")
    else:
        log(f"Deleting GitHub Release and all attached assets: {tag}")
        client.delete_release(int(release["id"]))
        release_deleted = True
        log(f"Deleted release: {tag}")

    if client.delete_tag_ref(tag):
        tag_deleted = True
        log(f"Deleted Git tag: {tag}")
    else:
        log(f"Git tag already absent: {tag}")
    return release_deleted, tag_deleted


def _delete_manifest_record(
    client,
    data: dict,
    log,
    protected_paths: set[str],
    *,
    fallback_path: str | None = None,
) -> bool:
    path = data.get("manifest_path") or fallback_path
    if not path:
        log("Manifest path absent; nothing to delete")
        return False
    if path in protected_paths:
        log(f"Shared raw manifest retained because another catalog entry still references it: {path}")
        return False
    if client.delete_repo_file(path, f"Delete manifest {path}"):
        log(f"Deleted raw manifest: {path}")
        return True
    log(f"Manifest already absent: {path}")
    return False


def _delete_channel_resources(
    client,
    game: dict,
    channel: str,
    data: dict,
    log,
    protected_tags: set[str],
    protected_paths: set[str],
) -> tuple[int, int, int]:
    releases = tags = manifests = 0

    rd, td = _delete_release_record(client, data, log, protected_tags)
    releases += int(rd)
    tags += int(td)
    fallback = manifest_repo_path(
        game["platform"], game["id"], channel, data.get("version", "unknown")
    )
    manifests += int(
        _delete_manifest_record(
            client, data, log, protected_paths, fallback_path=fallback
        )
    )

    for package in list(data.get("optional_packages") or []):
        title = package.get("title") or package.get("id") or "optional package"
        log(f"Cleaning optional package: {title}")
        rd, td = _delete_release_record(client, package, log, protected_tags)
        releases += int(rd)
        tags += int(td)
        manifests += int(
            _delete_manifest_record(client, package, log, protected_paths)
        )

    return releases, tags, manifests


def _delete_artwork(client, catalog: dict, game: dict, log):
    deleted = []
    protected_urls = _other_artwork_urls(catalog, game)
    for kind, value in list((game.get("artwork") or {}).items()):
        for url in _flatten_artwork_value(value):
            if url in protected_urls:
                log(f"Shared artwork retained because another catalog entry still references it ({kind})")
                continue
            path = repo_path_from_raw_url(client, url)
            if not path:
                log(f"Skipping non-repository artwork URL ({kind})")
                continue
            if client.delete_repo_file(path, f"Delete {game['title']} {kind} artwork"):
                deleted.append(path)
                log(f"Deleted artwork: {path}")
            else:
                log(f"Artwork already absent: {path}")
    return deleted


def _commit_catalog(client, catalog: dict, message: str):
    catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert_text(
        CATALOG_NAME,
        json.dumps(catalog, ensure_ascii=False, indent=2),
        message,
    )


def delete_channel(client, game_id: str, platform: str, channel: str, log=print) -> dict:
    """Delete a base channel plus all optional-package releases, then catalog."""
    catalog = load_catalog(client)
    game = _find_game(catalog, game_id, platform)
    channels = game.get("channels") or {}
    if channel not in channels:
        raise KeyError(f"channel not found: {channel}")

    protected_tags, protected_paths = _other_channel_refs(catalog, game, {channel})
    data = dict(channels[channel])
    releases, tags, manifests = _delete_channel_resources(
        client,
        game,
        channel,
        data,
        log,
        protected_tags,
        protected_paths,
    )

    del channels[channel]
    artwork = []
    removed_game = False
    if not channels:
        artwork = _delete_artwork(client, catalog, game, log)
        catalog["games"].remove(game)
        removed_game = True
    else:
        game["channels"] = channels

    _commit_catalog(client, catalog, f"Delete {game['title']} {channel}")
    log("Catalog updated after base and optional-package cleanup completed")
    return {
        "game_removed": removed_game,
        "channels_removed": [channel],
        "releases_deleted": releases,
        "tags_deleted": tags,
        "manifests_deleted": manifests,
        "artwork_deleted": artwork,
    }


def delete_game(client, game_id: str, platform: str, log=print) -> dict:
    """Delete every base/add-on release and manifest before removing the game."""
    catalog = load_catalog(client)
    game = _find_game(catalog, game_id, platform)
    channels = dict(game.get("channels") or {})
    protected_tags, protected_paths = _other_channel_refs(catalog, game, set(channels))
    releases = tags = manifests = 0

    for channel, data in channels.items():
        rd, td, md = _delete_channel_resources(
            client,
            game,
            channel,
            data,
            log,
            protected_tags,
            protected_paths,
        )
        releases += rd
        tags += td
        manifests += md

    artwork = _delete_artwork(client, catalog, game, log)
    catalog["games"].remove(game)
    _commit_catalog(client, catalog, f"Delete {game['title']} completely")
    log("Game removed from catalog after base and optional-package cleanup completed")
    return {
        "game_removed": True,
        "channels_removed": list(channels),
        "releases_deleted": releases,
        "tags_deleted": tags,
        "manifests_deleted": manifests,
        "artwork_deleted": artwork,
    }
