from __future__ import annotations

import json
import tempfile
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from .chunking import ChunkBuilder
from .constants import CATALOG_NAME, MANIFEST_NAME
from .direct_stream import DirectChunkReader, hash_source_files, plan_direct_stream
from .metadata import load_catalog, manifest_repo_path
from .turbo_upload import (
    DEFAULT_TURBO_WORKERS,
    TurboAssetUploader,
    choose_upload_plan,
)
from .util import slugify


def publish_project(
    client,
    source: Path,
    title: str,
    platform: str,
    channel: str,
    version: str,
    description: str = "",
    artwork: dict | None = None,
    progress=None,
    log=print,
    cancelled=lambda: False,
    upload_workers: int = DEFAULT_TURBO_WORKERS,
    media: dict | None = None,
    detailed_progress=None,
):
    game_id = slugify(title)
    platform = slugify(platform)
    channel = slugify(channel)
    tag = f"{platform}-{game_id}-v{version}-{channel}"

    source = Path(source)
    probe = ChunkBuilder(source)
    balanced = choose_upload_plan(probe.total_size, upload_workers)
    chunk_size = int(balanced["chunk_size"])
    builder = ChunkBuilder(source, chunk_size=chunk_size)
    builder.validate_capacity()

    # Direct Stream creates only a lightweight segment map. No large staging
    # files are materialized on disk.
    plan = plan_direct_stream(builder)
    planned_chunks = list(plan["chunks"])
    expected_chunks = int(balanced["chunk_count"])
    if len(planned_chunks) != expected_chunks:
        raise RuntimeError(
            f"balanced planner mismatch: expected {expected_chunks} chunks, "
            f"direct planner produced {len(planned_chunks)}"
        )

    workers = int(balanced["workers"])
    waves = int(balanced["waves"])
    if planned_chunks:
        workers = min(workers, len(planned_chunks))
    workers = max(1, workers)
    prerelease = channel in {"beta", "dev", "nightly"}

    file_sizes = {item.rel: item.size for item in plan["snapshots"]}

    log(
        "Balanced Direct Stream: "
        f"{workers} parallel stream • {waves} full wave • "
        f"chunk {chunk_size / 1024 / 1024:.1f} MiB • "
        f"{len(planned_chunks)} data asset • temp BIN 0 B"
    )

    if detailed_progress:
        detailed_progress({
            "phase": "plan",
            "total_sent": 0,
            "total_size": builder.total_size,
            "workers": workers,
            "waves": waves,
            "chunk_size": chunk_size,
            "chunk_count": len(planned_chunks),
            "completed_chunks": 0,
            "active": [],
        })

    rel = client.create_release(
        tag,
        f"{title} {version} [{platform.upper()} / {channel}]",
        description or title,
        prerelease,
    )
    rid = rel["id"]

    chunk_meta: list[tuple[int, dict]] = []
    progress_lock = threading.Lock()
    sent_by_chunk: dict[int, int] = {}
    active_chunks: dict[int, dict] = {}
    active_segments: dict[int, dict[str, dict]] = {}
    completed_file_bytes: dict[str, int] = {}
    last_progress_emit = [0.0]
    abort = threading.Event()

    def is_cancelled():
        return bool(cancelled()) or abort.is_set()

    def _segment_prefix_bytes(segment: dict, sent: int) -> int:
        start = int(segment.get("chunk_offset") or 0)
        length = int(segment.get("length") or 0)
        return max(0, min(int(sent) - start, length))

    def _current_segment(meta: dict, sent: int):
        segments = list(meta.get("segments") or [])
        if not segments:
            return None
        position = max(0, min(int(sent), int(meta.get("size") or 0)))
        for segment in segments:
            start = int(segment.get("chunk_offset") or 0)
            end = start + int(segment.get("length") or 0)
            if position < end:
                return segment
        return segments[-1]

    def _snapshot_locked(phase: str = "upload"):
        aggregate = min(sum(sent_by_chunk.values()), builder.total_size)
        active_rows = []
        for index, state in sorted(active_chunks.items()):
            meta = state["meta"]
            sent = max(0, min(int(sent_by_chunk.get(index, 0)), int(meta.get("size") or 0)))
            segment = _current_segment(meta, sent)
            file_path = str((segment or {}).get("file") or "")
            file_size = int(file_sizes.get(file_path, 0))
            file_sent = int(completed_file_bytes.get(file_path, 0))
            if file_path:
                for other_index in active_chunks:
                    other_segment = active_segments.get(other_index, {}).get(file_path)
                    if other_segment is None:
                        continue
                    file_sent += _segment_prefix_bytes(
                        other_segment,
                        int(sent_by_chunk.get(other_index, 0)),
                    )
                file_sent = max(0, min(file_sent, file_size)) if file_size else max(0, file_sent)

            active_rows.append({
                "index": int(index),
                "chunk": str(meta.get("name") or f"chunk-{index:06d}.bin"),
                "chunk_sent": sent,
                "chunk_size": int(meta.get("size") or 0),
                "file": file_path,
                "file_sent": file_sent,
                "file_size": file_size,
            })

        return {
            "phase": phase,
            "total_sent": aggregate,
            "total_size": builder.total_size,
            "workers": workers,
            "waves": waves,
            "chunk_size": chunk_size,
            "chunk_count": len(planned_chunks),
            "completed_chunks": len(chunk_meta),
            "active": active_rows,
        }

    def report_chunk_progress(index: int, sent: int):
        now = time.monotonic()
        snapshot = None
        aggregate = 0
        emit = False
        with progress_lock:
            sent_by_chunk[index] = max(0, int(sent))
            if now - last_progress_emit[0] >= 0.25:
                last_progress_emit[0] = now
                aggregate = min(sum(sent_by_chunk.values()), builder.total_size)
                emit = True
                if detailed_progress:
                    snapshot = _snapshot_locked("upload")
        if not emit:
            return
        if progress:
            progress(aggregate, builder.total_size)
        if detailed_progress and snapshot is not None:
            detailed_progress(snapshot)

    uploader = TurboAssetUploader(client, rid)

    def upload_one(index: int, meta: dict):
        if is_cancelled():
            raise RuntimeError("cancelled")

        log(
            f"Direct uploading {meta['name']} • "
            f"{meta['size'] / 1024 / 1024:.1f} MiB"
        )
        with progress_lock:
            active_chunks[index] = {"meta": meta}
            active_segments[index] = {
                str(segment.get("file") or ""): segment
                for segment in (meta.get("segments") or [])
                if segment.get("file")
            }
            sent_by_chunk[index] = 0
            start_snapshot = _snapshot_locked("upload") if detailed_progress else None
        if detailed_progress and start_snapshot is not None:
            detailed_progress(start_snapshot)

        _, chunk_sha = uploader.upload_stream(
            meta["name"],
            int(meta.get("size") or 0),
            reader_factory=lambda: DirectChunkReader(
                meta,
                plan["snapshot_map"],
                progress=lambda sent, total, idx=index: report_chunk_progress(idx, sent),
                cancelled=is_cancelled,
            ),
            progress=lambda sent, total, idx=index: report_chunk_progress(idx, sent),
        )

        completed_meta = dict(meta)
        completed_meta["sha256"] = chunk_sha

        with progress_lock:
            sent_by_chunk[index] = int(meta.get("size") or 0)
            for segment in meta.get("segments") or []:
                file_path = str(segment.get("file") or "")
                if not file_path:
                    continue
                completed_file_bytes[file_path] = (
                    int(completed_file_bytes.get(file_path, 0))
                    + int(segment.get("length") or 0)
                )
            active_chunks.pop(index, None)
            active_segments.pop(index, None)
            completed_snapshot = _snapshot_locked("upload") if detailed_progress else None

        if progress:
            with progress_lock:
                aggregate = min(sum(sent_by_chunk.values()), builder.total_size)
            progress(aggregate, builder.total_size)
        if detailed_progress and completed_snapshot is not None:
            detailed_progress(completed_snapshot)
        return index, completed_meta

    # File SHA-256 is calculated sequentially in one background reader while the
    # network workers upload logical chunks. On SSD/NVMe the extra read is hidden
    # behind the much slower network transfer.
    file_hash_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drowned-filehash")
    files_future = file_hash_pool.submit(hash_source_files, plan["snapshots"], is_cancelled)

    try:
        pending = set()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="drowned-direct") as pool:
            for index, meta in enumerate(planned_chunks, start=1):
                if is_cancelled():
                    raise RuntimeError("cancelled")
                pending.add(pool.submit(upload_one, index, meta))

            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    chunk_meta.append(future.result())

        files_meta = files_future.result()
    except Exception:
        abort.set()
        raise
    finally:
        file_hash_pool.shutdown(wait=True, cancel_futures=True)

    chunk_meta.sort(key=lambda pair: pair[0])
    ordered_chunks = [meta for _, meta in chunk_meta]

    if progress:
        progress(builder.total_size, builder.total_size)
    if detailed_progress:
        detailed_progress({
            "phase": "metadata",
            "total_sent": builder.total_size,
            "total_size": builder.total_size,
            "workers": workers,
            "waves": waves,
            "chunk_size": chunk_size,
            "chunk_count": len(planned_chunks),
            "completed_chunks": len(ordered_chunks),
            "active": [],
        })

    manifest = {
        "schema_version": 1,
        "game": {
            "id": game_id,
            "title": title,
            "platform": platform,
            "channel": channel,
            "version": version,
            "description": description,
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
        "chunks": ordered_chunks,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)

    # Only the tiny JSON manifest needs a temporary file because the metadata
    # helper accepts a path. No game data is staged on disk.
    with tempfile.TemporaryDirectory(prefix="drowned-meta-") as td:
        manifest_file = Path(td) / MANIFEST_NAME
        manifest_file.write_text(manifest_text, encoding="utf-8")
        client.upload_asset(rid, MANIFEST_NAME, manifest_file, "application/json")

    manifest_path = manifest_repo_path(platform, game_id, channel, version)
    client.upsert_text(manifest_path, manifest_text, f"Publish {title} {version} manifest")
    manifest_url = client.raw_url(manifest_path)

    art_urls = {}
    for kind, raw in (artwork or {}).items():
        if not raw:
            continue
        if kind == "screenshots":
            urls = []
            for index, shot in enumerate(raw):
                if not shot:
                    continue
                p = Path(shot)
                repo_path = f"artwork/{platform}/{game_id}/screenshots/{index:02d}{p.suffix.lower()}"
                client.upsert_bytes(repo_path, p.read_bytes(), f"Update {title} screenshot {index + 1}")
                urls.append(client.raw_url(repo_path))
            if urls:
                art_urls["screenshots"] = urls
            continue
        p = Path(raw)
        repo_path = f"artwork/{platform}/{game_id}/{kind}{p.suffix.lower()}"
        client.upsert_bytes(repo_path, p.read_bytes(), f"Update {title} {kind}")
        art_urls[kind] = client.raw_url(repo_path)

    catalog = load_catalog(client)
    game = next(
        (
            g
            for g in catalog["games"]
            if g.get("id") == game_id and g.get("platform") == platform
        ),
        None,
    )
    if not game:
        game = {
            "id": game_id,
            "title": title,
            "platform": platform,
            "description": description,
            "artwork": {},
            "channels": {},
        }
        catalog["games"].append(game)

    game["title"] = title
    game["description"] = description
    game["artwork"].update(art_urls)
    if media:
        game.setdefault("media", {}).update(media)
    game["channels"][channel] = {
        "version": version,
        "tag": tag,
        "manifest_path": manifest_path,
        "manifest_url": manifest_url,
        "size": builder.total_size,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert_text(
        CATALOG_NAME,
        json.dumps(catalog, ensure_ascii=False, indent=2),
        f"Publish {title} {version}",
    )
    client.publish_release(rid, prerelease)
    return manifest
