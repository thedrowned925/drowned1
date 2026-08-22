from __future__ import annotations

import json
import tempfile
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from .chunking import ChunkBuilder
from .constants import CATALOG_NAME, MANIFEST_NAME
from .direct_stream import DirectChunkReader, hash_source_files, plan_direct_stream
from .metadata import load_catalog
from .turbo_upload import DEFAULT_TURBO_WORKERS, TurboAssetUploader, choose_upload_plan
from .util import slugify


def addon_manifest_repo_path(
    platform: str,
    game_id: str,
    channel: str,
    base_version: str,
    package_id: str,
    package_version: str,
) -> str:
    return (
        f"manifests/{slugify(platform)}/{slugify(game_id)}/{slugify(channel)}/"
        f"{slugify(base_version)}/addons/{slugify(package_id)}/{slugify(package_version)}.json"
    )


def _find_target(catalog: dict, game_id: str, platform: str, channel: str, base_version: str):
    for game in catalog.get("games", []):
        if game.get("id") != game_id or game.get("platform") != platform:
            continue
        data = (game.get("channels") or {}).get(channel)
        if not data:
            raise KeyError(f"channel not found: {channel}")
        if str(data.get("version") or "") != str(base_version):
            raise ValueError(
                f"Base version changed: selected {base_version}, catalog has {data.get('version') or '?'}"
            )
        return game, data
    raise KeyError(f"game not found: {platform}/{game_id}")


def _existing_addon_paths(client, channel_data: dict) -> set[str]:
    result: set[str] = set()
    for package in channel_data.get("optional_packages") or []:
        path = str(package.get("manifest_path") or "")
        if not path:
            continue
        manifest = client.raw_json(path)
        if not manifest:
            continue
        result.update(str(item.get("path") or "") for item in manifest.get("files") or [])
    result.discard("")
    return result


