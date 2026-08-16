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
from .metadata import load_catalog, manifest_repo_path
from .turbo_upload import (
    DEFAULT_TURBO_WORKERS,
    TurboAssetUploader,
    choose_upload_chunk_size,
    effective_worker_count,
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
):
    game_id = slugify(title)
    platform = slugify(platform)
    channel = slugify(channel)
    tag = f"{platform}-{game_id}-v{version}-{channel}"

    source = Path(source)
    probe = ChunkBuilder(source)
    chunk_size = choose_upload_chunk_size(probe.total_size, upload_workers)
    builder = ChunkBuilder(source, chunk_size=chunk_size)
    builder.validate_capacity()
    workers = effective_worker_count(chunk_size, upload_workers)
    prerelease = channel in {"beta", "dev", "nightly"}

    log(
        "Turbo upload: "
        f"{workers} parallel stream • chunk {chunk_size / 1024 / 1024:.0f} MiB • "
        f"{builder.chunk_count} data asset"
    )

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
    last_progress_emit = [0.0]

    with tempfile.TemporaryDirectory(prefix="drowned-") as td:
        gen = builder.build(Path(td))
        uploader = TurboAssetUploader(client, rid)

        def report_chunk_progress(index: int, sent: int):
            if not progress:
                return
            now = time.monotonic()
            with progress_lock:
                sent_by_chunk[index] = sent
                if now - last_progress_emit[0] < 0.25 and sent < builder.total_size:
                    return
                last_progress_emit[0] = now
                aggregate = min(sum(sent_by_chunk.values()), builder.total_size)
            progress(aggregate, builder.total_size)

        def upload_one(built):
            if cancelled():
                raise RuntimeError("cancelled")
            log(
                f"Uploading {built.meta['name']} • "
                f"{built.meta['size'] / 1024 / 1024:.1f} MiB"
            )
            uploader.upload(
                built.meta["name"],
                built.path,
                progress=lambda sent, total, idx=built.index: report_chunk_progress(idx, sent),
            )
            built.path.unlink(missing_ok=True)
            return built.index, built.meta

        pending = set()
        result = None
        queue_limit = max(workers + 2, workers * 2)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="drowned-turbo") as pool:
            while True:
                if cancelled():
                    raise RuntimeError("cancelled")
                try:
                    built = next(gen)
                except StopIteration as stop:
                    result = stop.value
                    break

                pending.add(pool.submit(upload_one, built))

                # Bound temporary disk usage. Chunk building can stay ahead of the
                # network, but not enough to make a second full copy of the game.
                if len(pending) >= queue_limit:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        chunk_meta.append(future.result())

            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    chunk_meta.append(future.result())

        if result is None:
            result = {"total_size": builder.total_size, "files": [], "chunks": []}

        chunk_meta.sort(key=lambda pair: pair[0])
        ordered_chunks = [meta for _, meta in chunk_meta]
        if progress:
            progress(builder.total_size, builder.total_size)

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
            "total_size": result["total_size"],
            "files": result["files"],
            "chunks": ordered_chunks,
        }
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
        manifest_file = Path(td) / MANIFEST_NAME
        manifest_file.write_text(manifest_text, encoding="utf-8")
        client.upload_asset(rid, MANIFEST_NAME, manifest_file, "application/json")

    # Small metadata lives in the repository so clients read it through raw.githubusercontent.com
    # instead of spending REST API quota. Release assets remain the large binary transport.
    manifest_path = manifest_repo_path(platform, game_id, channel, version)
    client.upsert_text(manifest_path, manifest_text, f"Publish {title} {version} manifest")
    manifest_url = client.raw_url(manifest_path)

    art_urls = {}
    for kind, raw in (artwork or {}).items():
        if not raw:
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
    game["channels"][channel] = {
        "version": version,
        "tag": tag,
        "manifest_path": manifest_path,
        "manifest_url": manifest_url,
        "size": result["total_size"],
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
