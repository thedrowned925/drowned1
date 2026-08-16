from __future__ import annotations
import hashlib, math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator
from .constants import CHUNK_SIZE_BYTES, MAX_DATA_ASSETS
from .errors import SourceChangedError
from .util import iter_files

@dataclass
class BuiltChunk:
    index:int
    path:Path
    meta:dict

class ChunkBuilder:
    def __init__(self, root: Path, chunk_size: int=CHUNK_SIZE_BYTES, starter_chunk_size: int|None=None):
        self.root=Path(root).resolve(); self.chunk_size=int(chunk_size)
        self.starter_chunk_size=int(starter_chunk_size) if starter_chunk_size else None
        if not self.root.is_dir(): raise ValueError("source folder does not exist")
        self.files=iter_files(self.root)
        self.total_size=sum(p.stat().st_size for p in self.files)

    def _first_chunk_limit(self):
        if not self.total_size or not self.starter_chunk_size or self.starter_chunk_size >= self.chunk_size:
            return self.chunk_size
        starter=max(1,self.starter_chunk_size)
        candidate=1 + math.ceil(max(self.total_size-starter,0)/self.chunk_size)
        # Near the absolute release capacity we fall back to uniform chunks so
        # the fast-start asset never makes us exceed GitHub's asset count.
        return starter if candidate <= MAX_DATA_ASSETS else self.chunk_size

    @property
    def chunk_count(self):
        if not self.total_size: return 0
        first=self._first_chunk_limit()
        if self.total_size <= first: return 1
        return 1 + math.ceil((self.total_size-first)/self.chunk_size)

    def validate_capacity(self):
        if self.chunk_count > MAX_DATA_ASSETS: raise ValueError(f"needs {self.chunk_count} data chunks; max is {MAX_DATA_ASSETS}")

    def build(self, temp_dir: Path, progress: Callable[[int,int],None]|None=None) -> Generator[BuiltChunk,None,dict]:
        self.validate_capacity(); temp_dir.mkdir(parents=True, exist_ok=True)
        files_meta=[]; chunks_meta=[]; processed=0; idx=0
        fp=path=chash=None; csize=0; segments=[]; current_limit=self._first_chunk_limit()

        def open_chunk():
            nonlocal fp,path,chash,csize,segments,idx,current_limit
            idx+=1
            current_limit=self._first_chunk_limit() if idx == 1 else self.chunk_size
            path=temp_dir/f"chunk-{idx:06d}.bin"; fp=path.open("wb"); chash=hashlib.sha256(); csize=0; segments=[]

        def finish():
            nonlocal fp
            if fp is None: return None
            # This is a disposable staging file. flush() makes it visible to the
            # uploader; forcing fsync() only adds storage latency and gives no
            # durability benefit because a crashed publish is discarded anyway.
            fp.flush(); fp.close()
            meta={"name":path.name,"size":csize,"sha256":chash.hexdigest(),"segments":segments.copy()}; chunks_meta.append(meta); fp=None
            return BuiltChunk(idx,path,meta)

        if self.total_size: open_chunk()
        for src in self.files:
            rel=src.relative_to(self.root).as_posix(); before=src.stat(); expected=before.st_size; fhash=hashlib.sha256(); foff=0
            with src.open("rb") as sf:
                while foff < expected:
                    if fp is None: open_chunk()
                    take=min(current_limit-csize, expected-foff); seg_foff=foff; seg_coff=csize; left=take
                    while left:
                        block=sf.read(min(left,8*1024*1024))
                        if not block: raise SourceChangedError(rel)
                        fp.write(block); chash.update(block); fhash.update(block); n=len(block); left-=n; foff+=n; csize+=n; processed+=n
                        if progress: progress(processed,self.total_size)
                    segments.append({"file":rel,"file_offset":seg_foff,"chunk_offset":seg_coff,"length":take})
                    if csize == current_limit:
                        built=finish(); yield built
            after=src.stat()
            if after.st_size != expected or after.st_mtime_ns != before.st_mtime_ns: raise SourceChangedError(f"source changed during publish: {rel}")
            files_meta.append({"path":rel,"size":expected,"sha256":fhash.hexdigest()})
        if fp is not None: yield finish()
        return {"total_size":self.total_size,"files":files_meta,"chunks":chunks_meta}
