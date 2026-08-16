from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path
import requests
from .errors import DiskSpaceError, HashMismatchError
from .util import atomic_json, safe_relative_path, sha256_file
from .validation import validate_manifest


def fetch_json(url:str)->dict:
    r=requests.get(url,timeout=60,headers={"User-Agent":"Drowned-Launcher/0.1"}); r.raise_for_status(); return r.json()


def install_manifest(manifest:dict, root:Path, progress=lambda p,t:None, log=print, cancelled=lambda:False):
    validate_manifest(manifest); root=Path(root); root.mkdir(parents=True,exist_ok=True)
    needed=int(manifest["total_size"]); free=shutil.disk_usage(root).free
    if free < needed: raise DiskSpaceError(f"requires {needed} bytes; {free} free")
    state_path=root/".drowned"/"state.json"; state_path.parent.mkdir(exist_ok=True)
    try: state=json.loads(state_path.read_text())
    except Exception: state={}
    tag=manifest["release"]["tag"]
    if state.get("tag") != tag: state={"tag":tag,"completed_chunks":[]}
    completed=set(state["completed_chunks"])
    for f in manifest["files"]:
        p=root/safe_relative_path(f["path"]); p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists() or p.stat().st_size != int(f["size"]):
            with p.open("wb") as out: out.truncate(int(f["size"]))
    total=needed; done=sum(c["size"] for c in manifest["chunks"] if c["name"] in completed)
    headers={"User-Agent":"Drowned-Launcher/0.1"}
    for c in manifest["chunks"]:
        if c["name"] in completed: continue
        if cancelled(): raise RuntimeError("cancelled")
        url=f"https://github.com/{manifest['release']['owner']}/{manifest['release']['repo']}/releases/download/{tag}/{c['name']}"
        ok=False
        for attempt in range(3):
            h=hashlib.sha256(); pos=0; segi=0; current=None; fp=None
            try:
                with requests.get(url,stream=True,timeout=(30,300),headers=headers) as r:
                    r.raise_for_status()
                    for block in r.iter_content(8*1024*1024):
                        if not block: continue
                        h.update(block); mv=memoryview(block); used=0
                        while used < len(mv):
                            seg=c["segments"][segi]; seg_end=seg["chunk_offset"]+seg["length"]
                            if pos >= seg_end: segi+=1; continue
                            take=min(len(mv)-used,seg_end-pos); target=root/safe_relative_path(seg["file"])
                            if current != target:
                                if fp: fp.close()
                                current=target; fp=target.open("r+b")
                            within=pos-seg["chunk_offset"]; fp.seek(seg["file_offset"]+within); fp.write(mv[used:used+take]); used+=take; pos+=take; progress(done+pos,total)
                if fp: fp.close()
            except Exception:
                if fp: fp.close()
                if attempt==2: raise
                continue
            if h.hexdigest()==c["sha256"]: ok=True; break
        if not ok: raise HashMismatchError(c["name"])
        done+=c["size"]; completed.add(c["name"]); state["completed_chunks"]=sorted(completed); atomic_json(state_path,state); log(f"Verified {c['name']}")
    for f in manifest["files"]:
        p=root/safe_relative_path(f["path"])
        if sha256_file(p) != f["sha256"]: raise HashMismatchError(f["path"])
    state["verified"]=True; atomic_json(state_path,state); return True
