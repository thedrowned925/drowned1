from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path


class UnsafeUninstallTarget(RuntimeError):
    pass


def validate_uninstall_target(root: Path | str, expected_tag: str | None = None) -> Path:
    """Validate that *root* looks like a Drowned-managed installation.

    We deliberately require the .drowned/state.json marker before recursively
    deleting a directory. This prevents a damaged registry from ever turning
    a drive root or an arbitrary user folder into an uninstall target.
    """
    raw = Path(root).expanduser()
    if not raw.is_absolute():
        raise UnsafeUninstallTarget("Kurulum yolu mutlak bir yol değil.")
    if raw.is_symlink():
        raise UnsafeUninstallTarget("Sembolik bağlantı olan bir klasör otomatik kaldırılamaz.")
    is_junction = getattr(raw, "is_junction", None)
    if callable(is_junction) and is_junction():
        raise UnsafeUninstallTarget("Junction olan bir klasör otomatik kaldırılamaz.")

    resolved = raw.resolve()
    anchor = Path(resolved.anchor)
    if resolved == anchor or resolved.parent == resolved:
        raise UnsafeUninstallTarget("Disk kökü güvenlik nedeniyle silinemez.")
    try:
        if resolved == Path.home().resolve():
            raise UnsafeUninstallTarget("Kullanıcı ana klasörü güvenlik nedeniyle silinemez.")
    except RuntimeError:
        pass

    marker = resolved / ".drowned" / "state.json"
    if not marker.is_file():
        raise UnsafeUninstallTarget(
            "Bu klasörde Drowned kurulum işaretçisi (.drowned/state.json) bulunamadı. "
            "Güvenlik için otomatik silme durduruldu."
        )

    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except Exception as exc:
        raise UnsafeUninstallTarget("Drowned kurulum işaretçisi okunamadı.") from exc

    actual_tag = str(state.get("tag") or "")
    expected = str(expected_tag or "")
    if expected and actual_tag and actual_tag != expected:
        raise UnsafeUninstallTarget(
            f"Kurulum etiketi eşleşmiyor: kayıt={expected}, klasör={actual_tag}. "
            "Yanlış klasörü silmemek için işlem durduruldu."
        )
    return resolved


def _make_writable_and_retry(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        raise excinfo[1]


def remove_install_tree(root: Path | str, expected_tag: str | None = None) -> Path:
    target = validate_uninstall_target(root, expected_tag)
    try:
        shutil.rmtree(target, onexc=_make_writable_and_retry)
    except TypeError:
        # Compatibility fallback for Python versions where onexc is unavailable.
        shutil.rmtree(target, onerror=_make_writable_and_retry)
    return target
