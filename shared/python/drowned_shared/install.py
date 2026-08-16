from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import requests

from .errors import DiskSpaceError, HashMismatchError
from .util import atomic_json, safe_relative_path, sha256_file
from .validation import validate_manifest

BLOCK_SIZE = 8 * 1024 * 1024


def fetch_json(url: str) -> dict:
    r = requests.get(url, timeout=60, headers={"User-Agent": "Drowned-Launcher/0.5"})
    r.raise_for_status()
    return r.json()


def _state_path(root: Path) -> Path:
    return root / ".drowned" / "state.json"


def _load_state(root: Path, tag: str) -> dict:
    path = _state_path(root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if state.get("tag") != tag:
        state = {"tag": tag, "completed_chunks": [], "verified": False}
    state.setdefault("completed_chunks", [])
    state.setdefault("verified", False)
    return state


def _save_state(root: Path, state: dict) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, state)


def find_invalid_files(
    manifest: dict,
    root: Path,
    progress=lambda done, total: None,
    cancelled=lambda: False,
) -> list[str]:
    """Return missing, wrong-sized or SHA-256-invalid manifest file paths."""
    validate_manifest(manifest)
    root = Path(root)
    files = manifest["files"]
    total = sum(int(f["size"]) for f in files)
    checked = 0
    invalid: list[str] = []

    for entry in files:
        if cancelled():
            raise RuntimeError("cancelled")
        rel = entry["path"]
        path = root / safe_relative_path(rel)
        expected_size = int(entry["size"])
        if not path.is_file() or path.stat().st_size != expected_size:
            invalid.append(rel)
            checked += expected_size
            progress(min(checked, total), total)
            continue

        digest = hashlib.sha256()
        with path.open("rb") as fp:
            while True:
                if cancelled():
                    raise RuntimeError("cancelled")
                block = fp.read(BLOCK_SIZE)
                if not block:
                    break
                digest.update(block)
                checked += len(block)
                progress(min(checked, total), total)
        if digest.hexdigest().lower() != str(entry["sha256"]).lower():
            invalid.append(rel)

    return invalid


def chunks_for_files(manifest: dict, file_paths: list[str] | set[str]) -> set[str]:
    wanted = set(file_paths)
    result: set[str] = set()
    for chunk in manifest["chunks"]:
        if any(segment["file"] in wanted for segment in chunk["segments"]):
            result.add(chunk["name"])
    return result


def _prepare_manifest_files(manifest: dict, root: Path, only_files: set[str] | None = None) -> None:
    for entry in manifest["files"]:
        rel = entry["path"]
        if only_files is not None and rel not in only_files:
            continue
        path = root / safe_relative_path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = int(entry["size"])
        if not path.exists():
            with path.open("wb") as out:
                out.truncate(expected)
        elif path.stat().st_size != expected:
            with path.open("r+b") as out:
                out.truncate(expected)


def _download_chunks(
    manifest: dict,
    root: Path,
    chunk_names: set[str],
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
) -> int:
    """Download selected chunks and write their byte ranges directly to final files."""
    if not chunk_names:
        return 0

    tag = manifest["release"]["tag"]
    selected = [c for c in manifest["chunks"] if c["name"] in chunk_names]
    total = sum(int(c["size"]) for c in selected)
    done = 0
    headers = {"User-Agent": "Drowned-Launcher/0.5"}

    for chunk in selected:
        if cancelled():
            raise RuntimeError("cancelled")
        url = (
            f"https://github.com/{manifest['release']['owner']}/{manifest['release']['repo']}"
            f"/releases/download/{tag}/{chunk['name']}"
        )
        ok = False
        for attempt in range(3):
            digest = hashlib.sha256()
            position = 0
            segment_index = 0
            current_path = None
            current_fp = None
            try:
                with requests.get(url, stream=True, timeout=(30, 300), headers=headers) as response:
                    response.raise_for_status()
                    for block in response.iter_content(BLOCK_SIZE):
                        if cancelled():
                            raise RuntimeError("cancelled")
                        if not block:
                            continue
                        digest.update(block)
                        view = memoryview(block)
                        used = 0

                        while used < len(view):
                            while (
                                segment_index < len(chunk["segments"])
                                and position >= int(chunk["segments"][segment_index]["chunk_offset"])
                                + int(chunk["segments"][segment_index]["length"])
                            ):
                                segment_index += 1
                            if segment_index >= len(chunk["segments"]):
                                raise RuntimeError(f"Geçersiz segment haritası: {chunk['name']}")

                            segment = chunk["segments"][segment_index]
                            seg_start = int(segment["chunk_offset"])
                            seg_end = seg_start + int(segment["length"])
                            if position < seg_start:
                                skip = min(len(view) - used, seg_start - position)
                                used += skip
                                position += skip
                                continue

                            take = min(len(view) - used, seg_end - position)
                            target = root / safe_relative_path(segment["file"])
                            if current_path != target:
                                if current_fp:
                                    current_fp.close()
                                current_path = target
                                current_fp = target.open("r+b")
                            within = position - seg_start
                            current_fp.seek(int(segment["file_offset"]) + within)
                            current_fp.write(view[used : used + take])
                            used += take
                            position += take
                            progress(min(done + position, total), total)
                if current_fp:
                    current_fp.close()
                    current_fp = None
            except Exception:
                if current_fp:
                    current_fp.close()
                if attempt == 2:
                    raise
                log(f"{chunk['name']} yeniden deneniyor ({attempt + 2}/3)")
                continue

            if digest.hexdigest().lower() == str(chunk["sha256"]).lower():
                ok = True
                break
            log(f"{chunk['name']} hash uyuşmadı; yeniden indiriliyor")

        if not ok:
            raise HashMismatchError(chunk["name"])
        done += int(chunk["size"])
        progress(min(done, total), total)
        log(f"Doğrulandı: {chunk['name']}")

    return len(selected)


