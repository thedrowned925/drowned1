from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return re.sub(r"-{2,}", "-", value).strip("-") or "project"


def format_bytes(value: int) -> str:
    n=float(value)
    for u in ("B","KiB","MiB","GiB","TiB"):
        if n < 1024 or u == "TiB": return f"{n:.2f} {u}"
        n /= 1024


def iter_files(root: Path) -> list[Path]:
    return sorted((p for p in root.rglob("*") if p.is_file() and not p.is_symlink()), key=lambda p: p.relative_to(root).as_posix().lower())


def sha256_file(path: Path, block_size: int=8*1024*1024) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(block_size), b""): h.update(block)
    return h.hexdigest()


def safe_relative_path(value: str) -> Path:
    if not value or "\\" in value:
        raise ValueError("manifest path must use portable forward slashes")
    p=Path(value)
    if p.is_absolute() or value.startswith("/") or ":" in value.split("/")[0] or any(part in ("", ".", "..") for part in p.parts):
        raise ValueError(f"unsafe manifest path: {value}")
    return p


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
