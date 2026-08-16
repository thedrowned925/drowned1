from __future__ import annotations
import hashlib, math, os
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
    def __init__(self, root: Path, chunk_size: int=CHUNK_SIZE_BYTES):
        self.root=Path(root).resolve(); self.chunk_size=int(chunk_size)
        if not self.root.is_dir(): raise ValueError("source folder does not exist")
        self.files=iter_files(self.root)
        self.total_size=sum(p.stat().st_size for p in self.files)
    @property
    def chunk_count(self): return math.ceil(self.total_size/self.chunk_size) if self.total_size else 0
    def validate_capacity(self):
        if self.chunk_count > MAX_DATA_ASSETS: raise ValueError(f"needs {self.chunk_count} data chunks; max is {MAX_DATA_ASSETS}")
    def build(self, temp_dir: Path, progress: Callable[[int,int],None]|None=None) -> Generator[BuiltChunk,None,dict]:
        self.validate_capacity(); temp_dir.mkdir(parents=True, exist_ok=True)
        files_meta=[]; chunks_meta=[]; processed=0; idx=0
        fp=path=chash=None; csize=0; segments=[]
        def open_chunk():
            nonlocal fp,path,chash,csize,segments,idx
            idx+=1; path=temp_dir/f"chunk-{idx:06d}.bin"; fp=path.open("wb"); chash=hashlib.sha256(); csize=0; segments=[]
        def finish():
            nonlocal fp
            if fp is None: return None
            fp.flush(); os.fsync(fp.fileno()); fp.close()
            meta={"name":path.name,"size":csize,"sha256":chash.hexdigest(),"segments":segments.copy()}; chunks_meta.append(meta); fp=None
            return BuiltChunk(idx,path,meta)
        if self.total_size: open_chunk()
        for src in self.files:
            rel=src.relative_to(self.root).as_posix(); before=src.stat(); expected=before.st_size; fhash=hashlib.sha256(); foff=0
            with src.open("rb") as sf:
                while foff < expected:
                    if fp is None: open_chunk()
                    take=min(self.chunk_size-csize, expected-foff); seg_foff=foff; seg_coff=csize; left=take
                    while left:
                        block=sf.read(min(left,8*1024*1024))
                        if not block: raise SourceChangedError(rel)
                        fp.write(block); chash.update(block); fhash.update(block); n=len(block); left-=n; foff+=n; csize+=n; processed+=n
                        if progress: progress(processed,self.total_size)
                    segments.append({"file":rel,"file_offset":seg_foff,"chunk_offset":seg_coff,"length":take})
                    if csize == self.chunk_size:
                        built=finish(); yield built
            after=src.stat()
            if after.st_size != expected or after.st_mtime_ns != before.st_mtime_ns: raise SourceChangedError(f"source changed during publish: {rel}")
            files_meta.append({"path":rel,"size":expected,"sha256":fhash.hexdigest()})
        if fp is not None: yield finish()
        return {"total_size":self.total_size,"files":files_meta,"chunks":chunks_meta}
