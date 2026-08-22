from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from .errors import DiskSpaceError
from .install import (
    DEFAULT_DOWNLOAD_WORKERS,
    DownloadControl,
    _download_chunks,
    _prepare_manifest_files,
    chunks_for_files,
    find_invalid_files,
    repair_manifest,
)
from .util import atomic_json, safe_relative_path, slugify
from .validation import validate_manifest


def addon_state_dir(root: Path) -> Path:
    return Path(root) / ".drowned" / "addons"


def addon_state_path(root: Path, package_id: str) -> Path:
    return addon_state_dir(root) / f"{slugify(package_id)}.json"


def load_addon_state(root: Path, package_id: str) -> dict | None:
    path = addon_state_path(root, package_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("package_id") == slugify(package_id):
            return value
    except Exception:
        pass
    return None


def list_installed_addons(root: Path) -> list[dict]:
    folder = addon_state_dir(root)
    if not folder.is_dir():
        return []
    result = []
    for path in sorted(folder.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            package_id = slugify(str(value.get("package_id") or ""))
            if package_id and value.get("installed") is True:
                result.append(value)
        except Exception:
            continue
    return result


def is_addon_installed(root: Path, package_id: str, tag: str | None = None) -> bool:
    state = load_addon_state(root, package_id)
    if not state or state.get("installed") is not True:
        return False
    return not tag or str(state.get("tag") or "") == str(tag)


def _validate_optional_manifest(manifest: dict) -> dict:
    validate_manifest(manifest)
    if manifest.get("package_type") != "optional":
        raise ValueError("manifest is not an optional package")
    package = manifest.get("package") or {}
    base = manifest.get("base") or {}
    if not package.get("id") or not package.get("version"):
        raise ValueError("optional package metadata is incomplete")
    if not base.get("game_id") or not base.get("channel") or not base.get("version"):
        raise ValueError("optional package base-game metadata is incomplete")
    return manifest


def _base_identity(base_manifest: dict) -> dict:
    validate_manifest(base_manifest)
    game = base_manifest.get("game") or {}
    return {
        "game_id": str(game.get("id") or ""),
        "platform": str(game.get("platform") or ""),
        "channel": str(game.get("channel") or ""),
        "version": str(game.get("version") or ""),
        "tag": str((base_manifest.get("release") or {}).get("tag") or ""),
    }


def assert_addon_compatible(manifest: dict, base_manifest: dict) -> None:
    _validate_optional_manifest(manifest)
    identity = _base_identity(base_manifest)
    wanted = manifest.get("base") or {}
    for key in ("game_id", "platform", "channel", "version"):
        if str(wanted.get(key) or "") != identity[key]:
            raise ValueError(
                f"optional package is for another base {key}: "
                f"{wanted.get(key) or '?'} != {identity[key] or '?'}"
            )


def _package_paths(manifest: dict) -> set[str]:
    return {str(item["path"]) for item in manifest.get("files") or []}


def _base_paths(base_manifest: dict) -> set[str]:
    return {str(item["path"]) for item in base_manifest.get("files") or []}


def _required_growth(manifest: dict, root: Path) -> int:
    growth = 0
    for entry in manifest.get("files") or []:
        target = Path(root) / safe_relative_path(str(entry["path"]))
        expected = int(entry["size"])
        existing = target.stat().st_size if target.is_file() else 0
        growth += max(0, expected - existing)
    return growth


def _write_addon_state(root: Path, package_id: str, state: dict) -> None:
    state = dict(state)
    state["package_id"] = slugify(package_id)
    atomic_json(addon_state_path(root, package_id), state)


def _download_for_addon(
    manifest: dict,
    root: Path,
    state: dict,
    chunk_names: set[str],
    progress,
    log,
    cancelled,
    workers: int,
    control: DownloadControl | None,
) -> int:
    completed = set(state.get("completed_chunks") or [])
    state_lock = threading.Lock()

    def mark_complete(name: str):
        with state_lock:
            completed.add(name)
            state["completed_chunks"] = sorted(completed)
            _write_addon_state(root, state["package_id"], state)

    return _download_chunks(
        manifest,
        Path(root),
        set(chunk_names),
        progress=progress,
        log=log,
        cancelled=cancelled,
        workers=workers,
        control=control,
        on_chunk_complete=mark_complete,
    )


def install_optional_package(
    manifest: dict,
    root: Path,
    base_manifest: dict,
    *,
    manifest_url: str = "",
    base_manifest_url: str = "",
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
    workers: int = DEFAULT_DOWNLOAD_WORKERS,
    control: DownloadControl | None = None,
) -> dict:
    """Install/resume an optional package directly over an installed game."""
    _validate_optional_manifest(manifest)
    assert_addon_compatible(manifest, base_manifest)
    root = Path(root)
    if not root.is_dir():
        raise ValueError("base game install directory does not exist")

    package = manifest["package"]
    package_id = slugify(str(package["id"]))
    tag = str((manifest.get("release") or {}).get("tag") or "")
    base_identity = _base_identity(base_manifest)
    existing = load_addon_state(root, package_id) or {}
    if existing.get("tag") != tag:
        existing = {}

    growth = _required_growth(manifest, root)
    free = shutil.disk_usage(root).free
    if free < growth:
        raise DiskSpaceError(f"optional package requires {growth} extra bytes; {free} free")

    state = {
        **existing,
        "package_id": package_id,
        "title": str(package.get("title") or package_id),
        "version": str(package.get("version") or ""),
        "tag": tag,
        "manifest_url": str(manifest_url or existing.get("manifest_url") or ""),
        "base_manifest_url": str(base_manifest_url or existing.get("base_manifest_url") or ""),
        "base_tag": base_identity["tag"],
        "base": manifest.get("base") or {},
        "files": sorted(_package_paths(manifest)),
        "base_overlaps": sorted(_package_paths(manifest) & _base_paths(base_manifest)),
        "completed_chunks": list(existing.get("completed_chunks") or []),
        "installed": False,
    }
    _write_addon_state(root, package_id, state)

    all_chunks = {str(chunk["name"]) for chunk in manifest.get("chunks") or []}
    completed = set(state.get("completed_chunks") or [])
    missing_chunks = all_chunks - completed
    _prepare_manifest_files(manifest, root)
    if missing_chunks:
        log(f"Ek paket indiriliyor: {state['title']} • {len(missing_chunks)} chunk")
        _download_for_addon(
            manifest, root, state, missing_chunks, progress, log, cancelled, workers, control
        )

    # A resumed package may have had a previously completed chunk overwritten
    # by a base repair. Hash all package files once at completion and fetch only
    # the chunks that are now invalid.
    invalid = find_invalid_files(manifest, root, progress, cancelled, control)
    if invalid:
        required = chunks_for_files(manifest, invalid)
        _prepare_manifest_files(manifest, root, set(invalid))
        state["completed_chunks"] = sorted(all_chunks - required)
        _write_addon_state(root, package_id, state)
        _download_for_addon(
            manifest, root, state, required, progress, log, cancelled, workers, control
        )
        invalid = find_invalid_files(manifest, root, progress, cancelled, control)
        if invalid:
            raise RuntimeError(f"optional package verification failed: {invalid[0]}")

    state["completed_chunks"] = sorted(all_chunks)
    state["installed"] = True
    _write_addon_state(root, package_id, state)
    log(f"Ek paket kuruldu ve doğrulandı: {state['title']}")
    return state


def repair_optional_package(
    manifest: dict,
    root: Path,
    *,
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
    workers: int = DEFAULT_DOWNLOAD_WORKERS,
    control: DownloadControl | None = None,
) -> dict:
    _validate_optional_manifest(manifest)
    root = Path(root)
    package_id = slugify(str((manifest.get("package") or {}).get("id") or ""))
    state = load_addon_state(root, package_id)
    if not state or state.get("installed") is not True:
        raise ValueError(f"optional package is not installed: {package_id}")

    invalid = find_invalid_files(manifest, root, progress, cancelled, control)
    if not invalid:
        return {"repaired_files": [], "downloaded_chunks": 0}

    required = chunks_for_files(manifest, invalid)
    _prepare_manifest_files(manifest, root, set(invalid))
    completed = {str(c["name"]) for c in manifest.get("chunks") or []} - required
    state["completed_chunks"] = sorted(completed)
    _write_addon_state(root, package_id, state)
    downloaded = _download_for_addon(
        manifest, root, state, required, progress, log, cancelled, workers, control
    )
    again = find_invalid_files(manifest, root, progress, cancelled, control)
    if again:
        raise RuntimeError(f"optional package repair failed: {again[0]}")
    state["completed_chunks"] = [str(c["name"]) for c in manifest.get("chunks") or []]
    state["installed"] = True
    _write_addon_state(root, package_id, state)
    return {"repaired_files": invalid, "downloaded_chunks": downloaded}


def repair_base_with_addons(
    base_manifest: dict,
    root: Path,
    addon_manifests: list[dict],
    *,
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
    workers: int = DEFAULT_DOWNLOAD_WORKERS,
    control: DownloadControl | None = None,
) -> dict:
    """Repair the base game, then re-apply installed optional overlays."""
    result = repair_manifest(
        base_manifest,
        root,
        progress=progress,
        log=log,
        cancelled=cancelled,
        workers=workers,
        control=control,
    )
    repaired_addons = []
    for manifest in addon_manifests:
        package_id = slugify(str((manifest.get("package") or {}).get("id") or ""))
        if not is_addon_installed(root, package_id):
            continue
        repair_optional_package(
            manifest,
            root,
            progress=progress,
            log=log,
            cancelled=cancelled,
            workers=workers,
            control=control,
        )
        repaired_addons.append(package_id)
    result["reapplied_addons"] = repaired_addons
    return result


def _remove_empty_parents(target: Path, root: Path) -> None:
    parent = target.parent
    stop = Path(root).resolve()
    while parent != stop and stop in parent.resolve().parents:
        if parent.name == ".drowned":
            break
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def remove_optional_package(
    package_id: str,
    root: Path,
    base_manifest: dict,
    remaining_addon_manifests: list[dict] | None = None,
    *,
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
    workers: int = DEFAULT_DOWNLOAD_WORKERS,
    control: DownloadControl | None = None,
) -> dict:
    """Remove only package-owned files and restore any overwritten base files."""
    root = Path(root)
    package_id = slugify(package_id)
    state = load_addon_state(root, package_id)
    if not state or state.get("installed") is not True:
        return {"removed_files": [], "restored_base_files": [], "reapplied_addons": []}

    base_paths = _base_paths(base_manifest)
    owned = [str(path) for path in state.get("files") or []]
    unique_files = []
    overlap_files = []
    for rel in owned:
        safe = safe_relative_path(rel)
        target = root / safe
        if rel in base_paths:
            overlap_files.append(rel)
        else:
            unique_files.append(rel)
        if target.is_file() or target.is_symlink():
            target.unlink()
            _remove_empty_parents(target, root)

    # Removing overlapped paths makes the base repair deterministic. It also
    # protects against an add-on file having the same size as the original.
    log(
        f"Ek paket kaldırılıyor: {state.get('title') or package_id} • "
        f"{len(unique_files)} özel dosya • {len(overlap_files)} base override"
    )
    base_result = repair_manifest(
        base_manifest,
        root,
        progress=progress,
        log=log,
        cancelled=cancelled,
        workers=workers,
        control=control,
    )

    reapplied = []
    for manifest in remaining_addon_manifests or []:
        other_id = slugify(str((manifest.get("package") or {}).get("id") or ""))
        if not other_id or other_id == package_id or not is_addon_installed(root, other_id):
            continue
        repair_optional_package(
            manifest,
            root,
            progress=progress,
            log=log,
            cancelled=cancelled,
            workers=workers,
            control=control,
        )
        reapplied.append(other_id)

    addon_state_path(root, package_id).unlink(missing_ok=True)
    try:
        addon_state_dir(root).rmdir()
    except OSError:
        pass
    log(f"Ek paket kaldırıldı: {state.get('title') or package_id}")
    return {
        "removed_files": unique_files,
        "restored_base_files": overlap_files,
        "base_repaired_files": list(base_result.get("repaired_files") or []),
        "reapplied_addons": reapplied,
    }