def publish_optional_package(
    client,
    source: Path,
    game_id: str,
    platform: str,
    channel: str,
    base_version: str,
    package_title: str,
    package_id: str,
    package_version: str,
    description: str = "",
    progress=None,
    log=print,
    cancelled=lambda: False,
    upload_workers: int = DEFAULT_TURBO_WORKERS,
):
    """Publish one optional package without modifying the base-game manifest.

    Optional packages use the same Direct Stream protocol as normal games. The
    catalog entry is updated only after all assets and the package manifest are
    durable, so older Launchers can safely ignore the new metadata.
    """
    source = Path(source)
    game_id = slugify(game_id)
    platform = slugify(platform)
    channel = slugify(channel)
    package_id = slugify(package_id or package_title)
    package_title = str(package_title or package_id).strip()
    package_version = str(package_version or "1.0.0").strip()
    base_version = str(base_version or "").strip()
    if not package_title or not package_id or not base_version:
        raise ValueError("game, base version, package title/id and source are required")

    catalog = load_catalog(client)
    game, channel_data = _find_target(catalog, game_id, platform, channel, base_version)

    # Do not replace one package record in-place. Its old Release/tag/manifest
    # would become unreachable from catalog.json and leak storage. Revisions are
    # therefore explicit: remove the old package first, then publish the new one.
    existing_same = next(
        (
            item
            for item in channel_data.get("optional_packages") or []
            if slugify(str(item.get("id") or "")) == package_id
        ),
        None,
    )
    if existing_same:
        raise ValueError(
            f"Optional package ID already exists: {package_id}. "
            "Delete the existing package from Release Manager first, then publish its new version."
        )

    probe = ChunkBuilder(source)
    if probe.total_size <= 0:
        raise ValueError("optional package source folder is empty")
    balanced = choose_upload_plan(probe.total_size, upload_workers)
    chunk_size = int(balanced["chunk_size"])
    builder = ChunkBuilder(source, chunk_size=chunk_size)
    builder.validate_capacity()
    plan = plan_direct_stream(builder)
    planned_chunks = list(plan["chunks"])
    if len(planned_chunks) != int(balanced["chunk_count"]):
        raise RuntimeError("optional-package balanced planner mismatch")

    new_paths = {snap.rel for snap in plan["snapshots"]}
    occupied = _existing_addon_paths(client, channel_data)
    collision = sorted(new_paths & occupied)
    if collision:
        preview = "\n".join(collision[:12])
        more = "" if len(collision) <= 12 else f"\n… +{len(collision) - 12} more"
        raise ValueError(
            "Two optional packages cannot own the same relative file path. "
            "Move/merge the colliding files into one package:\n" + preview + more
        )

    workers = max(1, min(int(balanced["workers"]), len(planned_chunks)))
    waves = int(balanced["waves"])
    tag = (
        f"{platform}-{game_id}-v{slugify(base_version)}-{channel}-"
        f"addon-{package_id}-v{slugify(package_version)}"
    )
    prerelease = channel in {"beta", "dev", "nightly"}
    log(
        f"Optional package Direct Stream: {workers} stream • {waves} wave • "
        f"{chunk_size / 1024 / 1024:.1f} MiB target chunk • {len(planned_chunks)} asset"
    )

    rel = client.create_release(
        tag,
        f"{game.get('title', game_id)} — {package_title} {package_version}",
        description or f"Optional package: {package_title}",
        prerelease,
    )
    rid = int(rel["id"])
    uploader = TurboAssetUploader(client, rid)
    abort = threading.Event()
    progress_lock = threading.Lock()
    sent_by_chunk: dict[int, int] = {}
    completed: list[tuple[int, dict]] = []

    def is_cancelled():
        return bool(cancelled()) or abort.is_set()

    def report(index: int, sent: int):
        with progress_lock:
            sent_by_chunk[index] = max(0, int(sent))
            aggregate = min(sum(sent_by_chunk.values()), builder.total_size)
        if progress:
            progress(aggregate, builder.total_size)

    def upload_one(index: int, meta: dict):
        if is_cancelled():
            raise RuntimeError("cancelled")
        _, chunk_sha = uploader.upload_stream(
            meta["name"],
            int(meta["size"]),
            reader_factory=lambda: DirectChunkReader(
                meta,
                plan["snapshot_map"],
                progress=lambda sent, total: report(index, sent),
                cancelled=is_cancelled,
            ),
            progress=lambda sent, total: report(index, sent),
        )
        finished = dict(meta)
        finished["sha256"] = chunk_sha
        report(index, int(meta["size"]))
        log(f"Uploaded add-on chunk: {meta['name']}")
        return index, finished

    file_hash_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drowned-addon-hash")
    files_future = file_hash_pool.submit(hash_source_files, plan["snapshots"], is_cancelled)
    try:
        pending = set()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="drowned-addon-upload") as pool:
            for index, meta in enumerate(planned_chunks, start=1):
                pending.add(pool.submit(upload_one, index, meta))
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    completed.append(future.result())
        files_meta = files_future.result()
    except Exception:
        abort.set()
        raise
    finally:
        file_hash_pool.shutdown(wait=True, cancel_futures=True)

    completed.sort(key=lambda pair: pair[0])
    manifest_path = addon_manifest_repo_path(
        platform, game_id, channel, base_version, package_id, package_version
    )
    manifest = {
        "schema_version": 1,
        "package_type": "optional",
        "package": {
            "id": package_id,
            "title": package_title,
            "version": package_version,
            "description": description,
        },
        "base": {
            "game_id": game_id,
            "platform": platform,
            "channel": channel,
            "version": base_version,
        },
        "release": {
            "owner": client.owner,
            "repo": client.repo,
            "tag": tag,
        },
        "chunk_size": chunk_size,
        "upload_workers": workers,
        "upload_waves": waves,
        "total_size": builder.total_size,
        "files": files_meta,
        "chunks": [meta for _, meta in completed],
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)

    with tempfile.TemporaryDirectory(prefix="drowned-addon-meta-") as td:
        manifest_file = Path(td) / MANIFEST_NAME
        manifest_file.write_text(manifest_text, encoding="utf-8")
        client.upload_asset(rid, MANIFEST_NAME, manifest_file, "application/json")

    client.upsert_text(
        manifest_path,
        manifest_text,
        f"Publish optional package {package_title} {package_version}",
    )
    manifest_url = client.raw_url(manifest_path)

    record = {
        "id": package_id,
        "title": package_title,
        "description": description,
        "version": package_version,
        "tag": tag,
        "manifest_path": manifest_path,
        "manifest_url": manifest_url,
        "size": builder.total_size,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    packages = list(channel_data.get("optional_packages") or [])
    packages.append(record)
    packages.sort(key=lambda item: str(item.get("title") or item.get("id") or "").lower())
    channel_data["optional_packages"] = packages
    catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert_text(
        CATALOG_NAME,
        json.dumps(catalog, ensure_ascii=False, indent=2),
        f"Attach optional package {package_title} to {game.get('title', game_id)}",
    )
    client.publish_release(rid, prerelease)
    if progress:
        progress(builder.total_size, builder.total_size)
    return manifest
