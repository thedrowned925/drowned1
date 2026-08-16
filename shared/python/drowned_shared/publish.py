from __future__ import annotations
import json,tempfile,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from .chunking import ChunkBuilder
from .constants import MANIFEST_NAME,CATALOG_NAME,CHUNK_SIZE_BYTES,STARTER_CHUNK_SIZE_BYTES
from .metadata import load_catalog, manifest_repo_path
from .util import slugify


def publish_project(client, source:Path, title:str, platform:str, channel:str, version:str, description:str="", artwork:dict|None=None, progress=None, log=print, cancelled=lambda:False):
    game_id=slugify(title); platform=slugify(platform); channel=slugify(channel); tag=f"{platform}-{game_id}-v{version}-{channel}"
    builder=ChunkBuilder(source,starter_chunk_size=STARTER_CHUNK_SIZE_BYTES); builder.validate_capacity(); prerelease=channel in {"beta","dev","nightly"}
    rel=client.create_release(tag,f"{title} {version} [{platform.upper()} / {channel}]",description or title,prerelease); rid=rel["id"]
    chunk_meta=[]

    with tempfile.TemporaryDirectory(prefix="drowned-") as td:
        gen=builder.build(Path(td))
        current_future=None
        current_chunk=None
        uploaded_bytes=0

        def submit_upload(pool,built,base_bytes):
            last_emit=[0.0]
            def upload_progress(sent,total):
                if not progress: return
                now=time.monotonic()
                # PyInstaller/PySide apps can emit thousands of progress signals
                # during one large upload. Throttle them to ~4 updates/second.
                if sent == total or now-last_emit[0] >= 0.25:
                    last_emit[0]=now
                    progress(base_bytes+sent,builder.total_size)
            log(f"Uploading {built.meta['name']} ({built.meta['size']} bytes)")
            return pool.submit(client.upload_asset,rid,built.meta["name"],built.path,"application/octet-stream",upload_progress)

        # GitHub recommends avoiding concurrent mutating REST requests. We keep
        # exactly one upload POST active, but build the NEXT chunk at the same
        # time. This hides most disk/hash preparation time without increasing
        # secondary-rate-limit pressure.
        with ThreadPoolExecutor(max_workers=1,thread_name_prefix="drowned-upload") as pool:
            while True:
                if cancelled(): raise RuntimeError("cancelled")
                try:
                    built=next(gen)
                except StopIteration as stop:
                    result=stop.value
                    break

                if current_future is None:
                    current_chunk=built
                    current_future=submit_upload(pool,built,uploaded_bytes)
                    continue

                # While the previous asset was uploading, the generator above
                # prepared this new chunk. Only wait here if the network is
                # slower than local chunk preparation.
                current_future.result()
                uploaded_bytes+=current_chunk.meta["size"]
                chunk_meta.append(current_chunk.meta)
                current_chunk.path.unlink(missing_ok=True)
                if progress: progress(uploaded_bytes,builder.total_size)
                if cancelled(): raise RuntimeError("cancelled")

                current_chunk=built
                current_future=submit_upload(pool,built,uploaded_bytes)

            if current_future is not None:
                current_future.result()
                uploaded_bytes+=current_chunk.meta["size"]
                chunk_meta.append(current_chunk.meta)
                current_chunk.path.unlink(missing_ok=True)
                if progress: progress(uploaded_bytes,builder.total_size)

        manifest={"schema_version":1,"game":{"id":game_id,"title":title,"platform":platform,"channel":channel,"version":version,"description":description},"release":{"owner":client.owner,"repo":client.repo,"tag":tag},"chunk_size":CHUNK_SIZE_BYTES,"starter_chunk_size":STARTER_CHUNK_SIZE_BYTES,"total_size":result["total_size"],"files":result["files"],"chunks":chunk_meta}
        manifest_text=json.dumps(manifest,ensure_ascii=False,indent=2)
        mp=Path(td)/MANIFEST_NAME; mp.write_text(manifest_text,encoding="utf-8"); client.upload_asset(rid,MANIFEST_NAME,mp,"application/json")

    # Small metadata lives in the repository so clients read it through raw.githubusercontent.com
    # instead of spending REST API quota. Release assets remain the large binary transport.
    manifest_path=manifest_repo_path(platform,game_id,channel,version)
    client.upsert_text(manifest_path,manifest_text,f"Publish {title} {version} manifest")
    manifest_url=client.raw_url(manifest_path)

    art_urls={}
    for kind,raw in (artwork or {}).items():
        if not raw: continue
        p=Path(raw); repo_path=f"artwork/{platform}/{game_id}/{kind}{p.suffix.lower()}"; client.upsert_bytes(repo_path,p.read_bytes(),f"Update {title} {kind}")
        art_urls[kind]=client.raw_url(repo_path)

    catalog=load_catalog(client)
    game=next((g for g in catalog["games"] if g.get("id")==game_id and g.get("platform")==platform),None)
    if not game:
        game={"id":game_id,"title":title,"platform":platform,"description":description,"artwork":{},"channels":{}}; catalog["games"].append(game)
    game["title"]=title; game["description"]=description; game["artwork"].update(art_urls)
    game["channels"][channel]={"version":version,"tag":tag,"manifest_path":manifest_path,"manifest_url":manifest_url,"size":result["total_size"],"published_at":datetime.now(timezone.utc).isoformat()}
    catalog["updated_at"]=datetime.now(timezone.utc).isoformat(); client.upsert_text(CATALOG_NAME,json.dumps(catalog,ensure_ascii=False,indent=2),f"Publish {title} {version}")
    client.publish_release(rid,prerelease); return manifest