def repair_manifest(
    manifest: dict,
    root: Path,
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
) -> dict:
    """Verify an installation and redownload only chunks touching invalid files."""
    validate_manifest(manifest)
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Kurulum klasörü bulunamadı: {root}")

    log("Dosyalar SHA-256 ile doğrulanıyor…")
    invalid = find_invalid_files(manifest, root, progress, cancelled)
    if not invalid:
        tag = manifest["release"]["tag"]
        state = _load_state(root, tag)
        state["verified"] = True
        state["completed_chunks"] = [c["name"] for c in manifest["chunks"]]
        _save_state(root, state)
        log("Tüm dosyalar sağlam.")
        return {"invalid_files": [], "repaired_files": [], "downloaded_chunks": 0}

    log(f"{len(invalid)} eksik/bozuk dosya bulundu.")
    for rel in invalid[:50]:
        log(f"  • {rel}")
    if len(invalid) > 50:
        log(f"  … ve {len(invalid) - 50} dosya daha")

    required_chunks = chunks_for_files(manifest, invalid)
    if not required_chunks:
        raise HashMismatchError("Bozuk dosyaları onaracak chunk bulunamadı")

    invalid_set = set(invalid)
    _prepare_manifest_files(manifest, root, invalid_set)

    tag = manifest["release"]["tag"]
    state = _load_state(root, tag)
    completed = set(state.get("completed_chunks", []))
    completed.difference_update(required_chunks)
    state["completed_chunks"] = sorted(completed)
    state["verified"] = False
    _save_state(root, state)

    log(f"Yalnız gerekli {len(required_chunks)} chunk yeniden indirilecek.")
    downloaded = _download_chunks(
        manifest, root, required_chunks, progress, log, cancelled
    )

    log("Onarılan dosyalar tekrar doğrulanıyor…")
    still_invalid = []
    by_path = {f["path"]: f for f in manifest["files"]}
    for rel in invalid:
        entry = by_path[rel]
        path = root / safe_relative_path(rel)
        if (
            not path.is_file()
            or path.stat().st_size != int(entry["size"])
            or sha256_file(path).lower() != str(entry["sha256"]).lower()
        ):
            still_invalid.append(rel)
    if still_invalid:
        raise HashMismatchError(", ".join(still_invalid[:5]))

    completed.update(required_chunks)
    state["completed_chunks"] = sorted(completed)
    state["verified"] = True
    _save_state(root, state)
    log(f"Onarım tamamlandı: {len(invalid)} dosya, {downloaded} chunk.")
    return {
        "invalid_files": invalid,
        "repaired_files": invalid,
        "downloaded_chunks": downloaded,
    }


def install_manifest(
    manifest: dict,
    root: Path,
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
):
    validate_manifest(manifest)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    # Only require enough free space for bytes not already allocated on disk.
    required_growth = 0
    for entry in manifest["files"]:
        path = root / safe_relative_path(entry["path"])
        existing = path.stat().st_size if path.exists() and path.is_file() else 0
        required_growth += max(0, int(entry["size"]) - existing)
    free = shutil.disk_usage(root).free
    if free < required_growth:
        raise DiskSpaceError(f"requires {required_growth} bytes; {free} free")

    tag = manifest["release"]["tag"]
    state = _load_state(root, tag)
    completed = set(state.get("completed_chunks", []))
    _prepare_manifest_files(manifest, root)

    pending = {c["name"] for c in manifest["chunks"] if c["name"] not in completed}
    if pending:
        downloaded = _download_chunks(manifest, root, pending, progress, log, cancelled)
        completed.update(pending)
        state["completed_chunks"] = sorted(completed)
        state["verified"] = False
        _save_state(root, state)
        log(f"{downloaded} chunk indirildi.")

    # A completed-chunk state can become stale when users delete or modify files.
    # Always finish by verifying and repairing only the affected chunks.
    result = repair_manifest(manifest, root, progress, log, cancelled)
    state = _load_state(root, tag)
    state["completed_chunks"] = [c["name"] for c in manifest["chunks"]]
    state["verified"] = True
    _save_state(root, state)
    return result
