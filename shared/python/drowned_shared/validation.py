from __future__ import annotations
from collections import defaultdict
from .errors import ManifestError
from .util import safe_relative_path


def validate_manifest(m: dict) -> dict:
    try:
        if m.get("schema_version") != 1: raise ManifestError("unsupported manifest schema")
        files=m["files"]; chunks=m["chunks"]
        if not isinstance(files, list) or not isinstance(chunks, list): raise ManifestError("files/chunks must be lists")
        file_sizes={}
        for f in files:
            p=str(safe_relative_path(f["path"]))
            size=int(f["size"])
            if size < 0 or p in file_sizes: raise ManifestError("duplicate/invalid file")
            file_sizes[p]=size
        seen_chunk_names=set()
        coverage=defaultdict(list)
        for c in chunks:
            name=c["name"]
            if name in seen_chunk_names: raise ManifestError("duplicate chunk")
            seen_chunk_names.add(name)
            csize=int(c["size"])
            if csize < 0: raise ManifestError("negative chunk size")
            for s in c.get("segments", []):
                path=str(safe_relative_path(s["file"]))
                if path not in file_sizes: raise ManifestError("segment references missing file")
                fo,co,l=map(int,(s["file_offset"],s["chunk_offset"],s["length"]))
                if min(fo,co,l) < 0 or l == 0: raise ManifestError("invalid segment offsets")
                if fo+l > file_sizes[path] or co+l > csize: raise ManifestError("segment overflow")
                coverage[path].append((fo,fo+l))
        for path,size in file_sizes.items():
            ranges=sorted(coverage[path])
            cursor=0
            for start,end in ranges:
                if start != cursor: raise ManifestError(f"segment gap/overlap in {path}")
                cursor=end
            if cursor != size: raise ManifestError(f"segment coverage mismatch in {path}")
        if sum(int(c["size"]) for c in chunks) != int(m.get("total_size", -1)): raise ManifestError("total size mismatch")
        return m
    except ManifestError: raise
    except Exception as e: raise ManifestError(str(e)) from e


def parse_catalog(value: dict) -> dict:
    if value.get("schema_version") != 1 or not isinstance(value.get("games"), list):
        raise ManifestError("invalid catalog")
    return value
